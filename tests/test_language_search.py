from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from app.mcp_server.server import _SEARCH_COURSES_SCHEMA, _handle_search_courses
from app.models.course import Course, CourseTranslation
from app.services.course_qa_service import _build_system_prompt
from app.services.search_service import search_courses


def _bilingual_course() -> Course:
    now = datetime.now(UTC)
    return Course(
        course_number="02452",
        academic_year="2026-2027",
        source_url="https://kurser.dtu.dk/course/2026-2027/02452",
        content_hash="a" * 64,
        imported_at=now,
        updated_at=now,
        translations=[
            CourseTranslation(
                language_code="da-DK", title="Machine learning",
                description="Datamodellering med beslutningstræer",
                content="Klassifikation og tæthedsestimering",
            ),
            CourseTranslation(
                language_code="en-GB", title="Machine Learning",
                description="Data modelling with decision trees",
                content="Classification and density estimation",
            ),
        ],
    )


def test_search_service_keeps_danish_and_english_text_separate(db_session):
    db_session.add(_bilingual_course())
    db_session.commit()

    danish = search_courses(
        db_session,
        q="beslutningstræer",
        academic_year="2026-2027",
        search_language="da",
    )
    wrong_language = search_courses(
        db_session,
        q="beslutningstræer",
        academic_year="2026-2027",
        search_language="en",
    )
    english = search_courses(
        db_session,
        q="decision trees",
        academic_year="2026-2027",
        search_language="en",
    )

    assert [course.course_number for course, _ in danish.courses] == ["02452"]
    assert wrong_language.count == 0
    assert [course.course_number for course, _ in english.courses] == ["02452"]


def test_mcp_search_requires_and_returns_search_language(db_session):
    db_session.add(_bilingual_course())
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    with patch("app.database.SessionLocal", factory):
        result = _handle_search_courses(
            {
                "q": "beslutningstræer",
                "academic_year": "2026-2027",
                "search_language": "da",
            }
        )

    assert "search_language" in _SEARCH_COURSES_SCHEMA["required"]
    assert result["search_language"] == "da"
    assert result["courses"][0]["title"] == "Machine learning"
    assert result["courses"][0]["description"] == "Datamodellering med beslutningstræer"


def test_chat_prompt_passes_detected_language_to_mcp_tools():
    prompt = _build_system_prompt("da", "2026-2027")

    assert "search_language være 'da'" in prompt
    assert "response_language være 'da'" in prompt


def test_chat_prompt_formats_course_results_as_multiline_bullet_lists():
    prompt = _build_system_prompt("en", "2026-2027")

    assert "Never format course results as Markdown tables." in prompt
    assert "Present courses as a readable bullet list." in prompt
    assert "course number and title on the first line" in prompt
    assert "ECTS and level on the following line" in prompt
    assert "Do not place multiple courses on the same line." in prompt
    assert "sort every course list by course number in ascending order" in prompt
