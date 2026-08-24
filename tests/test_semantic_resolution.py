from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.specialization import SpecializationRequirement, StudySpecialization
from app.models.study_plan import StudyProgram
from app.services.recommendation_service import recommend_courses
from app.services.semantic_resolver import SemanticCandidate, SemanticMatch, resolve_semantic_candidate


def _settings(**overrides):
    values = {
        "semantic_resolution_enabled": True,
        "semantic_resolution_min_confidence": 0.85,
        "semantic_resolution_timeout": 10.0,
        "groq_api_key": "test-key",
        "groq_base_url": "https://api.groq.test/openai/v1",
        "groq_model": "openai/gpt-oss-120b",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_semantic_resolver_returns_only_valid_high_confidence_candidate():
    client = MagicMock()
    client.responses.parse.return_value.output_parsed = SemanticMatch(
        candidate_id="cse",
        confidence=0.97,
    )

    with (
        patch("app.services.semantic_resolver.get_settings", return_value=_settings()),
        patch("openai.OpenAI", return_value=client),
    ):
        result = resolve_semantic_candidate(
            "comp sci and eng",
            [
                SemanticCandidate("cse", "Computer Science and Engineering", ("computer science",)),
                SemanticCandidate("bio", "Biotechnology"),
            ],
            entity_type="DTU study programme",
        )

    assert result == "cse"
    request = client.responses.parse.call_args.kwargs
    assert "comp sci and eng" in request["input"]
    assert "id=cse" in request["input"]
    assert request["text_format"] is SemanticMatch


def test_semantic_resolver_rejects_low_confidence_or_unknown_candidate():
    client = MagicMock()
    candidates = [SemanticCandidate("cse", "Computer Science and Engineering")]

    with (
        patch("app.services.semantic_resolver.get_settings", return_value=_settings()),
        patch("openai.OpenAI", return_value=client),
    ):
        client.responses.parse.return_value.output_parsed = SemanticMatch(
            candidate_id="cse",
            confidence=0.6,
        )
        assert resolve_semantic_candidate("computer", candidates, entity_type="programme") is None

        client.responses.parse.return_value.output_parsed = SemanticMatch(
            candidate_id="invented",
            confidence=1,
        )
        assert resolve_semantic_candidate("invented", candidates, entity_type="programme") is None


def test_semantic_resolver_is_optional_and_skips_network_without_api_key():
    with (
        patch(
            "app.services.semantic_resolver.get_settings",
            return_value=_settings(groq_api_key=""),
        ),
        patch("openai.OpenAI") as openai_client,
    ):
        result = resolve_semantic_candidate(
            "comp sci",
            [SemanticCandidate("cse", "Computer Science and Engineering")],
            entity_type="programme",
        )

    assert result is None
    openai_client.assert_not_called()


def test_chat_semantically_resolves_abbreviated_program_name(db_session):
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
                slug="machine-learning",
                name="Machine Learning",
                source_url="https://www.dtu.dk/cse/machine-learning",
                content_hash="b" * 64,
            )
        ],
    )
    db_session.add(program)
    db_session.commit()

    with patch(
        "app.services.recommendation_service.resolve_semantic_candidate",
        return_value=str(program.id),
    ) as resolver:
        response = recommend_courses(
            db_session,
            messages=["Hvilke specialiseringer har comp sci and eng?"],
            academic_year="2026-2027",
        )

    assert response.understood.program == "Computer Science and Engineering"
    assert [item.name for item in response.specializations] == ["Machine Learning"]
    assert resolver.call_count == 1
    assert resolver.call_args.kwargs["entity_type"] == "DTU study programme"


def test_chat_semantically_resolves_specialization_within_program(db_session):
    specialization = StudySpecialization(
        slug="artificial-intelligence-and-algorithms",
        name="Artificial Intelligence and Algorithms",
        source_url="https://www.dtu.dk/cse/ai-algorithms",
        content_hash="c" * 64,
        requirements=[
            SpecializationRequirement(
                requirement_type="min_ects",
                description="Choose at least 25 ECTS.",
                required_ects=25,
                position=0,
            )
        ],
    )
    program = StudyProgram(
        slug="computer-science-and-engineering",
        name="Computer Science and Engineering",
        degree_type="Master",
        aliases=["CSE"],
        academic_year="2026-2027",
        source_url="https://student.dtu.dk/cse",
        content_hash="d" * 64,
        specializations=[specialization],
    )
    db_session.add(program)
    db_session.commit()

    with patch(
        "app.services.recommendation_service.resolve_semantic_candidate",
        return_value=str(specialization.id),
    ) as resolver:
        response = recommend_courses(
            db_session,
            messages=["Hvor mange ECTS kræver intelligent algorithms-specialiseringen på CSE?"],
            academic_year="2026-2027",
        )

    assert response.specializations[0].name == "Artificial Intelligence and Algorithms"
    assert response.specializations[0].requirements[0].required_ects == 25
    assert "mindst 25 ECTS" in response.reply
    assert resolver.call_count == 1
    assert resolver.call_args.kwargs["entity_type"] == "DTU study specialization"
