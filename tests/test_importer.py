from sqlalchemy import func, select

from app.models.course import Course
from app.models.import_failure import ImportFailure
from app.schemas.course import CourseData
from importer.importer import clear_failure, record_failure, upsert_course


def course_data() -> CourseData:
    return CourseData(
        course_number="01017",
        academic_year="2026-2027",
        title="Discrete Mathematics",
        ects=5,
        source_url="https://kurser.dtu.dk/course/2026-2027/01017",
    )


def test_database_upsert_and_unchanged_detection(db_session):
    data = course_data()
    assert upsert_course(db_session, data) == "imported"
    db_session.commit()
    assert upsert_course(db_session, data) == "unchanged"
    changed = data.model_copy(update={"title": "Changed official title"})
    assert upsert_course(db_session, changed) == "updated"
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(Course)) == 1
    assert db_session.scalar(select(Course.title)) == "Changed official title"


def test_duplicate_constraint_is_backed_by_upsert(db_session):
    data = course_data()
    upsert_course(db_session, data)
    upsert_course(db_session, data)
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(Course)) == 1


def test_failed_import_is_recorded_incremented_and_cleared(db_session):
    error = ValueError("parser failed")
    url = "https://kurser.dtu.dk/course/2026-2027/01017"
    record_failure(db_session, "01017", "2026-2027", url, error)
    db_session.commit()
    record_failure(db_session, "01017", "2026-2027", url, error)
    db_session.commit()
    failure = db_session.scalar(select(ImportFailure))
    assert failure.attempts == 2
    clear_failure(db_session, "01017", "2026-2027")
    db_session.commit()
    assert db_session.scalar(select(ImportFailure)) is None
