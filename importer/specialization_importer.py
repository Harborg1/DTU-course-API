import hashlib
import json
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.specialization import (
    SpecializationCourse,
    SpecializationRequirement,
    SpecializationRequirementCourse,
    StudySpecialization,
)
from app.models.study_plan import StudyProgram
from importer.specialization_parser import SpecializationData, parse_specialization_page
from importer.study_plan_importer import StudyPlanClient

logger = logging.getLogger(__name__)


@dataclass
class SpecializationImportSummary:
    discovered: int = 0
    imported: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0


def read_specialization_urls(path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip().startswith("https://")]


def specialization_content_hash(data: SpecializationData) -> str:
    payload = json.dumps(data.hash_payload(), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _make_specialization(program: StudyProgram, data: SpecializationData, digest: str) -> StudySpecialization:
    specialization = StudySpecialization(
        program=program,
        slug=data.slug,
        name=data.name,
        description=data.description,
        source_url=data.source_url,
        content_hash=digest,
        position=data.position,
    )
    courses_by_key: dict[str, SpecializationCourse] = {}
    for course_data in data.courses:
        course = SpecializationCourse(
            course_number=course_data.course_number,
            title=course_data.title,
            ects=course_data.ects,
            schedule=course_data.schedule,
            source_url=course_data.source_url,
            role=course_data.role,
            is_terminated=course_data.is_terminated,
            position=course_data.position,
        )
        specialization.courses.append(course)
        courses_by_key[course_data.key] = course

    for requirement_data in data.requirements:
        requirement = SpecializationRequirement(
            requirement_type=requirement_data.requirement_type,
            description=requirement_data.description,
            required_ects=requirement_data.required_ects,
            required_count=requirement_data.required_count,
            position=requirement_data.position,
        )
        specialization.requirements.append(requirement)
        for member_key in requirement_data.member_keys:
            course = courses_by_key.get(member_key)
            if course is not None:
                requirement.course_links.append(SpecializationRequirementCourse(course=course))
    return specialization


def upsert_specialization(session: Session, data: SpecializationData) -> str:
    program = session.scalar(select(StudyProgram).where(StudyProgram.slug == data.program_slug))
    if program is None:
        raise ValueError(
            f"Study program '{data.program_slug}' is missing; import app/data/program_urls.txt first"
        )
    digest = specialization_content_hash(data)
    existing = session.scalar(
        select(StudySpecialization).where(
            StudySpecialization.program_id == program.id,
            StudySpecialization.slug == data.slug,
        )
    )
    if existing is not None and existing.content_hash == digest:
        return "unchanged"
    action = "imported" if existing is None else "updated"
    if existing is not None:
        session.delete(existing)
        session.flush()
    session.add(_make_specialization(program, data, digest))
    session.flush()
    return action


async def run_specialization_import(
    session: Session,
    *,
    urls: list[str],
    request_delay: float = 0.5,
) -> SpecializationImportSummary:
    summary = SpecializationImportSummary(discovered=len(urls))
    async with StudyPlanClient(request_delay=request_delay) as client:
        for page_position, url in enumerate(urls):
            try:
                html = await client.fetch(url)
                specializations = parse_specialization_page(html, url)
                parsed_slugs = {data.slug for data in specializations}
                for offset, data in enumerate(specializations):
                    data.position = page_position * 10 + offset
                    action = upsert_specialization(session, data)
                    setattr(summary, action, getattr(summary, action) + 1)

                program_slug = specializations[0].program_slug
                program = session.scalar(select(StudyProgram).where(StudyProgram.slug == program_slug))
                if program is not None:
                    stale = list(
                        session.scalars(
                            select(StudySpecialization).where(
                                StudySpecialization.program_id == program.id,
                                StudySpecialization.source_url == url,
                                StudySpecialization.slug.not_in(parsed_slugs),
                            )
                        )
                    )
                    for specialization in stale:
                        session.delete(specialization)
                session.commit()
            except Exception:
                session.rollback()
                logger.exception("Failed to import specialization page %s", url)
                summary.failed += 1
    return summary
