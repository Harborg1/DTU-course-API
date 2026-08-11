from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.orm import Session

from app.models.course import Course


@dataclass
class SearchResult:
    count: int
    courses: list[tuple[Course, float]]


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
    limit: int = 20,
    offset: int = 0,
) -> SearchResult:
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

    if q and dialect == "postgresql":
        query = func.websearch_to_tsquery("simple", q)
        filters.append(Course.search_vector.op("@@")(query))
        rank = func.ts_rank_cd(Course.search_vector, query, 32).label("relevance_score")
    elif q:
        pattern = f"%{q}%"
        searchable = [Course.title, Course.description, Course.content, Course.learning_objectives, Course.prerequisites]
        filters.append(or_(*(column.ilike(pattern) for column in searchable)))
        # SQLite is used only by isolated tests; deterministic ordering matters more than a synthetic score.
        rank = literal(1.0).label("relevance_score")
    else:
        rank = literal(0.0).label("relevance_score")

    condition = and_(*filters)
    count = session.scalar(select(func.count()).select_from(Course).where(condition)) or 0
    statement = select(Course, rank).where(condition)
    if q:
        statement = statement.order_by(rank.desc(), Course.course_number)
    else:
        statement = statement.order_by(Course.course_number)
    rows = session.execute(statement.limit(limit).offset(offset)).all()
    return SearchResult(count=count, courses=[(course, float(score or 0.0)) for course, score in rows])
