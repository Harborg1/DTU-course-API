import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models.study_plan import (
    StudyPlanCourse,
    StudyPlanRequirement,
    StudyPlanRequirementCourse,
    StudyPlanSection,
    StudyProgram,
)
from importer.study_plan_parser import StudyProgramData, parse_study_plan_page

logger = logging.getLogger(__name__)


class StudyPlanFetchError(RuntimeError):
    pass


@dataclass
class StudyPlanImportSummary:
    discovered: int = 0
    imported: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0


class StudyPlanClient:
    def __init__(self, request_delay: float = 0.5, timeout: float = 30.0):
        self.request_delay = request_delay
        self._last_request = 0.0
        self.client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout),
            headers={
                "User-Agent": "dtu-course-api/1.0 (+official DTU study-plan importer)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, StudyPlanFetchError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def fetch(self, url: str) -> str:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if parsed.scheme != "https" or not (hostname == "dtu.dk" or hostname.endswith(".dtu.dk")):
            raise ValueError(f"Only public HTTPS pages on dtu.dk can be imported: {url}")
        elapsed = monotonic() - self._last_request
        if elapsed < self.request_delay:
            await asyncio.sleep(self.request_delay - elapsed)
        response = await self.client.get(url)
        self._last_request = monotonic()
        response.raise_for_status()
        if "<html" not in response.text.casefold():
            raise StudyPlanFetchError(f"DTU returned non-HTML content for {url}")
        return response.text


def read_program_urls(path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip().startswith("https://")]


def study_plan_content_hash(data: StudyProgramData) -> str:
    payload = json.dumps(data.hash_payload(), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _make_program(
    data: StudyProgramData,
    digest: str,
    program: StudyProgram | None = None,
) -> StudyProgram:
    if program is None:
        program = StudyProgram()
    program.slug = data.slug
    program.name = data.name
    program.degree_type = data.degree_type
    program.aliases = data.aliases
    program.academic_year = data.academic_year
    program.valid_from_year = data.valid_from_year
    program.valid_to_year = data.valid_to_year
    program.introduction = data.introduction
    program.source_url = data.source_url
    program.content_hash = digest
    requirements_by_key: dict[str, StudyPlanRequirement] = {}
    pending_parents: list[tuple[StudyPlanRequirement, str]] = []

    for section_data in data.sections:
        section = StudyPlanSection(
            name=section_data.name,
            description=section_data.description,
            position=section_data.position,
        )
        program.sections.append(section)
        courses_by_key: dict[str, StudyPlanCourse] = {}
        for course_data in section_data.courses:
            course = StudyPlanCourse(
                program=program,
                course_number=course_data.course_number,
                title=course_data.title,
                ects=course_data.ects,
                ects_options=course_data.ects_options,
                schedule=course_data.schedule,
                source_url=course_data.source_url,
                requirement_role=course_data.requirement_role,
                position=course_data.position,
            )
            section.courses.append(course)
            courses_by_key[course_data.key] = course

        for requirement_data in section_data.requirements:
            requirement = StudyPlanRequirement(
                program=program,
                requirement_type=requirement_data.requirement_type,
                description=requirement_data.description,
                required_ects=requirement_data.required_ects,
                required_count=requirement_data.required_count,
                position=requirement_data.position,
            )
            section.requirements.append(requirement)
            requirements_by_key[requirement_data.key] = requirement
            if requirement_data.parent_key:
                pending_parents.append((requirement, requirement_data.parent_key))
            for member_key in requirement_data.member_keys:
                course = courses_by_key.get(member_key)
                if course is not None:
                    requirement.course_links.append(StudyPlanRequirementCourse(course=course))

    for requirement, parent_key in pending_parents:
        requirement.parent = requirements_by_key.get(parent_key)
    return program


def upsert_study_plan(session: Session, data: StudyProgramData) -> str:
    digest = study_plan_content_hash(data)
    existing = session.scalar(select(StudyProgram).where(StudyProgram.source_url == data.source_url))
    if existing is not None and existing.content_hash == digest:
        return "unchanged"
    action = "imported" if existing is None else "updated"
    if existing is not None:
        # Keep the StudyProgram row stable so child data imported from other
        # sources, such as specializations, survives a curriculum refresh.
        existing.sections.clear()
        session.flush()
        _make_program(data, digest, existing)
    else:
        session.add(_make_program(data, digest))
    session.flush()
    return action


async def run_study_plan_import(
    session: Session,
    *,
    urls: list[str],
    request_delay: float = 0.5,
) -> StudyPlanImportSummary:
    summary = StudyPlanImportSummary(discovered=len(urls))
    async with StudyPlanClient(request_delay=request_delay) as client:
        for url in urls:
            try:
                html = await client.fetch(url)
                data = parse_study_plan_page(html, url)
                action = upsert_study_plan(session, data)
                session.commit()
                setattr(summary, action, getattr(summary, action) + 1)
            except Exception:
                session.rollback()
                logger.exception("Failed to import study plan from %s", url)
                summary.failed += 1
    return summary
