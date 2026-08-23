import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.course import Course, CourseTranslation
from app.models.import_failure import ImportFailure
from app.models.import_run import ImportRun
from app.schemas.course import CourseData
from importer.course_xml_parser import parse_course_xml
from importer.importer import (
    course_content_hash,
    course_translation_values,
    course_values,
    record_failure,
    upsert_course,
)


logger = logging.getLogger(__name__)


@dataclass
class CourseXmlImportSummary:
    courses_discovered: int = 0
    courses_imported: int = 0
    courses_updated: int = 0
    courses_unchanged: int = 0
    courses_failed: int = 0


def import_course_xml_directory(
    session: Session,
    directory: Path,
    *,
    academic_year: str | None = None,
    limit: int | None = None,
) -> CourseXmlImportSummary:
    paths = sorted(directory.glob("*.txt"))
    if limit is not None:
        paths = paths[:limit]
    if not paths:
        raise ValueError(f"no .txt XML files found in {directory}")

    run_year = academic_year or "unknown"
    summary = CourseXmlImportSummary(courses_discovered=len(paths))
    import_run = ImportRun(academic_year=run_year, status="running")
    session.add(import_run)
    session.commit()

    parsed: list[CourseData] = []
    failures: list[tuple[str, str, Exception]] = []
    for path in paths:
        course_number = path.stem.upper()
        source_url = f"https://kurser.dtu.dk/course/{run_year}/{course_number}"
        try:
            data = parse_course_xml(path.read_bytes())
            if data.course_number != course_number:
                raise ValueError(
                    f"{path.name} contains course {data.course_number}, expected {course_number}"
                )
            if academic_year and data.academic_year != academic_year:
                raise ValueError(
                    f"{path.name} contains {data.academic_year}, expected {academic_year}"
                )
            if run_year == "unknown":
                run_year = data.academic_year
                import_run.academic_year = run_year
            parsed.append(data)
        except Exception as exc:
            failures.append((course_number, source_url, exc))
            logger.exception("Failed to parse %s", path)

    if session.get_bind().dialect.name == "postgresql":
        _bulk_upsert_postgresql(session, parsed, summary)
    else:
        for index, data in enumerate(parsed, start=1):
            action = upsert_course(session, data)
            setattr(summary, f"courses_{action}", getattr(summary, f"courses_{action}") + 1)
            logger.info("[%d/%d] %s: %s", index, len(parsed), data.course_number, action)

    successful_numbers = [data.course_number for data in parsed]
    if successful_numbers:
        session.execute(
            delete(ImportFailure).where(
                ImportFailure.academic_year == run_year,
                ImportFailure.course_number.in_(successful_numbers),
            )
        )
    for course_number, source_url, exc in failures:
        record_failure(session, course_number, run_year, source_url, exc)
    summary.courses_failed = len(failures)

    import_run.status = "completed" if summary.courses_failed == 0 else "completed_with_errors"
    import_run.completed_at = datetime.now(UTC)
    for key, value in asdict(summary).items():
        setattr(import_run, key, value)
    session.commit()
    return summary


def _bulk_upsert_postgresql(
    session: Session,
    courses: list[CourseData],
    summary: CourseXmlImportSummary,
    *,
    batch_size: int = 50,
) -> None:
    if not courses:
        return
    years = {course.academic_year for course in courses}
    existing = {
        (course_number, academic_year): content_hash
        for course_number, academic_year, content_hash in session.execute(
            select(Course.course_number, Course.academic_year, Course.content_hash).where(
                Course.academic_year.in_(years)
            )
        )
    }

    rows = []
    changed_courses = []
    for course in courses:
        digest = course_content_hash(course)
        key = (course.course_number, course.academic_year)
        previous_hash = existing.get(key)
        if previous_hash == digest:
            summary.courses_unchanged += 1
            continue
        if previous_hash is None:
            summary.courses_imported += 1
        else:
            summary.courses_updated += 1
        rows.append({**course_values(course), "content_hash": digest})
        changed_courses.append(course)

    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        statement = insert(Course).values(batch)
        update_values = {
            key: getattr(statement.excluded, key)
            for key in batch[0]
            if key not in {"course_number", "academic_year"}
        }
        update_values["updated_at"] = func.now()
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[Course.course_number, Course.academic_year],
                set_=update_values,
            )
        )
        logger.info("Upserted %d/%d changed courses", min(offset + batch_size, len(rows)), len(rows))

    course_ids = {
        (course_number, academic_year): course_id
        for course_id, course_number, academic_year in session.execute(
            select(Course.id, Course.course_number, Course.academic_year).where(
                Course.academic_year.in_(years)
            )
        )
    }
    translation_rows = []
    for course in changed_courses:
        course_id = course_ids[(course.course_number, course.academic_year)]
        for language in ("da", "en"):
            translation_rows.append(
                {
                    "course_id": course_id,
                    **course_translation_values(course, language),
                }
            )

    for offset in range(0, len(translation_rows), batch_size):
        batch = translation_rows[offset : offset + batch_size]
        statement = insert(CourseTranslation).values(batch)
        update_values = {
            key: getattr(statement.excluded, key)
            for key in batch[0]
            if key not in {"course_id", "language_code"}
        }
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[CourseTranslation.course_id, CourseTranslation.language_code],
                set_=update_values,
            )
        )
