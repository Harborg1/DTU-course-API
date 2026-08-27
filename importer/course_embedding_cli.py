import argparse
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models.course import Course, CourseTranslation
from app.services.embedding_service import (
    EmbeddingService,
    EmbeddingServiceError,
    course_embedding_text_hash,
    embedding_document_from_translation,
)


logger = logging.getLogger(__name__)


@dataclass
class CourseEmbeddingSummary:
    translations_scanned: int = 0
    embeddings_current: int = 0
    embeddings_generated: int = 0
    embeddings_pending: int = 0


def backfill_course_embeddings(
    session: Session,
    *,
    academic_year: str,
    batch_size: int | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    force: bool = False,
    service: EmbeddingService | None = None,
) -> CourseEmbeddingSummary:
    settings = get_settings()
    selected_batch_size = batch_size or settings.embedding_batch_size
    rows = session.execute(
        select(CourseTranslation, Course.course_number)
        .join(Course, Course.id == CourseTranslation.course_id)
        .where(Course.academic_year == academic_year)
        .order_by(CourseTranslation.id)
    ).all()
    summary = CourseEmbeddingSummary(translations_scanned=len(rows))
    pending: list[tuple[CourseTranslation, str, str]] = []
    for translation, course_number in rows:
        document = embedding_document_from_translation(course_number, translation)
        source_hash = course_embedding_text_hash(document)
        is_current = (
            not force
            and translation.embedding is not None
            and translation.embedding_text_hash == source_hash
            and translation.embedding_model == settings.embedding_model
        )
        if is_current:
            summary.embeddings_current += 1
        else:
            pending.append((translation, document, source_hash))

    if limit is not None:
        pending = pending[:limit]
    summary.embeddings_pending = len(pending)
    if dry_run or not pending:
        return summary

    embedding_service = service or EmbeddingService(settings=settings)
    total_pending = len(pending)
    for offset in range(0, len(pending), selected_batch_size):
        batch = pending[offset : offset + selected_batch_size]
        vectors = embedding_service.embed_texts([document for _, document, _ in batch])
        updated_at = datetime.now(UTC)
        for (translation, _document, source_hash), vector in zip(batch, vectors, strict=True):
            translation.embedding = vector
            translation.embedding_text_hash = source_hash
            translation.embedding_model = settings.embedding_model
            translation.embedding_updated_at = updated_at
        session.commit()
        summary.embeddings_generated += len(batch)
        summary.embeddings_pending -= len(batch)
        logger.info(
            "Generated %d/%d pending course embeddings",
            summary.embeddings_generated,
            total_pending,
        )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate missing or stale OpenAI embeddings for DTU course translations"
    )
    parser.add_argument("--academic-year", default="2026-2027")
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.batch_size is not None and not 1 <= args.batch_size <= 2048:
        raise SystemExit("--batch-size must be between 1 and 2048")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        with SessionLocal() as session:
            summary = backfill_course_embeddings(
                session,
                academic_year=args.academic_year,
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=args.dry_run,
                force=args.force,
            )
    except EmbeddingServiceError as exc:
        raise SystemExit(str(exc)) from exc

    print("Course embedding backfill complete")
    for key, value in asdict(summary).items():
        print(f"{key.replace('_', ' ').title()}: {value}")


if __name__ == "__main__":
    main()
