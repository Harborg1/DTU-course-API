from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.course import Course
from importer.course_xml_importer import import_course_xml_directory
from importer.course_xml_parser import parse_course_xml


FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_bilingual_course_xml():
    course = parse_course_xml((FIXTURES / "course_02452.xml").read_bytes())

    assert course.course_number == "02452"
    assert course.academic_year == "2026-2027"
    assert course.title_da == "Machine learning"
    assert course.title_en == "Machine Learning"
    assert course.content_da == "Struktureret datamodellering og beslutningstræer."
    assert course.content_en == "Structured data modelling and decision trees."
    assert course.description_da == "Anvende machine learning på virkelige data."
    assert course.description_en == "Apply machine learning to real-world data."
    assert course.learning_objectives_da == "Evaluere machine learning-modeller."
    assert course.learning_objectives_en == "Evaluate machine-learning models."
    assert course.prerequisites_da == "Lineær algebra og Python."
    assert course.prerequisites_en == "Linear algebra and Python."
    assert course.recommended_prerequisite_course_numbers == [
        "01017",
        "02101",
        "02105",
        "02180",
    ]


def test_parses_structured_course_metadata():
    course = parse_course_xml((FIXTURES / "course_02452.xml").read_bytes())

    assert course.level == "MSc"
    assert course.schedules == ["E4A"]
    assert course.period == "E"
    assert course.responsible_people[0]["name"] == "Georgios Arvanitidis"
    assert course.examinations[0]["assessment_key"] == "Written_Exam_And_Exercises"
    assert course.no_credit_with == ["02450", "02451"]
    assert course.recommended_prerequisite_course_numbers == [
        "01017",
        "02101",
        "02105",
        "02180",
    ]
    assert course.source_last_updated.isoformat() == "2026-03-26T00:00:00+01:00"


def test_rejects_xml_without_course():
    with pytest.raises(ValueError, match="Course element"):
        parse_course_xml("<root />")


def test_imports_saved_xml_idempotently(db_session, tmp_path):
    destination = tmp_path / "02452.txt"
    destination.write_bytes((FIXTURES / "course_02452.xml").read_bytes())

    first = import_course_xml_directory(
        db_session,
        tmp_path,
        academic_year="2026-2027",
    )
    second = import_course_xml_directory(
        db_session,
        tmp_path,
        academic_year="2026-2027",
    )

    course = db_session.scalar(select(Course))
    assert first.courses_imported == 1
    assert second.courses_unchanged == 1
    assert course.content_da == "Struktureret datamodellering og beslutningstræer."
    assert course.content_en == "Structured data modelling and decision trees."
    assert course.recommended_prerequisite_course_numbers == [
        "01017",
        "02101",
        "02105",
        "02180",
    ]
