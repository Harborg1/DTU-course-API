import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.models.course import Course, CourseTranslation
from app.services.course_qa_service import CourseQAError, _detect_language, answer_course_question
from app.services.recommendation_service import _extract_course_number, recommend_courses

os.environ["GROQ_API_KEY"] = "test-groq-key"
get_settings.cache_clear()


def test_detects_danish_from_real_question():
    assert _detect_language("Jeg vil gerne vide hvem der underviser i kurset 02421") == "da"


def test_detects_english_from_real_question():
    assert _detect_language("Who teaches course 02421?") == "en"


def test_fallback_to_english_on_detection_error():
    result = _detect_language("")
    assert result == "en"


def test_fallback_to_english_for_unknown_language():
    assert _detect_language("¿Quién enseña?") == "en"


def test_extract_course_number_from_question():
    result = _extract_course_number("hvad er skemagruppen for 02285?")
    assert result == "02285"


def test_extract_course_number_from_danish_question():
    result = _extract_course_number("hvornår er eksamen for 02450?")
    assert result == "02450"


def test_no_course_number_returns_none():
    result = _extract_course_number("hvad kan du fortælle om machine learning?")
    assert result is None


def test_course_number_in_middle_of_text():
    result = _extract_course_number("jeg vil gerne vide noget om 02450 og machine learning")
    assert result == "02450"


def test_answer_course_question_returns_string():
    course = Course(
        course_number="02450",
        academic_year="2026-2027",
        ects=5,
        level="MSc",
        schedule="E2A",
        exam="oral exam",
        language="English",
        source_url="https://kurser.dtu.dk/course/2026-2027/02450",
        content_hash="a" * 64,
        imported_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        translations=[
            CourseTranslation(language_code="en-GB", title="Introduction to Machine Learning")
        ],
    )

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Skemagruppen er E2A."))]

    with patch("openai.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = mock_response

        result = answer_course_question(course, "Hvad er skemagruppen?")

    assert result == "Skemagruppen er E2A."
    MockClient.assert_called_once()
    call_args = MockClient.call_args
    assert call_args.kwargs["api_key"] == "test-groq-key"
    assert call_args.kwargs["timeout"] == 20.0
    assert call_args.kwargs["max_retries"] == 1


def test_answer_course_question_without_api_key():
    os.environ["GROQ_API_KEY"] = ""
    get_settings.cache_clear()

    course = Course(
        course_number="02450",
        academic_year="2026-2027",
        ects=5,
        level="MSc",
        schedule="E2A",
        exam="oral exam",
        language="English",
        source_url="https://kurser.dtu.dk/course/2026-2027/02450",
        content_hash="a" * 64,
        imported_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        translations=[
            CourseTranslation(language_code="en-GB", title="Introduction to Machine Learning")
        ],
    )

    with pytest.raises(CourseQAError, match="GROQ_API_KEY"):
        answer_course_question(course, "Hvad er skemagruppen?")

    os.environ["GROQ_API_KEY"] = "test-groq-key"
    get_settings.cache_clear()


def test_course_question_triggers_llm(client, sample_courses):
    with patch(
        "app.services.recommendation_service.answer_with_remote_mcp",
        return_value="Skemagruppen for 02450 er E2A.",
    ) as answer:
        response = client.post(
            "/api/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "hvad er skemagruppen for 02450?",
                    }
                ]
            },
        )

    answer.assert_called_once_with("hvad er skemagruppen for 02450?", "2026-2027")

    assert response.status_code == 200
    body = response.json()
    assert body["isDirectAnswer"] is True
    assert body["reply"] == "Skemagruppen for 02450 er E2A."
    assert body["understood"]["topic"] == "course 02450"
    assert body["recommendations"] == []


def test_course_question_nonexistent_course(client, sample_courses):
    response = client.post(
        "/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "hvad er skemagruppen for 99999?",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["isDirectAnswer"] is False
    assert body["recommendations"] == []
    assert "ikke finde" in body["reply"] or "kunne ikke" in body["reply"]


def test_recommend_courses_with_course_number_uses_llm(db_session, sample_courses):
    with patch(
        "app.services.recommendation_service.answer_with_remote_mcp",
        return_value="Eksamen er mundtlig.",
    ) as answer:
        result = recommend_courses(
            db_session,
            messages=["hvad er eksamen for 02450?"],
            academic_year="2026-2027",
        )

    answer.assert_called_once_with("hvad er eksamen for 02450?", "2026-2027")

    assert result.is_direct_answer is True
    assert result.reply == "Eksamen er mundtlig."
    assert result.understood.topic == "course 02450"


def test_recommend_courses_without_llm_key_returns_clear_unavailable_answer(db_session, sample_courses):
    os.environ["GROQ_API_KEY"] = ""
    get_settings.cache_clear()

    try:
        result = recommend_courses(
            db_session,
            messages=["hvad er skemagruppen for 02450?"],
            academic_year="2026-2027",
        )
    finally:
        os.environ["GROQ_API_KEY"] = "test-groq-key"
        get_settings.cache_clear()

    assert result.is_direct_answer is True
    assert result.understood.topic == "course 02450"
    assert "AI-svaret kunne ikke hentes" in result.reply
