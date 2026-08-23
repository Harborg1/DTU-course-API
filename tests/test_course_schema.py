from app.schemas.course import CourseData


def test_zero_ects_is_preserved_for_official_non_credit_course():
    data = CourseData(
        course_number="41E16",
        academic_year="2026-2027",
        title="Engineering mathematics and physics for building constructers",
        ects=0,
        source_url="https://kurser.dtu.dk/course/2026-2027/41E16",
    )
    assert data.ects == 0
