import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["API_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["MCP_TOKEN"] = "test-mcp-token"
os.environ["SEMANTIC_RESOLUTION_ENABLED"] = "false"
os.environ["SEMANTIC_INTENT_ENABLED"] = "false"
os.environ["SEMANTIC_COURSE_SEARCH_ENABLED"] = "false"

from app.config import get_settings  # noqa: E402
get_settings.cache_clear()
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.course import Course, CourseTranslation  # noqa: E402


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def sample_courses(db_session: Session) -> list[Course]:
    now = datetime.now(UTC)
    courses = [
        Course(
            course_number="02450", academic_year="2026-2027", ects=5, level="MSc",
            course_type="MSc", language="English", department="DTU Compute",
            department_code="01", period="E", schedule="E2A", campus="Campus Lyngby",
            source_url="https://kurser.dtu.dk/course/2026-2027/02450",
            content_hash="a" * 64, imported_at=now, updated_at=now,
            translations=[
                CourseTranslation(
                    language_code="da-DK", title="Introduktion til maskinlæring",
                    description="Datamodellering med beslutningstræer",
                    content="Maskinlæringsalgoritmer",
                ),
                CourseTranslation(
                    language_code="en-GB", title="Introduction to Machine Learning",
                    description="Supervised learning and decision trees",
                    content="Machine learning algorithms",
                ),
            ],
        ),
        Course(
            course_number="01418", academic_year="2026-2027", ects=5, level="BSc",
            course_type="Bachelor", language="English", department="DTU Compute",
            department_code="01", period="E", schedule="E5A", campus="Campus Lyngby",
            source_url="https://kurser.dtu.dk/course/2026-2027/01418",
            content_hash="b" * 64, imported_at=now, updated_at=now,
            translations=[
                CourseTranslation(language_code="da-DK", title="Partielle differentialligninger"),
                CourseTranslation(
                    language_code="en-GB", title="Partial Differential Equations",
                    description="Mathematical physics", content="Waves and diffusion",
                ),
            ],
        ),
        Course(
            course_number="02450", academic_year="2025-2026", ects=5, level="MSc",
            language="English", source_url="https://kurser.dtu.dk/course/2025-2026/02450",
            content_hash="c" * 64, imported_at=now, updated_at=now,
            translations=[
                CourseTranslation(language_code="da-DK", title="Gammel machine learning"),
                CourseTranslation(language_code="en-GB", title="Old Machine Learning"),
            ],
        ),
    ]
    db_session.add_all(courses)
    db_session.commit()
    return courses


@pytest.fixture
def client(db_session: Session) -> TestClient:
    def override_db():
        yield db_session
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": "test-secret"}
