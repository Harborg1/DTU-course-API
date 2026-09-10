import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.course import Course, CourseTranslation
from app.services.embedding_service import EmbeddingServiceError, get_embedding_service
from app.services.language_service import detect_user_language


logger = logging.getLogger(__name__)
RRF_RANK_CONSTANT = 60
SUMMARY_CANDIDATE_LIMIT = 100

SearchResultMode = Literal["summary", "all"]


@dataclass
class SearchResult:
    count: int
    courses: list[tuple[Course, float]]
    search_language: str
    result_mode: SearchResultMode = "all"


def _count_distinct_matches(session: Session, statements: list) -> int:
    """Count a union of matching course IDs without materializing courses."""
    if not statements:
        return 0
    matches = union_all(*statements).subquery()
    return int(
        session.scalar(
            select(func.count(func.distinct(matches.c.course_id)))
        )
        or 0
    )


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
    result_mode: SearchResultMode = "all",
) -> SearchResult:
    if result_mode not in {"summary", "all"}:
        raise ValueError("result_mode must be 'summary' or 'all'")

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
            result_mode=result_mode,
        )

    languages = (
        (("da-DK", "danish"), ("en-GB", "english"))
        if search_all_languages
        else ((selected_language_code, selected_config),)
    )
    lexical_rows: list[tuple[Course, float]] = []
    lexical_match_statements = []
    candidate_limit = max(SUMMARY_CANDIDATE_LIMIT, offset + limit)
    for language_code, search_config in languages:
        condition = base_condition(language_code)
        if dialect == "postgresql":
            query = func.websearch_to_tsquery(search_config, q)
            rank = func.ts_rank_cd(CourseTranslation.search_vector, query, 32)
            match_condition = CourseTranslation.search_vector.op("@@")(query)
            statement = (
                select(Course, rank.label("relevance_score"))
                .join(CourseTranslation)
                .where(condition, match_condition)
                .order_by(rank.desc(), Course.course_number)
            )
            match_statement = (
                select(Course.id.label("course_id"))
                .join(CourseTranslation)
                .where(condition, match_condition)
            )
        else:
            pattern = f"%{q}%"
            match_condition = or_(*(column.ilike(pattern) for column in searchable_columns))
            statement = (
                select(Course, literal(1.0).label("relevance_score"))
                .join(CourseTranslation)
                .where(condition, match_condition)
                .order_by(Course.course_number)
            )
            match_statement = (
                select(Course.id.label("course_id"))
                .join(CourseTranslation)
                .where(condition, match_condition)
            )
        lexical_match_statements.append(match_statement)
        if result_mode == "summary":
            statement = statement.limit(candidate_limit)
        lexical_rows.extend(
            (course, float(score or 0.0))
            for course, score in session.execute(statement).all()
        )

    semantic_rows: list[tuple[Course, float]] = []
    semantic_match_statements = []
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
                match_statement = (
                    select(Course.id.label("course_id"))
                    .join(CourseTranslation)
                    .where(
                        base_condition(language_code),
                        CourseTranslation.embedding.is_not(None),
                        CourseTranslation.embedding_model == settings.embedding_model,
                        similarity >= settings.semantic_course_min_similarity,
                    )
                )
                if result_mode == "summary":
                    statement = statement.limit(candidate_limit)
                with session.begin_nested():
                    semantic_rows.extend(
                        (course, float(score or 0.0))
                        for course, score in session.execute(statement).all()
                    )
                semantic_match_statements.append(match_statement)
        except (EmbeddingServiceError, SQLAlchemyError):
            semantic_rows.clear()
            semantic_match_statements.clear()
            logger.warning(
                "Semantic course search failed; using lexical search fallback",
                exc_info=True,
            )

    lexical = _merge_best_scores(lexical_rows)
    semantic = _merge_best_scores(semantic_rows)
    merged_rows = _reciprocal_rank_fusion(lexical, semantic)
    if result_mode == "all":
        count = len(merged_rows)
    else:
        match_statements = lexical_match_statements + semantic_match_statements
        try:
            with session.begin_nested():
                count = _count_distinct_matches(session, match_statements)
        except SQLAlchemyError:
            # A provider-specific vector expression may fail even after the
            # candidate query succeeded. Keep the lexical count usable.
            logger.warning(
                "Could not count semantic search matches; using lexical count",
                exc_info=True,
            )
            with session.begin_nested():
                count = _count_distinct_matches(session, lexical_match_statements)
    rows = merged_rows[offset : offset + limit]
    return SearchResult(
        count=count,
        courses=rows,
        search_language=selected_language,
        result_mode=result_mode,
    )
