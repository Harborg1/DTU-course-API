from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.course import Course


class CatalogComparisonError(ValueError):
    """Raised when both catalogues needed for a comparison are not imported."""


@dataclass(frozen=True)
class NewCourse:
    course: Course
    classification: Literal["created", "renumbered"]
    previous_course_numbers: tuple[str, ...] = ()


@dataclass(frozen=True)
class NewCoursesResult:
    academic_year: str
    previous_academic_year: str
    courses: tuple[NewCourse, ...]
    level: str | None = None

    @property
    def created_count(self) -> int:
        return sum(item.classification == "created" for item in self.courses)

    @property
    def renumbered_count(self) -> int:
        return sum(item.classification == "renumbered" for item in self.courses)


def preceding_academic_year(academic_year: str) -> str:
    try:
        start_text, end_text = academic_year.split("-", maxsplit=1)
        start, end = int(start_text), int(end_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("academic year must have the form YYYY-YYYY") from exc
    if len(start_text) != 4 or len(end_text) != 4 or end != start + 1:
        raise ValueError("academic year must cover consecutive years")
    return f"{start - 1:04d}-{start:04d}"


def get_new_courses(
    session: Session,
    academic_year: str,
    previous_academic_year: str | None = None,
    *,
    level: str | None = None,
) -> NewCoursesResult:
    """Return courses absent by number from the preceding catalogue.

    DTU's ``PreviousCourse`` metadata identifies entries that represent an
    existing course under a new number. Every other number absent from the
    preceding catalogue is classified as newly created.
    """
    comparison_year = previous_academic_year or preceding_academic_year(academic_year)
    previous_numbers = set(
        session.scalars(
            select(Course.course_number).where(Course.academic_year == comparison_year)
        )
    )
    if not previous_numbers:
        raise CatalogComparisonError(
            f"No course data is imported for comparison year {comparison_year}"
        )

    current_query = (
        select(Course)
        .options(selectinload(Course.translations))
        .where(Course.academic_year == academic_year)
        .order_by(Course.course_number)
    )
    if level:
        current_query = current_query.where(Course.level == level)
    current_courses = tuple(
        session.scalars(
            current_query
        )
    )
    current_catalogue_exists = session.scalar(
        select(Course.id).where(Course.academic_year == academic_year).limit(1)
    )
    if current_catalogue_exists is None:
        raise CatalogComparisonError(
            f"No course data is imported for academic year {academic_year}"
        )

    new_courses = []
    for course in current_courses:
        if course.course_number in previous_numbers:
            continue
        replaced_numbers = tuple(
            sorted(set(course.previous_course_numbers or ()) & previous_numbers)
        )
        new_courses.append(
            NewCourse(
                course=course,
                classification="renumbered" if replaced_numbers else "created",
                previous_course_numbers=replaced_numbers,
            )
        )

    return NewCoursesResult(
        academic_year=academic_year,
        previous_academic_year=comparison_year,
        courses=tuple(new_courses),
        level=level,
    )
