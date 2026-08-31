from unittest.mock import patch

from app.models.study_plan import StudyProgram
from app.services.recommendation_service import recommend_courses


def _program(slug: str, name: str, degree_type: str, introduction: str) -> StudyProgram:
    return StudyProgram(
        slug=slug,
        name=name,
        degree_type=degree_type,
        aliases=[],
        academic_year="2026-2027",
        introduction=introduction,
        source_url=f"https://www.dtu.dk/english/education/{slug}",
        content_hash=slug[0] * 64,
    )


def test_recommends_imported_programmes_instead_of_courses(db_session):
    db_session.add_all(
        [
            _program(
                "applied-mathematics",
                "Applied Mathematics",
                "Bachelor",
                "A bachelor programme focused on mathematics and mathematical modelling.",
            ),
            _program(
                "mathematical-modelling-and-computation",
                "Mathematical Modelling and Computation",
                "Master",
                "An MSc programme in mathematical modelling, computation, and data analysis.",
            ),
            _program(
                "biotechnology",
                "Biotechnology",
                "Master",
                "An MSc programme about cells, bioprocesses, and biological production.",
            ),
        ]
    )
    db_session.commit()

    with patch("app.services.recommendation_service.answer_with_remote_mcp") as remote_answer:
        response = recommend_courses(
            db_session,
            messages=["Jeg kan godt lide matematik. Hvilke studier kan du anbefale?"],
            academic_year="2026-2027",
        )

    remote_answer.assert_not_called()
    assert response.understood.topic == "matematik"
    assert response.recommendations == []
    assert [program.name for program in response.study_programs] == [
        "Applied Mathematics",
        "Mathematical Modelling and Computation",
    ]
    assert all(program.source_url.startswith("https://www.dtu.dk/") for program in response.study_programs)
    assert "studieprogrammer" in response.reply
    assert response.response_language == "da"


def test_ambiguous_interest_asks_courses_or_programmes_without_calling_model(db_session):
    with patch("app.services.recommendation_service.answer_with_remote_mcp") as remote_answer:
        response = recommend_courses(
            db_session,
            messages=["Jeg kan godt lide matematik"],
            academic_year="2026-2027",
        )

    remote_answer.assert_not_called()
    assert "studieprogrammer eller kurser" in response.reply
    assert "‘studier’ eller ‘kurser’" in response.reply
    assert response.study_programs == []
    assert response.recommendations == []
    assert response.understood.topic == "matematik"


def test_standalone_programme_choice_without_previous_topic_does_not_repeat_clarification(db_session):
    with patch("app.services.recommendation_service.answer_with_remote_mcp") as remote_answer:
        response = recommend_courses(
            db_session,
            messages=["Kan du anbefale noget?", "studier"],
            academic_year="2026-2027",
        )

    remote_answer.assert_not_called()
    assert response.reply == (
        "Hvilket emne interesserer dig, og leder du efter en bachelor- eller kandidatuddannelse?"
    )
    assert "studieprogrammer eller kurser" not in response.reply
    assert response.understood.topic == ""


def test_programme_follow_up_reuses_topic_from_previous_user_message(db_session):
    db_session.add(
        _program(
            "mathematical-modelling-and-computation",
            "Mathematical Modelling and Computation",
            "Master",
            "An MSc programme in mathematical modelling and computation.",
        )
    )
    db_session.commit()

    response = recommend_courses(
        db_session,
        messages=["Jeg kan godt lide matematik", "Studier"],
        academic_year="2026-2027",
    )

    assert response.understood.topic == "matematik"
    assert [program.name for program in response.study_programs] == [
        "Mathematical Modelling and Computation"
    ]


def test_course_follow_up_reuses_topic_and_keeps_course_flow(db_session):
    with patch(
        "app.services.recommendation_service.answer_with_remote_mcp",
        return_value="Jeg fandt relevante matematikkurser.",
    ) as remote_answer:
        response = recommend_courses(
            db_session,
            messages=["Jeg kan godt lide matematik", "Kurser"],
            academic_year="2026-2027",
        )

    remote_answer.assert_called_once_with(
        "Jeg kan godt lide matematik Kurser",
        "2026-2027",
        response_language="da",
    )
    assert response.understood.topic == "matematik"
    assert response.study_programs == []
    assert response.recommendations == []


def test_programme_recommendations_serialize_with_separate_response_field(db_session):
    db_session.add(
        _program(
            "engineering-physics",
            "Engineering Physics",
            "Master",
            "Advanced physics, mathematical methods, and engineering applications.",
        )
    )
    db_session.commit()

    response = recommend_courses(
        db_session,
        messages=["Recommend study programmes if I like physics"],
        academic_year="2026-2027",
    )
    payload = response.model_dump(by_alias=True)

    assert payload["recommendations"] == []
    assert payload["studyPrograms"][0]["name"] == "Engineering Physics"
    assert payload["studyPrograms"][0]["degreeType"] == "Master"
