from pathlib import Path

import pytest

from importer.course_list import parse_course_numbers, parse_departments
from importer.course_parser import parse_course_page
from app.schemas.course import CourseData

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    ("course_number", "title", "ects"),
    [
        ("01001", "Mathematics 1a (Polytechnical foundation)", "10"),
        ("01017", "Discrete Mathematics", "5"),
        ("01418", "Introduction to Partial Differential Equations", "5"),
    ],
)
def test_parse_verified_course_variants(course_number, title, ects):
    html = (FIXTURES / f"course_{course_number}.html").read_text()
    course = parse_course_page(html, course_number, "2026-2027")
    assert course.title == title
    assert str(course.ects) == ects
    assert course.department_code == "01"
    assert course.source_url.endswith(f"/2026-2027/{course_number}")
    assert course.learning_objectives


def test_parser_normalizes_level_and_language_for_api_filters():
    html = (FIXTURES / "course_01017.html").read_text()
    course = parse_course_page(html, "01017", "2026-2027")
    assert course.level == "BSc"
    assert course.language == "English"


def test_parser_handles_optional_fields_without_inventing_values():
    html = (FIXTURES / "course_01017.html").read_text()
    course = parse_course_page(html, "01017", "2026-2027")
    assert course.prerequisites is None
    assert course.remarks is None


def test_parser_rejects_wrong_academic_year():
    html = (FIXTURES / "course_01001.html").read_text()
    with pytest.raises(ValueError, match="expected academic year"):
        parse_course_page(html, "01001", "2025-2026")


def test_course_list_extracts_departments_and_deduplicates():
    html = (FIXTURES / "course_list.html").read_text()
    assert [item.code for item in parse_departments(html)] == ["1", "IHK"]
    assert parse_course_numbers(html) == {"01001", "01017"}


def test_zero_ects_is_preserved_for_official_non_credit_course():
    data = CourseData(
        course_number="41E16",
        academic_year="2026-2027",
        title="Engineering mathematics and physics for building constructers",
        ects=0,
        source_url="https://kurser.dtu.dk/course/2026-2027/41E16",
    )
    assert data.ects == 0
