import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.course import Course, CourseTranslation
from app.services.embedding_service import EmbeddingServiceError, get_embedding_service
from app.services.language_service import detect_user_language


logger = logging.getLogger(__name__)
RRF_RANK_CONSTANT = 60


@dataclass
class SearchResult:
    count: int
    courses: list[tuple[Course, float]]
    search_language: str


def _merge_best_scores(
    rows: list[tuple[Course, float]],
) -> dict[int, tuple[Course, float]]:
    merged: dict[int, tuple[Course, float]] = {}
    for course, score in rows:
        numeric_score = float(score or 0.0)
        existing = merged.get(course.id)
        if existing is None or numeric_score > existing[1]:
            merged[course.id] = (course, numeric_score)
    return merged


def _reciprocal_rank_fusion(
    lexical: dict[int, tuple[Course, float]],
    semantic: dict[int, tuple[Course, float]],
) -> list[tuple[Course, float]]:
    fused: dict[int, tuple[Course, float]] = {}
    ranked_sources = (
        sorted(lexical.values(), key=lambda item: (-item[1], item[0].course_number)),
        sorted(semantic.values(), key=lambda item: (-item[1], item[0].course_number)),
    )
    for rows in ranked_sources:
        for rank, (course, _source_score) in enumerate(rows, start=1):
            increment = 1.0 / (RRF_RANK_CONSTANT + rank)
            existing = fused.get(course.id)
            fused[course.id] = (
                course,
                increment if existing is None else existing[1] + increment,
            )
    return sorted(
        fused.values(),
        key=lambda item: (-item[1], item[0].course_number),
    )


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
    search_all_languages: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> SearchResult:
    selected_language = (
        search_language
        if search_language in {"da", "en"}
        else detect_user_language(q or "")
    )
    dialect = session.get_bind().dialect.name
    course_filters = [Course.academic_year == academic_year]
    if ects is not None:
        course_filters.append(Course.ects == ects)
    if level:
        course_filters.append(func.lower(Course.level) == level.casefold())
    if period:
        course_filters.append(Course.period.ilike(f"%{period}%"))
    if schedule:
        course_filters.append(Course.schedule.ilike(f"%{schedule}%"))
    if department:
        course_filters.append(Course.department.ilike(f"%{department}%"))
    if language:
        course_filters.append(func.lower(Course.language) == language.casefold())
    if campus:
        course_filters.append(Course.campus.ilike(f"%{campus}%"))

    if selected_language == "da":
        selected_config = "danish"
        selected_language_code = "da-DK"
    else:
        selected_config = "english"
        selected_language_code = "en-GB"

    searchable_columns = (
        CourseTranslation.title,
        CourseTranslation.description,
        CourseTranslation.content,
        CourseTranslation.learning_objectives,
        CourseTranslation.prerequisites,
        CourseTranslation.mandatory_prerequisites,
        CourseTranslation.teaching_methods,
        CourseTranslation.literature,
        CourseTranslation.remarks,
    )

    def base_condition(language_code: str):
        return and_(
            *course_filters,
            CourseTranslation.language_code == language_code,
        )

    if not q:
        condition = base_condition(selected_language_code)
        statement = (
            select(Course, literal(0.0).label("relevance_score"))
            .join(CourseTranslation)
            .where(condition)
            .order_by(Course.course_number)
        )
        count = session.scalar(
            select(func.count())
            .select_from(Course)
            .join(CourseTranslation)
            .where(condition)
        ) or 0
        rows = session.execute(statement.limit(limit).offset(offset)).all()
        return SearchResult(
            count=count,
            courses=[(course, float(score or 0.0)) for course, score in rows],
            search_language=selected_language,
        )

    languages = (
        (("da-DK", "danish"), ("en-GB", "english"))
        if search_all_languages
        else ((selected_language_code, selected_config),)
    )
    lexical_rows: list[tuple[Course, float]] = []
    for language_code, search_config in languages:
        condition = base_condition(language_code)
        if dialect == "postgresql":
            query = func.websearch_to_tsquery(search_config, q)
            rank = func.ts_rank_cd(CourseTranslation.search_vector, query, 32)
            statement = (
                select(Course, rank.label("relevance_score"))
                .join(CourseTranslation)
                .where(condition, CourseTranslation.search_vector.op("@@")(query))
                .order_by(rank.desc(), Course.course_number)
            )
        else:
            pattern = f"%{q}%"
            statement = (
                select(Course, literal(1.0).label("relevance_score"))
                .join(CourseTranslation)
                .where(
                    condition,
                    or_(*(column.ilike(pattern) for column in searchable_columns)),
                )
                .order_by(Course.course_number)
            )
        lexical_rows.extend(
            (course, float(score or 0.0))
            for course, score in session.execute(statement).all()
        )

    semantic_rows: list[tuple[Course, float]] = []
    settings = get_settings()
    semantic_enabled = (
        dialect == "postgresql"
        and settings.semantic_course_search_enabled
        and bool(settings.embedding_api_key)
    )
    if semantic_enabled:
        try:
            query_embedding = get_embedding_service().embed_query(q)
            distance = CourseTranslation.embedding.cosine_distance(query_embedding)
            similarity = (literal(1.0) - distance).label("semantic_similarity")
            for language_code, _search_config in languages:
                statement = (
                    select(Course, similarity)
                    .join(CourseTranslation)
                    .where(
                        base_condition(language_code),
                        CourseTranslation.embedding.is_not(None),
                        CourseTranslation.embedding_model == settings.embedding_model,
                        similarity >= settings.semantic_course_min_similarity,
                    )
                    .order_by(similarity.desc(), Course.course_number)
                )
                with session.begin_nested():
                    semantic_rows.extend(
                        (course, float(score or 0.0))
                        for course, score in session.execute(statement).all()
                    )
        except (EmbeddingServiceError, SQLAlchemyError):
            semantic_rows.clear()
            logger.warning(
                "Semantic course search failed; using lexical search fallback",
                exc_info=True,
            )

    lexical = _merge_best_scores(lexical_rows)
    semantic = _merge_best_scores(semantic_rows)
    merged_rows = _reciprocal_rank_fusion(lexical, semantic)
    count = len(merged_rows)
    rows = merged_rows[offset : offset + limit]
    return SearchResult(
        count=count,
        courses=rows,
        search_language=selected_language,
    )
