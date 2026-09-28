from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Course, CourseTranslation, StudyProgram, StudySpecialization
from scripts.compare_databases import capture_snapshot, compare_snapshots, database_identity


def _database(path, *, course_hash="a", include_extra_course=False):
    database_url = f"sqlite:///{path}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        course = Course(
            course_number="02450",
            academic_year="2026-2027",
            source_url="https://kurser.dtu.dk/course/2026-2027/02450",
            content_hash=course_hash * 64,
            translations=[
                CourseTranslation(
                    language_code="en-GB",
                    title="Introduction to Machine Learning",
                    embedding_text_hash="e" * 64,
                    embedding_model="text-embedding-3-small",
                )
            ],
        )
        program = StudyProgram(
            slug="computer-science-and-engineering",
            name="Computer Science and Engineering",
            degree_type="Master",
            source_url="https://www.dtu.dk/computer-science/curriculum",
            content_hash="p" * 64,
        )
        program.specializations.append(
            StudySpecialization(
                slug="cybersecurity",
                name="Cybersecurity",
                source_url="https://www.dtu.dk/computer-science/specialization/cybersecurity",
                content_hash="s" * 64,
            )
        )
        session.add_all([course, program])
        if include_extra_course:
            session.add(
                Course(
                    course_number="01001",
                    academic_year="2026-2027",
                    source_url="https://kurser.dtu.dk/course/2026-2027/01001",
                    content_hash="x" * 64,
                    translations=[CourseTranslation(language_code="en-GB", title="Mathematics")],
                )
            )
        session.commit()
    engine.dispose()
    return database_url


def test_identical_databases_compare_equal(tmp_path):
    source_url = _database(tmp_path / "source.db")
    target_url = _database(tmp_path / "target.db")

    report = compare_snapshots(
        capture_snapshot(source_url),
        capture_snapshot(target_url),
        source_label="source",
        target_label="target",
    )

    assert report["has_differences"] is False
    assert report["entities"]["courses"]["identical"] == 1
    assert report["entities"]["study_programs"]["identical"] == 1
    assert report["entities"]["specializations"]["identical"] == 1
    assert report["entities"]["course_embeddings"]["identical"] == 1


def test_changed_and_missing_courses_are_reported(tmp_path):
    source_url = _database(tmp_path / "source.db", course_hash="a", include_extra_course=True)
    target_url = _database(tmp_path / "target.db", course_hash="b")

    report = compare_snapshots(
        capture_snapshot(source_url),
        capture_snapshot(target_url),
        source_label="source",
        target_label="target",
    )
    courses = report["entities"]["courses"]

    assert report["has_differences"] is True
    assert courses["source_only"] == ["2026-2027/01001"]
    assert courses["target_only"] == []
    assert [item["key"] for item in courses["changed"]] == ["2026-2027/02450"]


def test_capture_snapshot_does_not_modify_database(tmp_path):
    database_url = _database(tmp_path / "database.db")

    capture_snapshot(database_url)

    engine = create_engine(database_url)
    with Session(engine) as session:
        assert len(list(session.scalars(select(Course)))) == 1
    engine.dispose()


def test_database_identity_omits_credentials():
    identity = database_identity(
        "postgresql+psycopg://secret-user:secret-password@db.example.com:6543/postgres"
    )

    assert identity == {
        "driver": "postgresql+psycopg",
        "host": "db.example.com",
        "port": 6543,
        "database": "postgres",
    }
