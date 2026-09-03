from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models.course import Course, CourseTranslation
from app.services.course_change_service import (
    CatalogComparisonError,
    get_new_courses,
    preceding_academic_year,
)


def _course(
    number: str,
    year: str,
    *,
    previous_course_numbers: list[str] | None = None,
    level: str | None = None,
    ects: Decimal | int | float | None = None,
    topic: str | None = None,
) -> Course:
    now = datetime.now(UTC)
    return Course(
        course_number=number,
        academic_year=year,
        source_url=f"https://kurser.dtu.dk/course/{year}/{number}",
        content_hash=number.ljust(64, "0"),
        imported_at=now,
        updated_at=now,
        previous_course_numbers=previous_course_numbers or [],
        level=level,
        ects=ects,
        translations=[
            CourseTranslation(
                language_code="da-DK",
                title=f"Dansk {number}",
                description=topic,
            ),
            CourseTranslation(
                language_code="en-GB",
                title=f"English {number}",
                description=topic,
            ),
        ],
    )


def test_preceding_academic_year():
    assert preceding_academic_year("2026-2027") == "2025-2026"


def test_classifies_created_and_renumbered_courses(db_session):
    db_session.add_all(
        [
            _course("01001", "2025-2026"),
            _course("01002", "2025-2026"),
            _course("01001", "2026-2027"),
            _course("01003", "2026-2027"),
            _course("01004", "2026-2027", previous_course_numbers=["01002", "09999"]),
        ]
    )
    db_session.commit()

    result = get_new_courses(db_session, "2026-2027")

    assert [item.course.course_number for item in result.courses] == ["01003", "01004"]
    assert [item.classification for item in result.courses] == ["created", "renumbered"]
    assert result.courses[1].previous_course_numbers == ("01002",)
    assert result.created_count == 1
    assert result.renumbered_count == 1


def test_refuses_comparison_when_previous_catalogue_is_missing(db_session):
    db_session.add(_course("01003", "2026-2027"))
    db_session.commit()

    with pytest.raises(CatalogComparisonError, match="2025-2026"):
        get_new_courses(db_session, "2026-2027")


@pytest.mark.parametrize(
    ("level", "expected_numbers"),
    [
        ("BSc", ["01003"]),
        ("MSc", ["01004"]),
        ("PhD", ["01005"]),
    ],
)
def test_filters_new_courses_by_level(db_session, level, expected_numbers):
    db_session.add_all(
        [
            _course("01001", "2025-2026", level="BSc"),
            _course("01002", "2025-2026", level="MSc"),
            _course("01001", "2026-2027", level="BSc"),
            _course("01003", "2026-2027", level="BSc"),
            _course("01004", "2026-2027", level="MSc"),
            _course("01005", "2026-2027", level="PhD"),
        ]
    )
    db_session.commit()

    result = get_new_courses(db_session, "2026-2027", level=level)

    assert [item.course.course_number for item in result.courses] == expected_numbers
    assert result.level == level


@pytest.mark.parametrize(
    ("ects", "expected_numbers"),
    [
        (Decimal("5"), ["01003"]),
        (Decimal("7.5"), ["01004"]),
        (Decimal("10"), ["01005"]),
    ],
)
def test_filters_new_courses_by_exact_ects(db_session, ects, expected_numbers):
    db_session.add_all(
        [
            _course("01001", "2025-2026"),
            _course("01003", "2026-2027", ects=5),
            _course("01004", "2026-2027", ects=Decimal("7.5")),
            _course("01005", "2026-2027", ects=10),
        ]
    )
    db_session.commit()

    result = get_new_courses(db_session, "2026-2027", ects=ects)

    assert [item.course.course_number for item in result.courses] == expected_numbers
    assert result.ects == ects


def test_filters_new_courses_by_topic_ects_and_level(db_session):
    db_session.add_all(
        [
            _course("01001", "2025-2026"),
            _course("01003", "2026-2027", level="MSc", ects=5, topic="machine learning"),
            _course("01004", "2026-2027", level="MSc", ects=10, topic="machine learning"),
            _course("01005", "2026-2027", level="BSc", ects=5, topic="machine learning"),
            _course("01006", "2026-2027", level="MSc", ects=5, topic="artificial intelligence"),
        ]
    )
    db_session.commit()

    result = get_new_courses(
        db_session,
        "2026-2027",
        level="MSc",
        topic="machine learning",
        ects=Decimal("5"),
    )

    assert [item.course.course_number for item in result.courses] == ["01003"]
    assert result.topic == "machine learning"
