from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.specialization import StudySpecialization
from app.models.study_plan import StudyProgram
from app.services.recommendation_service import recommend_courses
from app.services.semantic_intent_service import (
    SemanticQueryPlan,
    classify_query_semantically,
    intent_from_query_plan,
)
from app.services.intent_service import StudyPlanIntent
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
    assert [course.course_number for course in response.recommendations] == ["01418", "02450"]
    assert response.reply.startswith(
        "I found 2 unique courses for artificial intelligence and machine learning."
    )
    assert response.reply.index("01418") < response.reply.index("02450")
    assert response.reply.count("01418") == 1
