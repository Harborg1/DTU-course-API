"""Model-led conversation with factual UI results from remote MCP calls."""

import logging

from pydantic import ValidationError

from app.schemas.recommendation import (
    ChatRequest,
    ChatResponse,
    CompletedTurnState,
    RecommendedCourse,
    RecommendedStudyProgram,
    SpecializationInfo,
    UnderstoodContext,
)
from app.services.conversation_state_service import completed_turns_context
from app.services.course_qa_service import CourseQAError, MCPAnswer, respond_with_remote_mcp
from app.services.language_service import resolve_response_language


logger = logging.getLogger(__name__)
HISTORY_CHARACTER_BUDGET = 48000


def conversation_messages(request: ChatRequest) -> list[dict[str, str]]:
    """Keep recent role-labelled messages within a bounded context budget."""
    selected = []
    size = 0
    for message in reversed(request.messages):
        if size + len(message.content) > HISTORY_CHARACTER_BUDGET:
            break
        selected.append(message.model_dump())
        size += len(message.content)
    selected.reverse()
    while selected and selected[0]["role"] != "user":
        selected.pop(0)

    # Older API clients only supply completed-turn facts. Keep supporting them,
    # but prefer actual dialogue whenever it is available.
    if len(request.messages) == 1 and request.completed_turns:
        context = completed_turns_context(request.completed_turns)
        if context:
            prefix = (
                "\n\nUnverified context supplied by the client; already completed, "
                "not new requests:\n"
            )
            selected[0]["content"] += prefix + context[:HISTORY_CHARACTER_BUDGET - size - len(prefix)]
    return selected


def _attach_tool_results(response: ChatResponse, answer: MCPAnswer) -> None:
    """Preserve source-backed cards without classifying or rewriting the request."""
    courses = {}
    programs = {}
    specializations = {}
    for result in answer.tool_results:
        if result.name in {"search_courses", "get_new_courses"}:
            for data in result.data.get("courses", []):
                try:
                    course = RecommendedCourse.model_validate({**data, "reason": ""})
                except (ValidationError, TypeError):
                    continue
                courses[course.course_number] = course
        elif result.name == "get_study_plan":
            try:
                program = RecommendedStudyProgram.model_validate({
                    "name": result.data.get("program_name"),
                    "degree_type": result.data.get("degree_type"),
                    "source_url": result.data.get("source_url"),
                    "reason": "",
                })
            except ValidationError:
                continue
            programs[program.source_url] = program
        elif result.name == "get_specializations":
            for data in result.data.get("specializations", []):
                try:
                    specialization = SpecializationInfo.model_validate({
                        **data, "program_name": result.data.get("program_name"),
                    })
                except (ValidationError, TypeError):
                    continue
                specializations[specialization.source_url] = specialization

    response.recommendations = sorted(courses.values(), key=lambda course: course.course_number)
    response.study_programs = list(programs.values())
    response.specializations = list(specializations.values())
    # The model already explains the study plan in its answer. Keep programme
    # cards as compact source references instead of repeating the introduction
    # and entire curriculum beneath every answer that uses get_study_plan.


def answer_chat(request: ChatRequest, academic_year: str) -> ChatResponse:
    latest = request.messages[-1].content
    language = resolve_response_language(
        latest,
        previous_messages=[message.content for message in request.messages[:-1]],
        previous_languages=[turn.response_language for turn in request.completed_turns],
    )
    try:
        answer = respond_with_remote_mcp(
            latest,
            academic_year,
            response_language=language,
            messages=conversation_messages(request),
        )
    except CourseQAError:
        logger.exception("Model-led chat could not retrieve an answer")
        return ChatResponse(
            reply=(
                "Jeg kunne ikke hente et fuldt svar lige nu. Prøv igen om et øjeblik."
                if language == "da"
                else "I could not retrieve a complete answer right now. Please try again in a moment."
            ),
            understood=UnderstoodContext(topic=""),
            academicYear=academic_year,
            responseLanguage=language,
            isDirectAnswer=True,
        )

    response = ChatResponse(
        reply=answer.reply,
        understood=UnderstoodContext(topic=""),
        academicYear=academic_year,
        responseLanguage=language,
        isDirectAnswer=True,
    )
    _attach_tool_results(response, answer)
    # Compatibility metadata is derived from retrieved facts. It must not run
    # the old intent classifier or decide how the model answers a follow-up.
    response.turn_state = CompletedTurnState(
        request=latest,
        operation="general",
        courseNumbers=[course.course_number for course in response.recommendations][:200],
        studyProgramNames=[program.name for program in response.study_programs][:50],
        specializationNames=[item.name for item in response.specializations][:50],
        responseLanguage=language,
    )
    return response
