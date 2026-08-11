from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.course import Course
from app.models.import_failure import ImportFailure
from app.models.import_run import ImportRun
from app.schemas.course import CourseDetail, CourseSummary
from app.schemas.search import CourseListResponse, CourseSearchResponse
from app.security.api_key import require_api_key
from app.services.course_service import get_course
from app.services.search_service import search_courses

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])


def _summary(course: Course, score: float | None) -> CourseSummary:
    description = course.description
    if description and len(description) > 500:
        description = description[:497].rstrip() + "..."
    return CourseSummary(
        courseNumber=course.course_number,
        title=course.title,
        ects=course.ects,
        level=course.level,
        period=course.period,
        schedule=course.schedule,
        language=course.language,
        department=course.department,
        campus=course.campus,
        description=description,
        relevanceScore=round(score, 6) if score is not None else None,
        sourceUrl=course.source_url,
    )


def _search(
    session: Session,
    q: str | None,
    academic_year: str,
    ects: Decimal | None,
    level: str | None,
    period: str | None,
    schedule: str | None,
    department: str | None,
    language: str | None,
    campus: str | None,
    limit: int,
    offset: int,
) -> CourseSearchResponse:
    result = search_courses(
        session, q=q, academic_year=academic_year, ects=ects, level=level, period=period,
        schedule=schedule, department=department, language=language, campus=campus,
        limit=limit, offset=offset,
    )
    return CourseSearchResponse(
        count=result.count, limit=limit, offset=offset,
        courses=[_summary(course, score if q else None) for course, score in result.courses],
    )


@router.get(
    "/courses/search",
    response_model=CourseSearchResponse,
    response_model_by_alias=True,
    summary="Search official DTU courses",
)
def search(
    session: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    academic_year: Annotated[str, Query(pattern=r"^\d{4}-\d{4}$")] = get_settings().default_academic_year,
    ects: Annotated[Decimal | None, Query(gt=0, le=120)] = None,
    level: str | None = None,
    period: str | None = None,
    schedule: str | None = None,
    department: str | None = None,
    language: str | None = None,
    campus: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CourseSearchResponse:
    return _search(session, q, academic_year, ects, level, period, schedule, department, language, campus, limit, offset)


@router.get("/courses", response_model=CourseListResponse, response_model_by_alias=True, summary="List DTU courses")
def list_courses(
    session: Annotated[Session, Depends(get_db)],
    academic_year: Annotated[str, Query(pattern=r"^\d{4}-\d{4}$")] = get_settings().default_academic_year,
    ects: Annotated[Decimal | None, Query(gt=0, le=120)] = None,
    level: str | None = None,
    period: str | None = None,
    schedule: str | None = None,
    department: str | None = None,
    language: str | None = None,
    campus: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CourseListResponse:
    return _search(session, None, academic_year, ects, level, period, schedule, department, language, campus, limit, offset)


@router.get("/courses/{course_number}", response_model=CourseDetail, response_model_by_alias=True, summary="Get one DTU course")
def course_detail(
    course_number: str,
    session: Annotated[Session, Depends(get_db)],
    academic_year: Annotated[str, Query(pattern=r"^\d{4}-\d{4}$")] = get_settings().default_academic_year,
) -> Course:
    course = get_course(session, course_number, academic_year)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


class ImportStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    academic_year: str = Field(alias="academicYear")
    course_count: int = Field(alias="courseCount")
    last_successful_import: datetime | None = Field(alias="lastSuccessfulImport")
    failed_imports: int = Field(alias="failedImports")


@router.get("/import/status", response_model=ImportStatusResponse, response_model_by_alias=True, summary="Get import status")
def import_status(
    session: Annotated[Session, Depends(get_db)],
    academic_year: Annotated[str, Query(pattern=r"^\d{4}-\d{4}$")] = get_settings().default_academic_year,
) -> ImportStatusResponse:
    count = session.scalar(select(func.count()).select_from(Course).where(Course.academic_year == academic_year)) or 0
    last_import = session.scalar(
        select(func.max(ImportRun.completed_at)).where(
            ImportRun.academic_year == academic_year,
            ImportRun.status == "completed",
        )
    )
    failures = session.scalar(
        select(func.count()).select_from(ImportFailure).where(ImportFailure.academic_year == academic_year)
    ) or 0
    return ImportStatusResponse(
        academicYear=academic_year, courseCount=count, lastSuccessfulImport=last_import, failedImports=failures
    )
