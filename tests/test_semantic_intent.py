from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from app.models.specialization import StudySpecialization
from app.models.course import Course, CourseTranslation
from app.models.study_plan import StudyProgram
from app.schemas.recommendation import CompletedTurnState
from app.services.recommendation_service import recommend_courses
from app.services.semantic_intent_service import (
    SemanticQueryPlan,
    classify_query_semantically,
    intent_from_query_plan,
)
from app.services.intent_service import (
    ClarificationIntent,
    OpenQuestionIntent,
    StudyPlanIntent,
    StudyProgramRecommendationIntent,
)
from app.services.search_service import SearchResult


def _settings(**overrides):
    values = {
        "semantic_intent_enabled": True,
        "semantic_intent_min_confidence": 0.85,
        "semantic_intent_timeout": 10.0,
        "groq_api_key": "test-key",
        "groq_base_url": "https://api.groq.test/openai/v1",
        "groq_model": "openai/gpt-oss-120b",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _program_overview_plan(**overrides) -> SemanticQueryPlan:
    values = {
        "domain": "study_program",
        "operation": "overview",
        "program_mention": "Computer Science and Engineering",
        "specialization_mention": None,
        "course_number": None,
        "topic": None,
        "topics": [],
        "result_mode": "summary",
        "language": "en",
        "confidence": 0.97,
    }
    values.update(overrides)
    return SemanticQueryPlan(**values)


def test_semantic_classifier_returns_validated_query_plan():
    client = MagicMock()
    client.responses.parse.return_value.output_parsed = _program_overview_plan()

    with (
        patch("app.services.semantic_intent_service.get_settings", return_value=_settings()),
        patch("openai.OpenAI", return_value=client),
    ):
        plan = classify_query_semantically("computer science study guide")

    assert plan == _program_overview_plan()
    request = client.responses.parse.call_args.kwargs
    assert "computer science study guide" in request["input"]
    assert request["text_format"] is SemanticQueryPlan
    assert "study_program/overview" in request["instructions"]
    assert isinstance(intent_from_query_plan(plan), StudyPlanIntent)


def test_semantic_comparison_stays_in_open_question_mcp_flow(db_session):
    plan = SemanticQueryPlan(
        domain="specialization",
        operation="compare",
        program_mention=None,
        specialization_mention=None,
        course_number=None,
        topic=None,
        topics=[],
        result_mode="summary",
        language="da",
        confidence=1.0,
    )

    assert isinstance(intent_from_query_plan(plan), OpenQuestionIntent)

    prompts = [
        "Sammenlign computer science and engineering og wind energy",
        "Kan du sammenligne computer science and engineering og wind energy",
    ]

    with (
        patch(
            "app.services.recommendation_service.classify_query_semantically",
            return_value=plan,
        ),
        patch(
            "app.services.recommendation_service.answer_with_remote_mcp",
            return_value="Computer Science and Engineering og Wind Energy har forskellige faglige fokus.",
        ) as remote_answer,
    ):
        responses = [
            recommend_courses(
                db_session,
                messages=[prompt],
                academic_year="2026-2027",
            )
            for prompt in prompts
        ]

    assert remote_answer.call_args_list == [
        call(prompt, "2026-2027", response_language="da") for prompt in prompts
    ]
    assert all(response.understood.topic == "general question" for response in responses)
    assert all(response.response_language == "da" for response in responses)
    assert all(response.specializations == [] for response in responses)


def test_how_it_works_comparison_uses_semantic_operation_not_subject_keywords(db_session):
    """Programme names such as Applied Mathematics must not turn a comparison into course search."""
    prompt = "Compare Applied Mathematics and Computer Science and Engineering"
    plan = _program_overview_plan(
        operation="compare",
        program_mention=None,
        topics=[],
    )

    with (
        patch(
            "app.services.recommendation_service.classify_query_semantically",
            return_value=plan,
        ) as classifier,
        patch(
            "app.services.recommendation_service.answer_with_remote_mcp",
            return_value="The programmes have different structures and subject focus.",
        ) as remote_answer,
    ):
        response = recommend_courses(
            db_session,
            messages=[prompt],
            academic_year="2026-2027",
        )

    classifier.assert_called_once_with(prompt, conversation=prompt)
    remote_answer.assert_called_once_with(
        prompt,
        "2026-2027",
        response_language="en",
    )
    assert response.understood.topic == "general question"


def test_semantic_classifier_rejects_low_confidence_and_skips_without_key():
    client = MagicMock()
    client.responses.parse.return_value.output_parsed = _program_overview_plan(confidence=0.6)

    with (
        patch("app.services.semantic_intent_service.get_settings", return_value=_settings()),
        patch("openai.OpenAI", return_value=client),
    ):
        assert classify_query_semantically("computer science study guide") is None

    with (
        patch(
            "app.services.semantic_intent_service.get_settings",
            return_value=_settings(groq_api_key=""),
        ),
        patch("openai.OpenAI") as openai_client,
    ):
        assert classify_query_semantically("computer science study guide") is None

    openai_client.assert_not_called()


def test_semantic_programme_recommendation_and_clarification_map_to_dedicated_intents():
    recommendation_plan = _program_overview_plan(
        operation="recommend",
        topic="renewable energy",
    )
    clarification_plan = _program_overview_plan(
        domain="general",
        operation="clarify",
        topic="renewable energy",
    )

    recommendation_intent = intent_from_query_plan(recommendation_plan)
    clarification_intent = intent_from_query_plan(clarification_plan)

    assert isinstance(recommendation_intent, StudyProgramRecommendationIntent)
    assert recommendation_intent.topic == "renewable energy"
    assert isinstance(clarification_intent, ClarificationIntent)
    assert clarification_intent.topic == "renewable energy"


def test_semantic_greetings_and_capability_questions_stay_general_questions(db_session):
    greeting_plan = _program_overview_plan(
        domain="general",
        operation="overview",
        program_mention=None,
        topic=None,
        language="da",
    )

    assert isinstance(intent_from_query_plan(greeting_plan), OpenQuestionIntent)

    with (
        patch(
            "app.services.recommendation_service.classify_query_semantically",
            return_value=greeting_plan,
        ),
        patch(
            "app.services.recommendation_service.answer_with_remote_mcp",
            return_value="Hej! Jeg kan hjælpe med kurser og studieprogrammer.",
        ) as remote_answer,
    ):
        responses = [
            recommend_courses(
                db_session,
                messages=[prompt],
                academic_year="2026-2027",
            )
            for prompt in ("Hej", "Hej hvad kan du hjælpe med?")
        ]

    assert all(response.understood.topic == "general question" for response in responses)
    assert all(response.response_language == "da" for response in responses)
    assert remote_answer.call_count == 2


def test_semantic_clarification_without_topic_cannot_override_general_question():
    plan = _program_overview_plan(
        domain="general",
        operation="clarify",
        program_mention=None,
        topic=None,
    )

    assert isinstance(intent_from_query_plan(plan), OpenQuestionIntent)


def test_unnamed_programme_request_does_not_become_study_plan(db_session):
    plan = _program_overview_plan(
        operation="overview",
        program_mention=None,
        topic=None,
    )

    intent = intent_from_query_plan(plan)
    assert isinstance(intent, StudyProgramRecommendationIntent)
    assert intent.topic == ""

    with patch(
        "app.services.recommendation_service.classify_query_semantically",
        return_value=plan,
    ):
        response = recommend_courses(
            db_session,
            messages=["Programmes"],
            academic_year="2026-2027",
        )

    assert response.understood.topic == ""
    assert response.response_language == "en"
    assert response.reply.startswith("What subject interests you")
    assert "identify the programme" not in response.reply


def test_semantic_program_overview_is_database_backed_and_marks_specializations_optional(db_session):
    program = StudyProgram(
        slug="computer-science-and-engineering",
        name="Computer Science and Engineering",
        degree_type="Master",
        aliases=[],
        academic_year="2026-2027",
        source_url="https://student.dtu.dk/cse",
        content_hash="a" * 64,
        specializations=[
            StudySpecialization(
                slug="artificial-intelligence-and-algorithms",
                name="Artificial Intelligence and Algorithms",
                source_url="https://www.dtu.dk/cse/ai-algorithms",
                content_hash="b" * 64,
            ),
            StudySpecialization(
                slug="software-engineering",
                name="Software Engineering",
                source_url="https://www.dtu.dk/cse/software-engineering",
                content_hash="c" * 64,
            ),
        ],
    )
    db_session.add(program)
    db_session.commit()

    with (
        patch(
            "app.services.recommendation_service.classify_query_semantically",
            return_value=_program_overview_plan(),
        ),
        patch("app.services.recommendation_service.answer_with_remote_mcp") as remote_answer,
    ):
        response = recommend_courses(
            db_session,
            messages=["computer science study guide"],
            academic_year="2026-2027",
        )

    remote_answer.assert_not_called()
    assert response.understood.topic == "program overview"
    assert response.understood.program == "Computer Science and Engineering"
    assert "120 ECTS" in response.reply
    assert "optional specialization paths" in response.reply
    assert "not automatically mandatory" in response.reply
    assert "System Integration" not in response.reply
    assert [item.name for item in response.specializations] == [
        "Artificial Intelligence and Algorithms",
        "Software Engineering",
    ]
    assert all(item.is_optional for item in response.specializations)


def test_all_course_search_unions_topics_deduplicates_and_bypasses_mcp(db_session, sample_courses):
    plan = SemanticQueryPlan(
        domain="course",
        operation="search",
        program_mention=None,
        specialization_mention=None,
        course_number=None,
        topic="artificial intelligence and machine learning",
        topics=["artificial intelligence", "machine learning"],
        result_mode="all",
        language="en",
        confidence=1,
    )
    machine_learning_course = sample_courses[0]
    artificial_intelligence_course = sample_courses[1]

    def search_result(*_args, **kwargs):
        if kwargs["q"] == "artificial intelligence":
            return SearchResult(
                count=1,
                courses=[(artificial_intelligence_course, 0.8)],
                search_language="en",
            )
        return SearchResult(
            count=2,
            courses=[
                (machine_learning_course, 0.9),
                (artificial_intelligence_course, 0.4),
            ],
            search_language="en",
        )

    with (
        patch(
            "app.services.recommendation_service.classify_query_semantically",
            return_value=plan,
        ),
        patch(
            "app.services.recommendation_service.search_courses",
            side_effect=search_result,
        ) as course_search,
        patch("app.services.recommendation_service.answer_with_remote_mcp") as remote_answer,
    ):
        response = recommend_courses(
            db_session,
            messages=["Find all courses about artificial intelligence and machine learning"],
            academic_year="2026-2027",
        )

    remote_answer.assert_not_called()
    assert [call.kwargs["q"] for call in course_search.call_args_list] == [
        "artificial intelligence",
        "machine learning",
    ]
    assert all(call.kwargs["limit"] == 10_000 for call in course_search.call_args_list)
    assert all(call.kwargs["search_all_languages"] is True for call in course_search.call_args_list)
    assert [course.course_number for course in response.recommendations] == ["01418", "02450"]
    assert response.reply.startswith(
        "I found 2 unique courses for artificial intelligence and machine learning."
    )
    assert response.reply.index("01418") < response.reply.index("02450")
    assert response.reply.count("01418") == 1


def test_all_course_search_never_falls_back_to_five_when_semantic_planner_is_unavailable(
    db_session,
):
    courses = [
        Course(
            course_number=f"10{index:03d}",
            academic_year="2026-2027",
            ects=5,
            level="MSc",
            language="English",
            source_url=f"https://kurser.dtu.dk/course/2026-2027/10{index:03d}",
            content_hash=str(index) * 64,
            translations=[
                CourseTranslation(
                    language_code="en-GB",
                    title=f"Artificial Intelligence {index}",
                    description="Artificial intelligence methods.",
                )
            ],
        )
        for index in range(7)
    ]
    search_result = SearchResult(
        count=len(courses),
        courses=[(course, 1.0) for course in courses],
        search_language="en",
    )

    with (
        patch(
            "app.services.recommendation_service.classify_query_semantically",
            return_value=None,
        ),
        patch(
            "app.services.recommendation_service.search_courses",
            return_value=search_result,
        ) as course_search,
        patch("app.services.recommendation_service.answer_with_remote_mcp") as remote_answer,
    ):
        response = recommend_courses(
            db_session,
            messages=["Find all 5 ECTS courses about artificial intelligence at MSc level"],
            academic_year="2026-2027",
        )

    remote_answer.assert_not_called()
    assert len(response.recommendations) == 7
    assert course_search.call_args.kwargs["limit"] == 10_000
    assert course_search.call_args.kwargs["ects"] == 5
    assert course_search.call_args.kwargs["level"] == "MSc"


def test_completed_turn_facts_do_not_replay_old_request_as_an_instruction(db_session):
    old_request = "Give me courses in artificial intelligence"
    current_request = "Who teaches Artificial Intelligence and Multi-Agent Systems?"
    completed_turn = CompletedTurnState(
        request=old_request,
        operation="course_search",
        topic="artificial intelligence",
        courseNumbers=["02285"],
    )
    plan = SemanticQueryPlan(
        domain="course",
        operation="detail",
        program_mention=None,
        specialization_mention=None,
        course_number=None,
        topic="Artificial Intelligence and Multi-Agent Systems",
        topics=[],
        result_mode="single",
        language="en",
        confidence=1,
        referenced_turn_indexes=[],
    )

    with (
        patch(
            "app.services.recommendation_service.classify_query_semantically",
            return_value=plan,
        ) as classifier,
        patch(
            "app.services.recommendation_service.answer_with_remote_mcp",
            return_value="The course is taught by the listed course coordinators.",
        ) as remote_answer,
    ):
        response = recommend_courses(
            db_session,
            messages=[current_request],
            academic_year="2026-2027",
            completed_turns=[completed_turn],
        )

    classifier_context = classifier.call_args.kwargs["conversation"]
    model_input = remote_answer.call_args.args[0]
    assert old_request not in classifier_context
    assert old_request not in model_input
    assert '"operation":"course_search"' in classifier_context
    assert '"topic":"artificial intelligence"' in classifier_context
    assert model_input.startswith(
        "Current user request (answer this request only):\n" + current_request
    )
    assert response.recommendations == []
    assert response.understood.topic == "general question"
