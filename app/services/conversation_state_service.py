import json

from app.schemas.recommendation import ChatResponse, CompletedTurnState, TurnOperation
from app.services.intent_service import (
    ClarificationIntent,
    CourseQAIntent,
    RecommendationIntent,
    SpecializationIntent,
    StudyProgramRecommendationIntent,
    StudyPlanIntent,
    classify_intent,
)


def completed_turns_context(turns: list[CompletedTurnState]) -> str | None:
    """Serialize completed facts without replaying old requests as instructions."""
    if not turns:
        return None
    payload = [
        {
            "turnIndex": index,
            **turn.model_dump(
                by_alias=True,
                exclude_none=True,
                exclude={"request"},
            ),
        }
        for index, turn in enumerate(turns[-11:])
    ]
    return "Completed conversation turns (already answered):\n" + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def model_question(latest_request: str, turns: list[CompletedTurnState]) -> str:
    context = completed_turns_context(turns)
    if context is None:
        return latest_request
    return (
        "Current user request (answer this request only):\n"
        f"{latest_request}\n\n"
        f"{context}\n"
        "Use completed turns only to resolve information omitted or explicitly referenced by the current request."
    )


def _operation_for_response(request: str, response: ChatResponse) -> TurnOperation:
    if response.study_programs:
        return "study_program_recommendation"
    if response.study_plan is not None:
        return "study_plan"
    if response.specializations:
        return "specialization"
    if response.recommendations:
        return "course_search"
    if "compare" in request.casefold() or "sammenlign" in request.casefold():
        return "comparison"

    intent = classify_intent(request)
    if isinstance(intent, CourseQAIntent):
        return "course_detail"
    if isinstance(intent, RecommendationIntent):
        return "course_search"
    if isinstance(intent, StudyProgramRecommendationIntent):
        return "study_program_recommendation"
    if isinstance(intent, StudyPlanIntent):
        return "study_plan"
    if isinstance(intent, SpecializationIntent):
        return "specialization"
    if isinstance(intent, ClarificationIntent):
        return "clarification"
    return "general"


def build_completed_turn(request: str, response: ChatResponse) -> CompletedTurnState:
    course_numbers = [course.course_number for course in response.recommendations]
    if response.understood.topic.startswith("course "):
        possible_number = response.understood.topic.removeprefix("course ").strip()
        if possible_number and possible_number not in course_numbers:
            course_numbers.append(possible_number)
    return CompletedTurnState(
        request=request,
        operation=_operation_for_response(request, response),
        topic=response.understood.topic or None,
        level=response.understood.level,
        ects=response.understood.ects,
        language=response.understood.language,
        period=response.understood.period,
        program=response.understood.program,
        courseNumbers=course_numbers,
        studyProgramNames=[program.name for program in response.study_programs],
        specializationNames=[item.name for item in response.specializations],
    )
