from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course


def get_course(session: Session, course_number: str, academic_year: str) -> Course | None:
    return session.scalar(
        select(Course).where(
            Course.course_number == course_number.upper(),
            Course.academic_year == academic_year,
        )
    )

