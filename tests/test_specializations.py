from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models.specialization import SpecializationCourse, StudySpecialization
from app.models.study_plan import StudyProgram
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
