from datetime import UTC, datetime

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
        translations=[
            CourseTranslation(language_code="da-DK", title=f"Dansk {number}"),
            CourseTranslation(language_code="en-GB", title=f"English {number}"),
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
