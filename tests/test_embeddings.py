from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import select

from app.config import Settings, get_settings
from app.models.course import Course, CourseTranslation
from app.services.embedding_service import (
    EmbeddingService,
    build_course_embedding_document,
    course_embedding_text_hash,
)
from app.services.search_service import _reciprocal_rank_fusion
from importer.course_embedding_cli import backfill_course_embeddings


class FakeEmbeddingsApi:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        dimensions = kwargs["dimensions"]
        data = [
            SimpleNamespace(index=index, embedding=[float(index)] * dimensions)
            for index, _text in reversed(list(enumerate(kwargs["input"])))
        ]
        return SimpleNamespace(data=data)


def test_embedding_document_is_normalized_and_hash_is_stable():
    first = build_course_embedding_document(
        course_number="02277",
        title=" Cyber Risk  Management ",
        description="Incident\nresponse and   security",
    )
    second = build_course_embedding_document(
        course_number="02277",
        title="Cyber Risk Management",
        description="Incident response and security",
    )

    assert first == second
    assert course_embedding_text_hash(first) == course_embedding_text_hash(second)
    assert "Prerequisites" not in first


def test_embedding_service_batches_inputs_and_preserves_response_order():
    settings = Settings(
        api_key="test-api-key",
        embedding_api_key="test-embedding-key",
    )
    embeddings_api = FakeEmbeddingsApi()
    client = SimpleNamespace(embeddings=embeddings_api)
    service = EmbeddingService(settings=settings, client=client)

    vectors = service.embed_texts(["first", "second"])

    assert vectors[0][0] == 0.0
    assert vectors[1][0] == 1.0
    assert embeddings_api.calls[0]["model"] == "text-embedding-3-small"
    assert embeddings_api.calls[0]["dimensions"] == 1536


def test_backfill_only_generates_missing_or_stale_embeddings(db_session):
    now = datetime.now(UTC)
    course = Course(
        course_number="02277",
        academic_year="2026-2027",
        source_url="https://kurser.dtu.dk/course/2026-2027/02277",
        content_hash="a" * 64,
        imported_at=now,
        updated_at=now,
        translations=[
            CourseTranslation(
                language_code="da-DK",
                title="Cyberrisikostyring og hændelsesrespons",
            ),
            CourseTranslation(
                language_code="en-GB",
                title="Cyber Risk Management and Incident Response",
            ),
        ],
    )
    db_session.add(course)
    db_session.commit()
    fake_service = SimpleNamespace(
        embed_texts=lambda texts: [[0.2] * 1536 for _text in texts]
    )

    first = backfill_course_embeddings(
        db_session,
        academic_year="2026-2027",
        batch_size=1,
        service=fake_service,
    )
    second = backfill_course_embeddings(
        db_session,
        academic_year="2026-2027",
        service=fake_service,
    )

    assert first.embeddings_generated == 2
    assert first.embeddings_pending == 0
    assert second.embeddings_generated == 0
    assert second.embeddings_current == 2
    translations = db_session.scalars(select(CourseTranslation)).all()
    assert all(item.embedding_text_hash for item in translations)
    assert all(item.embedding_model == get_settings().embedding_model for item in translations)


def test_rank_fusion_includes_semantic_only_courses_and_rewards_overlap():
    lexical_only = Course(id=1, course_number="02270", academic_year="2026-2027")
    both = Course(id=2, course_number="02277", academic_year="2026-2027")
    semantic_only = Course(id=3, course_number="62428", academic_year="2026-2027")

    rows = _reciprocal_rank_fusion(
        {1: (lexical_only, 0.9), 2: (both, 0.8)},
        {2: (both, 0.95), 3: (semantic_only, 0.8)},
    )

    assert rows[0][0].course_number == "02277"
    assert {course.course_number for course, _score in rows} == {
        "02270",
        "02277",
        "62428",
    }
