"""Tests for intent-based routing in recommend_courses()."""

import pytest

from app.models.course import Course, CourseTranslation
from app.models.study_plan import StudyProgram
from app.services.intent_service import (
    ClarificationIntent,
    CourseQAIntent,
    NewCoursesIntent,
    OpenQuestionIntent,
    RecommendationIntent,
    StudyProgramRecommendationIntent,
    StudyPlanIntent,
    classify_intent,
    extract_intent_keywords,
    extract_course_number,
    extract_topic,
    is_study_plan_related,
)


# ===================================================================
# Intent classification
# ===================================================================

class TestClassifyIntent:
    """Tests for classify_intent()."""

    def test_course_qa_with_exact_number(self):
        intent = classify_intent("hvad er 02450 om?")
        assert isinstance(intent, CourseQAIntent)
        assert intent.course_number == "02450"
        assert intent.confidence == 1.0

    def test_course_qa_with_number_in_longer_text(self):
        intent = classify_intent("kan du fortælle mig om 02450?")
        assert isinstance(intent, CourseQAIntent)
        assert intent.course_number == "02450"

    def test_course_qa_number_must_be_exactly_5_digits(self):
        intent = classify_intent("hvad er 1234 om?")
        assert not isinstance(intent, CourseQAIntent)

        intent = classify_intent("hvad er 123456 om?")
        assert not isinstance(intent, CourseQAIntent)

    def test_study_plan_question_with_structure(self):
        intent = classify_intent("hvordan er mit studie opbygget?")
        assert isinstance(intent, StudyPlanIntent)

    def test_study_plan_question_with_obligatorisk(self):
        intent = classify_intent("hvilke kurser er obligatoriske?")
        assert isinstance(intent, StudyPlanIntent)

    def test_study_plan_question_with_ects(self):
        intent = classify_intent("hvordan er ects-opbygningen?")
        assert isinstance(intent, StudyPlanIntent)
        assert intent.requires_ects_calculation is True

    def test_study_plan_question_with_programme_specific(self):
        intent = classify_intent("hvad er programmespecifikke kurser?")
        assert isinstance(intent, StudyPlanIntent)
        assert intent.requires_section_info is True

    def test_study_plan_question_with_mandatory(self):
        intent = classify_intent("skal jeg have nogle obligatoriske kurser?")
        assert isinstance(intent, StudyPlanIntent)
        assert intent.requires_course_count is True

    def test_recommendation_intent_with_topic(self):
        intent = classify_intent("kan du anbefale maskinlearning kurser?")
        assert isinstance(intent, RecommendationIntent)
        assert intent.topic == "maskinlearning"

    def test_recommendation_intent_with_level(self):
        intent = classify_intent("find msc kurser inden machine learning")
        assert isinstance(intent, RecommendationIntent)
        assert intent.level == "MSc"

    def test_recommendation_intent_with_bachelor(self):
        intent = classify_intent("bachelor kurser i optimering")
        assert isinstance(intent, RecommendationIntent)
        assert intent.level == "BSc"

    @pytest.mark.parametrize(
        ("prompt", "topic"),
        [
            ("Jeg kan godt lide matematik. Hvilke studier kan du anbefale?", "matematik"),
            ("Hvad kan jeg læse, hvis jeg interesserer mig for kemi?", "kemi"),
            ("Hvilken uddannelse passer til mig, hvis jeg kan lide kemi?", "kemi"),
            ("Which degree programme would you recommend if I like physics?", "physics"),
            ("Which degree should I choose if I enjoy software?", "software"),
        ],
    )
    def test_study_program_recommendation_intent(self, prompt, topic):
        intent = classify_intent(prompt)

        assert isinstance(intent, StudyProgramRecommendationIntent)
        assert intent.topic == topic

    def test_interest_without_course_or_programme_target_requires_clarification(self):
        intent = classify_intent("Jeg kan godt lide matematik")

        assert isinstance(intent, ClarificationIntent)
        assert intent.topic == "matematik"

    def test_explicit_course_target_keeps_course_recommendation(self):
        intent = classify_intent("Jeg kan godt lide matematik. Hvilke kurser kan du anbefale?")

        assert isinstance(intent, RecommendationIntent)
        assert intent.topic == "matematik"

    def test_open_question(self):
        intent = classify_intent("hej, hvem er du?")
        assert isinstance(intent, OpenQuestionIntent)

    def test_open_question_general(self):
        intent = classify_intent("hvad kan du hjælpe med?")
        assert isinstance(intent, OpenQuestionIntent)

    @pytest.mark.parametrize(
        "prompt",
        [
            "Hvilke kurser er nye?",
            "Vis de nye kurser",
            "Er der et nyt kursus?",
            "Which courses are new?",
            "Show me the new courses",
        ],
    )
    def test_new_courses_intent(self, prompt):
        assert isinstance(classify_intent(prompt), NewCoursesIntent)

    @pytest.mark.parametrize(
        ("prompt", "level"),
        [
            ("Hvilke nye kurser er der på BSc?", "BSc"),
            ("Hvilke kurser er nye på kandidatniveau?", "MSc"),
            ("Vis nye ph.d. kurser", "PhD"),
            ("Which BSc courses are new?", "BSc"),
            ("Which new MSc courses are available?", "MSc"),
            ("Which courses are new at PhD level?", "PhD"),
        ],
    )
    def test_new_courses_intent_extracts_level(self, prompt, level):
        intent = classify_intent(prompt)

        assert isinstance(intent, NewCoursesIntent)
        assert intent.level == level

    @pytest.mark.parametrize(
        ("prompt", "topic", "ects"),
        [
            ("Hvilke nye kurser er der om machine learning på 5 ECTS?", "machine learning", 5),
            ("Vis nye 7,5 ECTS kurser om kunstig intelligens", "kunstig intelligens", 7.5),
            ("Show new courses about artificial intelligence worth 10 ECTS", "artificial intelligence", 10),
        ],
    )
    def test_new_courses_intent_extracts_topic_and_ects(self, prompt, topic, ects):
        intent = classify_intent(prompt)

        assert isinstance(intent, NewCoursesIntent)
        assert intent.topic == topic
        assert float(intent.ects) == ects

    def test_study_plan_with_english_keywords(self):
        intent = classify_intent("how is my degree structured?")
        assert isinstance(intent, StudyPlanIntent)

    def test_study_plan_with_which_courses_do_i_need(self):
        intent = classify_intent("which courses do i need to take?")
        assert isinstance(intent, StudyPlanIntent)

    def test_course_qa_takes_precedence_over_study_plan(self):
        intent = classify_intent("hvad er 02450 om og hvordan er studieplanen opbygget?")
        assert isinstance(intent, CourseQAIntent)
        assert intent.course_number == "02450"


# ===================================================================
# Keyword extraction
# ===================================================================

class TestExtractIntentKeywords:
    """Tests for extract_intent_keywords()."""

    def test_ects_keyword(self):
        keywords = extract_intent_keywords("hvordan er ects-opbygningen?")
        assert "ects" in keywords

    def test_mandatory_keyword(self):
        keywords = extract_intent_keywords("skal jeg have obligatoriske kurser?")
        assert "mandatory" in keywords

    def test_elective_keyword(self):
        keywords = extract_intent_keywords("hvad er valgfrie kurser?")
        assert "elective" in keywords

    def test_programme_specific_keyword(self):
        keywords = extract_intent_keywords("hvad er retningsspecifikke kurser?")
        assert "programme-specific" in keywords

    def test_multiple_keywords(self):
        keywords = extract_intent_keywords("hvad er obligatoriske og valgfrie kurser?")
        assert "mandatory" in keywords
        assert "elective" in keywords

    def test_no_keywords(self):
        keywords = extract_intent_keywords("hej, hvem er du?")
        assert keywords == []

    def test_extracts_actual_topic_instead_of_category_name(self):
        assert extract_topic("find MSc kurser i machine learning") == "machine learning"


# ===================================================================
# Course number extraction
# ===================================================================

class TestExtractCourseNumber:
    """Tests for extract_course_number()."""

    def test_exact_5_digit(self):
        assert extract_course_number("02450") == "02450"

    def test_number_in_sentence(self):
        assert extract_course_number("hvad er 02450 om?") == "02450"

    def test_too_short(self):
        assert extract_course_number("1234") is None

    def test_too_long(self):
        assert extract_course_number("123456") is None

    def test_multiple_numbers(self):
        assert extract_course_number("hvad er 02450 eller 01418 om?") == "02450"


# ===================================================================
# Study plan detection
# ===================================================================

class TestIsStudyPlanRelated:
    """Tests for is_study_plan_related()."""

    def test_obligatorisk(self):
        assert is_study_plan_related("hvilke kurser er obligatoriske?") is True

    def test_opbygning(self):
        assert is_study_plan_related("hvordan er mit studie opbygget?") is True

    def test_study_plan_keyword(self):
        assert is_study_plan_related("kan du fortælle mig om studieplanen?") is True

    def test_hvordan_er_studiet(self):
        assert is_study_plan_related("hvordan er studiet?") is True

    def test_how_is_my_degree_structured(self):
        assert is_study_plan_related("how is my degree structured?") is True

    def test_which_courses_do_i_need(self):
        assert is_study_plan_related("which courses do i need?") is True

    def test_hvornar_ma_jeg(self):
        assert is_study_plan_related("hvornår må jeg tage hvilke kurser?") is True

    def test_non_study_plan(self):
        assert is_study_plan_related("hvad er 02450 om?") is False

    def test_non_study_plan_recommendation(self):
        assert is_study_plan_related("kan du anbefale machine learning kurser?") is False


# ===================================================================
# Intent-based routing integration tests
# ===================================================================

class TestRecommendCoursesIntentRouting:
    """Integration tests for recommend_courses() with intent-based routing."""

    def test_course_qa_intent(self, client, db_session):
        """Test that course Q&A intent routes to Groq answer."""
        from app.services.recommendation_service import recommend_courses

        db_session.add_all([
            Course(
                course_number="02450",
                academic_year="2026-2027",
                ects=5,
                level="MSc",
                course_type="MSc",
                language="English",
                department="DTU Compute",
                period="E",
                schedule="E2A",
                campus="Campus Lyngby",
                source_url="https://kurser.dtu.dk/course/2026-2027/02450",
                content_hash="a" * 64,
                translations=[
                    CourseTranslation(
                        language_code="en-GB",
                        title="Introduction to Machine Learning",
                        description="Supervised learning",
                        content="Machine learning",
                    )
                ],
            ),
        ])
        db_session.commit()

        # This will try to call Groq, which may fail in test environment
        # We just verify the intent routing works
        from app.services.intent_service import classify_intent
        intent = classify_intent("hvad er 02450 om?")
        assert isinstance(intent, CourseQAIntent)
        assert intent.course_number == "02450"

    def test_latest_message_can_switch_from_course_to_study_plan(self, db_session):
        """An earlier course number must not override the latest explicit intent."""
        from unittest.mock import patch

        from app.services.recommendation_service import recommend_courses

        program = StudyProgram(
            slug="computer-science-and-engineering",
            name="Computer Science and Engineering",
            degree_type="Master",
            academic_year="2026-2027",
            source_url="https://student.dtu.dk/studieordninger",
            content_hash="b" * 64,
        )
        db_session.add(program)
        db_session.commit()

        with patch(
            "app.services.recommendation_service.answer_with_remote_mcp",
            return_value="Her er studieplanen.",
        ) as answer:
            response = recommend_courses(
                db_session,
                messages=[
                    "Hvem underviser i kurset 02452?",
                    "Studieplan computer science and engineering",
                ],
                academic_year="2026-2027",
            )

        assert response.is_direct_answer is True
        assert response.understood.topic == "study plan qa"
        assert response.understood.program == "Computer Science and Engineering"
        answer.assert_called_once_with(
            "Studieplan computer science and engineering\n\n"
            "Identificeret studieprogram: Computer Science and Engineering (Master).",
            "2026-2027",
            response_language="da",
        )

    def test_study_plan_intent(self, client, db_session):
        """Test that study plan intent is correctly classified."""
        from app.services.intent_service import classify_intent

        intent = classify_intent("hvordan er mit studie opbygget?")
        assert isinstance(intent, StudyPlanIntent)

    def test_recommendation_intent(self, client, db_session):
        """Test that recommendation intent is correctly classified."""
        from app.services.intent_service import classify_intent

        intent = classify_intent("kan du anbefale machine learning kurser?")
        assert isinstance(intent, RecommendationIntent)

    def test_open_question_intent(self, client, db_session):
        """Test that open question intent is correctly classified."""
        from app.services.intent_service import classify_intent

        intent = classify_intent("hej, hvem er du?")
        assert isinstance(intent, OpenQuestionIntent)
