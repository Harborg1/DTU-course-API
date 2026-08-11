import asyncio
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from time import monotonic

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models.course import Course
from app.models.import_failure import ImportFailure
from app.models.import_run import ImportRun
from app.schemas.course import CourseData
from importer.course_list import parse_course_numbers, parse_departments
from importer.course_parser import parse_course_page

logger = logging.getLogger(__name__)


class FetchError(RuntimeError):
    pass


@dataclass
class ImportSummary:
    courses_discovered: int = 0
    courses_imported: int = 0
    courses_updated: int = 0
    courses_unchanged: int = 0
    courses_failed: int = 0


class DtuClient:
    def __init__(self, base_url: str, request_delay: float = 0.5, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.request_delay = request_delay
        self._last_request = 0.0
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            follow_redirects=True,
            timeout=httpx.Timeout(timeout),
            headers={
                "User-Agent": "dtu-course-api/1.0 (+course catalogue importer; contact your deployment administrator)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )

    async def __aenter__(self):
        await self._request("/search")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, FetchError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _request(self, path: str, *, params: dict[str, str] | None = None) -> str:
        elapsed = monotonic() - self._last_request
        if elapsed < self.request_delay:
            await asyncio.sleep(self.request_delay - elapsed)
        try:
            response = await self.client.get(path, params=params)
            self._last_request = monotonic()
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("HTTP request failed for %s", path, exc_info=True)
            raise
        html = response.text
        if "forceLogin=true" in html:
            raise FetchError(f"DTU session challenge received for {path}")
        if "<html" not in html.lower():
            raise FetchError(f"DTU returned non-HTML content for {path}")
        return html

    async def fetch_departments(self) -> str:
        return await self._request("/CourseList/list/")

    async def fetch_course_list(self, academic_year: str, department: str) -> str:
        return await self._request(
            "/courselist/courselist.aspx",
            params={"volume": academic_year.replace("-", "/"), "department": department},
        )

    async def fetch_course_page(self, course_number: str, academic_year: str) -> str:
        return await self._request(f"/course/{academic_year}/{course_number}")


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


async def discover_courses(client: DtuClient, academic_year: str) -> list[str]:
    departments = parse_departments(await client.fetch_departments())
    logger.info("Found %d departments in the official DTU course list", len(departments))
    numbers: set[str] = set()
    for department in departments:
        html = await client.fetch_course_list(academic_year, department.code)
        found = parse_course_numbers(html)
        logger.info("Department %s: %d courses", department.code, len(found))
        numbers.update(found)
    result = sorted(numbers)
    logger.info("Courses discovered: %d", len(result))
    return result


async def run_import(
    session: Session,
    *,
    academic_year: str,
    base_url: str,
    request_delay: float,
    course: str | None = None,
    retry_failed: bool = False,
    limit: int | None = None,
) -> ImportSummary:
    summary = ImportSummary()
    import_run = ImportRun(academic_year=academic_year, status="running")
    session.add(import_run)
    session.commit()
    logger.info("Starting DTU course import for %s", academic_year)
    async with DtuClient(base_url, request_delay) as client:
        if course:
            course_numbers = [course.upper()]
        elif retry_failed:
            course_numbers = list(
                session.scalars(
                    select(ImportFailure.course_number)
                    .where(ImportFailure.academic_year == academic_year)
                    .order_by(ImportFailure.course_number)
                )
            )
        else:
            course_numbers = await discover_courses(client, academic_year)
        if limit is not None:
            course_numbers = course_numbers[:limit]
        summary.courses_discovered = len(course_numbers)

        for index, course_number in enumerate(course_numbers, 1):
            source_url = f"{base_url.rstrip('/')}/course/{academic_year}/{course_number}"
            try:
                html = await client.fetch_course_page(course_number, academic_year)
                data = parse_course_page(html, course_number, academic_year, base_url)
                action = upsert_course(session, data)
                clear_failure(session, course_number, academic_year)
                session.commit()
                setattr(summary, f"courses_{action}", getattr(summary, f"courses_{action}") + 1)
                logger.info("[%d/%d] %s: %s", index, len(course_numbers), course_number, action)
            except (httpx.HTTPError, FetchError, ValueError, ValidationError, Exception) as exc:
                session.rollback()
                logger.exception("[%d/%d] Failed to import %s", index, len(course_numbers), course_number)
                try:
                    record_failure(session, course_number, academic_year, source_url, exc)
                    session.commit()
                except Exception:
                    session.rollback()
                    logger.exception("Could not persist import failure for %s", course_number)
                summary.courses_failed += 1
    import_run.status = "completed" if summary.courses_failed == 0 else "completed_with_errors"
    import_run.completed_at = datetime.now(UTC)
    for key, value in asdict(summary).items():
        setattr(import_run, key, value)
    session.commit()
    logger.info("Import summary: %s", asdict(summary))
    return summary
