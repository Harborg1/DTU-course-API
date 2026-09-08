"""Model-led conversation with MCP lookups retained as conversation context."""

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


def _completed_turns_suffix(request: ChatRequest) -> str:
    """Build bounded, client-supplied entity context for follow-up references."""
    turns = request.completed_turns[-11:]
    while turns:
        context = completed_turns_context(turns)
        if context:
            suffix = (
                "\n\nUnverified entity references from earlier completed turns; "
                "use them only to resolve references and verify facts with MCP:\n"
                f"{context}"
            )
            if len(request.messages[-1].content) + len(suffix) <= HISTORY_CHARACTER_BUDGET:
                return suffix
        turns = turns[1:]
    return ""


def conversation_messages(request: ChatRequest) -> list[dict[str, str]]:
    """Keep recent role-labelled messages within a bounded context budget."""
    completed_turns_suffix = _completed_turns_suffix(request)
    message_budget = HISTORY_CHARACTER_BUDGET - len(completed_turns_suffix)
    selected = []
    size = 0
    for message in reversed(request.messages):
        if size + len(message.content) > message_budget:
            break
        selected.append(message.model_dump())
        size += len(message.content)
    selected.reverse()
    while selected and selected[0]["role"] != "user":
        selected.pop(0)

    # The browser sends both dialogue and compact completed-turn facts. The
    # latter preserve exact entity identifiers for references such as "those
    # courses", but remain untrusted until the model verifies them with MCP.
    if selected and completed_turns_suffix:
        selected[-1]["content"] += completed_turns_suffix
    return selected


def _record_tool_context(state: CompletedTurnState, answer: MCPAnswer) -> None:
    """Record retrieved entities without presenting background lookups as recommendations."""
    courses = {}
    programs = {}
    specializations = {}
    for result in answer.tool_results:
        if result.name in {"get_courses", "search_courses", "get_new_courses"}:
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

    state.course_numbers = sorted(courses)[:200]
    state.study_program_names = [program.name for program in programs.values()][:50]
    state.specialization_names = [item.name for item in specializations.values()][:50]


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
    except CourseQAError as exc:
        logger.exception("Model-led chat could not retrieve an answer")
        if exc.code == "timeout":
            reply = (
                "Opslaget tog for lang tid. Prøv igen, eventuelt med færre kurser ad gangen."
                if language == "da"
                else "The lookup took too long. Please try again, possibly with fewer courses at a time."
            )
        elif exc.code == "incomplete":
            reply = (
                "Modellen nåede ikke at gøre svaret færdigt. Prøv spørgsmålet igen."
                if language == "da"
                else "The model did not finish the answer. Please try the question again."
            )
        else:
            reply = (
                "Jeg kunne ikke hente et fuldt svar lige nu. Prøv igen om et øjeblik."
                if language == "da"
                else "I could not retrieve a complete answer right now. Please try again in a moment."
            )
        return ChatResponse(
            reply=reply,
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
    # Compatibility metadata is derived from retrieved facts. It must not run
    # the old intent classifier or decide how the model answers a follow-up.
    response.turn_state = CompletedTurnState(
        request=latest,
        operation="general",
        responseLanguage=language,
    )
    _record_tool_context(response.turn_state, answer)
    return response
