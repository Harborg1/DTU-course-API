import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.import_failure import ImportFailure
from app.schemas.course import CourseData


def course_content_hash(data: CourseData) -> str:
    payload = data.model_dump(mode="json")
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def upsert_course(session: Session, data: CourseData) -> str:
    existing = session.scalar(
        select(Course).where(
            Course.course_number == data.course_number,
            Course.academic_year == data.academic_year,
        )
    )
    digest = course_content_hash(data)
    values = data.model_dump()
    if existing is None:
        session.add(Course(**values, content_hash=digest))
        session.flush()
        return "imported"
    if existing.content_hash == digest:
        return "unchanged"
    for key, value in values.items():
        setattr(existing, key, value)
    existing.content_hash = digest
    session.flush()
    return "updated"


def record_failure(session: Session, course_number: str, academic_year: str, source_url: str, exc: Exception) -> None:
    failure = session.scalar(
        select(ImportFailure).where(
            ImportFailure.course_number == course_number,
            ImportFailure.academic_year == academic_year,
        )
    )
    if failure is None:
        failure = ImportFailure(
            course_number=course_number,
            academic_year=academic_year,
            source_url=source_url,
            error_type=type(exc).__name__,
            error_message=str(exc)[:4000],
        )
        session.add(failure)
    else:
        failure.error_type = type(exc).__name__
        failure.error_message = str(exc)[:4000]
        failure.attempts += 1


def clear_failure(session: Session, course_number: str, academic_year: str) -> None:
    failure = session.scalar(
        select(ImportFailure).where(
            ImportFailure.course_number == course_number,
            ImportFailure.academic_year == academic_year,
        )
    )
    if failure is not None:
        session.delete(failure)
