from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from app.mcp_server.server import _SEARCH_COURSES_SCHEMA, _handle_search_courses
from app.models.course import Course, CourseTranslation
from app.services.course_qa_service import _build_system_prompt
from app.services.language_service import (
    detect_explicit_user_language,
    detect_user_language,
    resolve_response_language,
)
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


def _quantum_course() -> Course:
    now = datetime.now(UTC)
    return Course(
        course_number="02195",
        academic_year="2026-2027",
        source_url="https://kurser.dtu.dk/course/2026-2027/02195",
        content_hash="b" * 64,
        imported_at=now,
        updated_at=now,
        translations=[
            CourseTranslation(
                language_code="da-DK",
                title="Kvantealgoritmer og maskinlæring",
                description="Kvanteberegning og lineær algebra",
            ),
            CourseTranslation(
                language_code="en-GB",
                title="Quantum Algorithms and Machine Learning",
                description="Quantum computing and linear algebra",
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


def test_bilingual_search_returns_same_course_ids_for_both_presentation_languages(db_session):
    db_session.add_all([_bilingual_course(), _quantum_course()])
    db_session.commit()

    danish = search_courses(
        db_session,
        q="quantum",
        academic_year="2026-2027",
        search_language="da",
        search_all_languages=True,
    )
    english = search_courses(
        db_session,
        q="quantum",
        academic_year="2026-2027",
        search_language="en",
        search_all_languages=True,
    )

    assert danish.count == english.count == 1
    assert [course.course_number for course, _ in danish.courses] == ["02195"]
    assert [course.course_number for course, _ in english.courses] == ["02195"]
    assert danish.courses[0][0].title_da == "Kvantealgoritmer og maskinlæring"
    assert english.courses[0][0].title_en == "Quantum Algorithms and Machine Learning"


def test_bilingual_search_deduplicates_courses_matching_both_translations(db_session):
    db_session.add(_bilingual_course())
    db_session.commit()

    result = search_courses(
        db_session,
        q="machine learning",
        academic_year="2026-2027",
        search_language="en",
        search_all_languages=True,
    )

    assert result.count == 1
    assert [course.course_number for course, _ in result.courses] == ["02452"]


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
    assert "q være et kort, kanonisk engelsk emne" in prompt


def test_chat_prompt_formats_course_results_as_multiline_bullet_lists():
    prompt = _build_system_prompt("en", "2026-2027")

    assert "Never format course results as Markdown tables." in prompt
    assert "Present courses as a readable bullet list." in prompt
    assert "course number and title on the first line" in prompt
    assert "ECTS and level on the following line" in prompt
    assert "Do not place multiple courses on the same line." in prompt
    assert "sort every course list by course number in ascending order" in prompt


def test_response_language_follows_study_guide_wording():
    assert detect_user_language("Computer Science and Engineering study plan") == "en"
    assert detect_user_language("Computer Science and Engineering studieplan") == "da"
    assert detect_user_language("Computer Science and Engineering specialities") == "en"
    assert detect_user_language("Computer Science and Engineering specialiseringer") == "da"


def test_short_greetings_and_programme_choices_have_stable_languages():
    assert detect_user_language("Hej") == "da"
    assert detect_user_language("HEJ") == "da"
    assert detect_user_language("Hello") == "en"
    assert detect_user_language("HELLO") == "en"
    assert detect_user_language("Programmes") == "en"
    assert detect_user_language("programmes") == "en"


def test_short_danish_follow_ups_are_detected_as_danish():
    assert detect_user_language("ja") == "da"
    assert detect_user_language("kan du uddybe?") == "da"
    assert detect_user_language("computer science studieguide") == "da"


def test_language_neutral_messages_do_not_force_an_english_switch():
    assert detect_explicit_user_language("02402") is None
    assert detect_explicit_user_language("MSc") is None
    assert resolve_response_language("02402", previous_languages=["da"]) == "da"
    assert resolve_response_language("MSc", previous_messages=["Hvilke kurser kan du anbefale?"]) == "da"


def test_explicit_language_change_wins_over_conversation_history():
    assert resolve_response_language("Please answer in English", previous_languages=["da"]) == "en"


def test_semantic_language_is_used_when_message_and_history_are_neutral():
    assert resolve_response_language("DTU", inferred_language="da") == "da"
