from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.orm import Session

from app.models.course import Course, CourseTranslation
from app.services.language_service import detect_user_language


@dataclass
class SearchResult:
    count: int
    courses: list[tuple[Course, float]]
    search_language: str


def search_courses(
    session: Session,
    *,
    q: str | None,
    academic_year: str,
    ects: Decimal | None = None,
    level: str | None = None,
    period: str | None = None,
    schedule: str | None = None,
    department: str | None = None,
    language: str | None = None,
    campus: str | None = None,
    search_language: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> SearchResult:
    selected_language = (
        search_language
        if search_language in {"da", "en"}
        else detect_user_language(q or "")
    )
    dialect = session.get_bind().dialect.name
    filters = [Course.academic_year == academic_year]
    if ects is not None:
        filters.append(Course.ects == ects)
    if level:
        filters.append(func.lower(Course.level) == level.casefold())
    if period:
        filters.append(Course.period.ilike(f"%{period}%"))
    if schedule:
        filters.append(Course.schedule.ilike(f"%{schedule}%"))
    if department:
        filters.append(Course.department.ilike(f"%{department}%"))
    if language:
        filters.append(func.lower(Course.language) == language.casefold())
    if campus:
        filters.append(Course.campus.ilike(f"%{campus}%"))

    if selected_language == "da":
        search_config = "danish"
        language_code = "da-DK"
    else:
        search_config = "english"
        language_code = "en-GB"

    searchable = [
        CourseTranslation.title,
        CourseTranslation.description,
        CourseTranslation.content,
        CourseTranslation.learning_objectives,
        CourseTranslation.prerequisites,
        CourseTranslation.mandatory_prerequisites,
        CourseTranslation.teaching_methods,
        CourseTranslation.literature,
        CourseTranslation.remarks,
    ]
    filters.append(CourseTranslation.language_code == language_code)

    if q and dialect == "postgresql":
        query = func.websearch_to_tsquery(search_config, q)
        filters.append(CourseTranslation.search_vector.op("@@")(query))
        rank = func.ts_rank_cd(CourseTranslation.search_vector, query, 32).label("relevance_score")
    elif q:
        pattern = f"%{q}%"
        filters.append(or_(*(column.ilike(pattern) for column in searchable)))
        # SQLite is used only by isolated tests; deterministic ordering matters more than a synthetic score.
        rank = literal(1.0).label("relevance_score")
    else:
        rank = literal(0.0).label("relevance_score")

    condition = and_(*filters)
    count = session.scalar(
        select(func.count()).select_from(Course).join(CourseTranslation).where(condition)
    ) or 0
    statement = select(Course, rank).join(CourseTranslation).where(condition)
    if q:
        statement = statement.order_by(rank.desc(), Course.course_number)
    else:
        statement = statement.order_by(Course.course_number)
    rows = session.execute(statement.limit(limit).offset(offset)).all()
    return SearchResult(
        count=count,
        courses=[(course, float(score or 0.0)) for course, score in rows],
        search_language=selected_language,
    )
