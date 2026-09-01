"""Structured semantic fallback for requests missed by deterministic routing."""

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import get_settings
from app.services.intent_service import (
    ClarificationIntent,
    CourseQAIntent,
    Intent,
    OpenQuestionIntent,
    RecommendationIntent,
    SpecializationIntent,
    StudyProgramRecommendationIntent,
    StudyPlanIntent,
)


logger = logging.getLogger(__name__)


class SemanticQueryPlan(BaseModel):
    """A fact-free description of what the user wants the application to do."""

    model_config = ConfigDict(extra="forbid")

    domain: Literal[
        "course",
        "study_program",
        "specialization",
        "degree",
        "admission",
        "general",
    ]
    operation: Literal[
        "overview",
        "requirements",
        "list",
        "count",
        "search",
        "detail",
        "recommend",
        "compare",
        "check_eligibility",
        "clarify",
    ]
    program_mention: str | None
    specialization_mention: str | None
    course_number: str | None = Field(pattern=r"^\d{5}$")
    topic: str | None
    topics: list[str]
    result_mode: Literal["summary", "all", "page", "single"]
    language: Literal["da", "en"]
    confidence: float = Field(ge=0, le=1)
    level: Literal["BSc", "MSc", "PhD"] | None = None
    ects: float | None = Field(default=None, gt=0, le=120)
    teaching_language: Literal["English", "Danish"] | None = None
    period: str | None = None
    referenced_turn_indexes: list[int] = Field(default_factory=list)


def classify_query_semantically(
    latest_user_message: str,
    *,
    conversation: str | None = None,
) -> SemanticQueryPlan | None:
    """Return a validated query plan when keyword routing cannot identify the intent."""
    settings = get_settings()
    if not settings.semantic_intent_enabled or not settings.groq_api_key or not latest_user_message.strip():
        return None

    instructions = (
        "Classify the user's latest request for a DTU course and study-guide application. "
        "Return only the structured query plan and do not answer the request. Infer intent from semantic "
        "meaning, including short phrases, abbreviations, translations, and spelling mistakes. Extract only "
        "entities mentioned in the latest request or in explicitly supplied completed turns; never invent "
        "programme, specialization, course, or topic names. Completed turns are already answered and may only "
        "supply omitted context or resolve an explicit reference. Put the zero-based indexes of any completed "
        "turns actually used in referenced_turn_indexes. The latest request always determines the operation. "
        "Greetings in any language and questions about what the application can do are general/overview, not "
        "general/clarify. Use general/clarify only when the user has stated a concrete interest or request but "
        "has not chosen between course and study-programme recommendations; put that interest in topic. "
        "A guide, study guide, curriculum introduction, or general description of a named programme "
        "is study_program/overview. Questions about programme construction or required credits are "
        "study_program/requirements. Questions about a specialization or its courses use the specialization "
        "domain. A comparison between two named study programmes is study_program/compare, even when a "
        "programme has the same name as a specialization elsewhere. Requests for suitable degree or study "
        "programmes based on an interest use study_program/recommend and put the interest in topic. "
        "A stated interest without a clear choice between courses and study programmes uses general/clarify. "
        "Course discovery by subject uses "
        "course/search or course/recommend. For course discovery, "
        "put each distinct requested subject in topics, splitting coordinated subjects while preserving "
        "multiword subjects such as 'artificial intelligence' and 'machine learning'; otherwise use an empty "
        "topics list. Always express course-search topics as canonical English subject phrases, regardless of "
        "the user's language. Use result_mode=all when the user asks for all, every, the complete list, or "
        "equivalent. "
        "Use general only for "
        "requests unrelated to these domains, and use clarify when the intended action is genuinely ambiguous. "
        "Extract level, ECTS, teaching language, and period when relevant to course discovery."
    )
    prompt = f"Latest user request:\n{latest_user_message}"
    if conversation and conversation.strip() != latest_user_message.strip():
        prompt += f"\n\nConversation context:\n{conversation}"

    from openai import OpenAI, OpenAIError

    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        timeout=settings.semantic_intent_timeout,
        max_retries=0,
    )
    try:
        response = client.responses.parse(
            model=settings.groq_model,
            instructions=instructions,
            input=prompt,
            text_format=SemanticQueryPlan,
            temperature=0,
        )
        plan = response.output_parsed
    except (OpenAIError, ValidationError, ValueError, TypeError):
        logger.warning("Semantic intent classification failed", exc_info=True)
        return None

    if not isinstance(plan, SemanticQueryPlan):
        return None
    if plan.confidence < settings.semantic_intent_min_confidence:
        return None
    return plan


def intent_from_query_plan(plan: SemanticQueryPlan) -> Intent | None:
    """Map a semantic plan onto the application's existing routing intents."""
    if plan.operation == "compare":
        # Comparisons can involve multiple entities, while the deterministic
        # study-plan and specialization flows resolve exactly one. Keep the
        # request in the open-question MCP flow so every named entity can be
        # fetched and compared.
        return OpenQuestionIntent(confidence=plan.confidence)
    if plan.domain == "study_program" and (
        plan.operation in {"recommend", "list"} or not plan.program_mention
    ):
        return StudyProgramRecommendationIntent(
            confidence=plan.confidence,
            topic=plan.topic or "",
        )
    if plan.operation == "clarify":
        if not plan.topic:
            return OpenQuestionIntent(confidence=plan.confidence)
        return ClarificationIntent(
            confidence=plan.confidence,
            topic=plan.topic or "",
        )
    if plan.domain == "general":
        return OpenQuestionIntent(confidence=plan.confidence)
    if plan.domain == "specialization":
        return SpecializationIntent(confidence=plan.confidence)
    if plan.domain in {"study_program", "degree", "admission"}:
        return StudyPlanIntent(confidence=plan.confidence)
    if plan.domain == "course" and plan.course_number:
        return CourseQAIntent(confidence=plan.confidence, course_number=plan.course_number)
    if plan.domain == "course" and plan.operation in {"search", "recommend", "list", "count"}:
        return RecommendationIntent(
            confidence=plan.confidence,
            topic=plan.topic or "",
            level=plan.level or "",
            ects=plan.ects or 0,
            language=plan.teaching_language or "",
            period=plan.period or "",
        )
    if plan.domain == "course" and plan.operation == "detail":
        return OpenQuestionIntent(confidence=plan.confidence)
    return None
