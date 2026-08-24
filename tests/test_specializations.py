from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models.specialization import SpecializationCourse, StudySpecialization
from app.models.study_plan import StudyProgram
from app.services.intent_service import SpecializationIntent, classify_intent
from app.services.recommendation_service import recommend_courses
from importer.specialization_importer import upsert_specialization
from importer.specialization_parser import parse_specialization_page
from importer.study_plan_importer import upsert_study_plan
from importer.study_plan_parser import StudyProgramData


FIXTURES = Path(__file__).parent / "fixtures"
CSE_URL = (
    "https://www.dtu.dk/english/education/graduate/msc-programmes/"
    "computer-science-and-engineering/specialization/artificial-intelligence-and-algorithms"
)
WIND_URL = (
    "https://www.dtu.dk/english/education/graduate/msc-programmes/"
    "wind-energy/specialization/offshore-wind-energy"
)
TECH_URL = (
    "https://www.dtu.dk/english/education/graduate/msc-programmes/"
    "technology-entrepreneurship/specialization"
)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _program(slug: str, name: str) -> StudyProgram:
    return StudyProgram(
        slug=slug,
        name=name,
        degree_type="Master",
        aliases=[name],
        academic_year="2026-2027",
        source_url=f"https://www.dtu.dk/english/education/graduate/msc-programmes/{slug}/curriculum",
        content_hash="a" * 64,
    )


def test_parser_extracts_minimum_ects_and_terminated_courses():
    parsed = parse_specialization_page(_fixture("specialization_ai_algorithms.html"), CSE_URL)

    assert len(parsed) == 1
    specialization = parsed[0]
    assert specialization.program_slug == "computer-science-and-engineering"
    assert specialization.name == "Artificial Intelligence and Algorithms"
    assert specialization.requirements[0].requirement_type == "min_ects"
    assert specialization.requirements[0].required_ects == 25
    assert [course.course_number for course in specialization.courses[:3]] == ["02249", "02256", "02280"]
    assert [course.course_number for course in specialization.courses if course.is_terminated] == ["02221", "02285"]


def test_parser_preserves_separate_mandatory_choice_and_recommended_groups():
    parsed = parse_specialization_page(_fixture("specialization_offshore_wind.html"), WIND_URL)[0]

    assert [requirement.requirement_type for requirement in parsed.requirements] == [
        "all_of",
        "one_of",
        "one_of",
        "recommended",
    ]
    assert [course.role for course in parsed.courses] == [
        "mandatory",
        "mandatory",
        "choice",
        "choice",
        "choice",
        "choice",
        "recommended",
    ]


def test_parser_supports_one_page_with_multiple_specializations():
    parsed = parse_specialization_page(_fixture("specialization_technology_entrepreneurship.html"), TECH_URL)

    assert [item.name for item in parsed] == ["Technology", "Design", "Management", "Sustainability"]
    assert all(item.requirements[0].required_ects == 20 for item in parsed)


def test_parser_keeps_official_specialization_page_without_course_table():
    html = """
    <html><body><main id="main-content"><h1>Cold Regions</h1><div class="o-sdb">
      <p>This specialization focuses on design and construction in cold regions.</p>
    </div></main></body></html>
    """
    url = (
        "https://www.dtu.dk/english/education/graduate/msc-programmes/"
        "civil-engineering/specialization/cold-regions"
    )

    specialization = parse_specialization_page(html, url)[0]
    assert specialization.name == "Cold Regions"
    assert specialization.description == "This specialization focuses on design and construction in cold regions."
    assert specialization.courses == []
    assert specialization.requirements == []


def test_upsert_is_idempotent_and_replaces_changed_content(db_session):
    db_session.add(_program("computer-science-and-engineering", "Computer Science and Engineering"))
    db_session.commit()
    data = parse_specialization_page(_fixture("specialization_ai_algorithms.html"), CSE_URL)[0]

    assert upsert_specialization(db_session, data) == "imported"
    db_session.commit()
    assert upsert_specialization(db_session, data) == "unchanged"
    data.description = "Changed description"
    assert upsert_specialization(db_session, data) == "updated"
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(StudySpecialization)) == 1
    assert db_session.scalar(select(func.count()).select_from(SpecializationCourse)) == 5


def test_specialization_intent_has_priority_over_course_number():
    intent = classify_intent("Tæller 02249 på AI-specialiseringen?")
    assert isinstance(intent, SpecializationIntent)


def test_chat_lists_program_specializations_and_explains_course_requirements(db_session):
    program = _program("computer-science-and-engineering", "Computer Science and Engineering")
    program.aliases.append("CSE")
    db_session.add(program)
    db_session.commit()
    data = parse_specialization_page(_fixture("specialization_ai_algorithms.html"), CSE_URL)[0]
    upsert_specialization(db_session, data)
    db_session.commit()

    overview = recommend_courses(
        db_session,
        messages=["Hvilke specialiseringer har Computer Science and Engineering?"],
        academic_year="2026-2027",
    )
    assert overview.specializations[0].name == "Artificial Intelligence and Algorithms"
    assert overview.specializations[0].is_optional is True
    assert "følgende importerede specialiseringer" in overview.reply

    detail = recommend_courses(
        db_session,
        messages=["Hvilke kurser er der på Artificial Intelligence and Algorithms-specialiseringen?"],
        academic_year="2026-2027",
    )
    assert detail.specializations[0].requirements[0].required_ects == 25
    assert "mindst 25 ECTS" in detail.reply
    assert "02249 Computationally Hard Problems" in detail.reply


def test_chat_matches_danish_specialization_alias_in_ects_question(db_session):
    program = _program("computer-science-and-engineering", "Computer Science and Engineering")
    db_session.add(program)
    db_session.commit()
    upsert_specialization(
        db_session,
        parse_specialization_page(_fixture("specialization_ai_algorithms.html"), CSE_URL)[0],
    )
    db_session.commit()

    response = recommend_courses(
        db_session,
        messages=[
            "Hvor mange ECTS skal man have for at opnå en specialisering i f.eks. "
            "kunstig intelligens og algoritmer på computer science and engineering?"
        ],
        academic_year="2026-2027",
    )

    assert response.specializations[0].name == "Artificial Intelligence and Algorithms"
    assert response.specializations[0].requirements[0].required_ects == 25
    assert response.reply.startswith("For specialiseringen Artificial Intelligence and Algorithms")
    assert "mindst 25 ECTS" in response.reply


def test_exact_specialization_name_wins_over_fuzzy_program_match(db_session):
    db_session.add_all(
        [
            _program("computer-science-and-engineering", "Computer Science and Engineering"),
            StudyProgram(
                slug="kunstig-intelligens-og-data",
                name="Kunstig Intelligens og Data",
                degree_type="Bachelor",
                aliases=["Artificial Intelligence and Data"],
                academic_year="2026-2027",
                source_url="https://student.dtu.dk/study-plan/ai-data",
                content_hash="b" * 64,
            ),
        ]
    )
    db_session.commit()
    upsert_specialization(
        db_session,
        parse_specialization_page(_fixture("specialization_ai_algorithms.html"), CSE_URL)[0],
    )
    db_session.commit()

    response = recommend_courses(
        db_session,
        messages=["Hvilke kurser er der på Artificial Intelligence and Algorithms-specialiseringen?"],
        academic_year="2026-2027",
    )

    assert response.understood.program == "Computer Science and Engineering"
    assert response.specializations[0].name == "Artificial Intelligence and Algorithms"


def test_specialization_overview_keeps_program_when_global_specialization_has_same_name(db_session):
    wind_program = _program("wind-energy", "Wind Energy")
    wind_program.specializations = [
        StudySpecialization(
            slug="offshore-wind-energy",
            name="Offshore Wind Energy",
            source_url="https://www.dtu.dk/wind-energy/offshore-wind-energy",
            content_hash="c" * 64,
        ),
        StudySpecialization(
            slug="digitalization-in-wind-energy",
            name="Digitalization in Wind Energy",
            source_url="https://www.dtu.dk/wind-energy/digitalization",
            content_hash="d" * 64,
        ),
    ]
    sustainable_energy = _program(
        "sustainable-energy-technologies",
        "Sustainable Energy Technologies",
    )
    sustainable_energy.specializations = [
        StudySpecialization(
            slug="wind-energy",
            name="Wind Energy",
            source_url="https://www.dtu.dk/sustainable-energy-technologies/wind-energy",
            content_hash="e" * 64,
        )
    ]
    db_session.add_all([wind_program, sustainable_energy])
    db_session.commit()

    response = recommend_courses(
        db_session,
        messages=["Specialiseringer wind energy"],
        academic_year="2026-2027",
    )

    assert response.understood.program == "Wind Energy"
    assert [item.name for item in response.specializations] == [
        "Offshore Wind Energy",
        "Digitalization in Wind Energy",
    ]
    assert all(item.program_name == "Wind Energy" for item in response.specializations)


def test_mcp_specialization_handler_returns_structured_requirements(db_session):
    from app.mcp_server.server import _handle_get_specializations

    db_session.add(_program("computer-science-and-engineering", "Computer Science and Engineering"))
    db_session.commit()
    upsert_specialization(
        db_session,
        parse_specialization_page(_fixture("specialization_ai_algorithms.html"), CSE_URL)[0],
    )
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    with patch("app.database.SessionLocal", factory):
        result = _handle_get_specializations(
            {
                "program_name": "Computer Science and Engineering",
                "specialization_name": "Artificial Intelligence and Algorithms",
                "academic_year": "2026-2027",
            }
        )

    specialization = result["specializations"][0]
    assert result["specializations_are_optional"] is True
    assert specialization["is_optional"] is True
    assert specialization["requirements"][0]["required_ects"] == 25
    assert specialization["requirements"][0]["courses"][0]["course_number"] == "02249"


def test_study_plan_refresh_preserves_imported_specializations(db_session):
    program = _program("computer-science-and-engineering", "Computer Science and Engineering")
    db_session.add(program)
    db_session.commit()
    upsert_specialization(
        db_session,
        parse_specialization_page(_fixture("specialization_ai_algorithms.html"), CSE_URL)[0],
    )
    db_session.commit()
    original_program_id = program.id
    refreshed = StudyProgramData(
        slug=program.slug,
        name=program.name,
        degree_type=program.degree_type,
        aliases=program.aliases,
        academic_year=program.academic_year,
        valid_from_year=None,
        valid_to_year=None,
        introduction="Updated curriculum introduction",
        source_url=program.source_url,
        sections=[],
    )

    assert upsert_study_plan(db_session, refreshed) == "updated"
    db_session.commit()

    specialization = db_session.scalar(select(StudySpecialization))
    assert specialization is not None
    assert specialization.program_id == original_program_id
