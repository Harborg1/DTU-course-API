import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course, CourseTranslation
from app.models.import_failure import ImportFailure
from app.schemas.course import CourseData
from app.services.embedding_service import (
    course_embedding_text_hash,
    embedding_document_from_values,
)


def course_content_hash(data: CourseData) -> str:
    payload = data.model_dump(mode="json")
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


TRANSLATED_FIELDS = (
    "title",
    "description",
    "content",
    "learning_objectives",
    "prerequisites",
    "mandatory_prerequisites",
    "teaching_methods",
    "literature",
    "remarks",
)


def course_values(data: CourseData) -> dict:
    values = data.model_dump()
    for field in TRANSLATED_FIELDS:
        values.pop(field, None)
        values.pop(f"{field}_da", None)
        values.pop(f"{field}_en", None)
    values.pop("title_da", None)
    values.pop("title_en", None)
    return values


def course_translation_values(data: CourseData, language: str) -> dict:
    suffix, language_code = ("da", "da-DK") if language == "da" else ("en", "en-GB")
    fallback_suffix = "en" if suffix == "da" else "da"
    values = {"language_code": language_code}
    for field in TRANSLATED_FIELDS:
        value = getattr(data, f"{field}_{suffix}", None)
        if field == "title" and not value:
            value = getattr(data, f"title_{fallback_suffix}", None) or data.title
        values[field] = value
    return values


def invalidate_translation_embedding(translation: CourseTranslation) -> None:
    translation.embedding = None
    translation.embedding_text_hash = None
    translation.embedding_model = None
    translation.embedding_updated_at = None


def upsert_course(session: Session, data: CourseData) -> str:
    existing = session.scalar(
        select(Course).where(
            Course.course_number == data.course_number,
            Course.academic_year == data.academic_year,
        )
    )
    digest = course_content_hash(data)
    values = course_values(data)
    translations = [
        CourseTranslation(**course_translation_values(data, language))
        for language in ("da", "en")
    ]
    if existing is None:
        session.add(Course(**values, content_hash=digest, translations=translations))
        session.flush()
        return "imported"
    if existing.content_hash == digest:
        return "unchanged"
    for key, value in values.items():
        setattr(existing, key, value)
    translations_by_language = {
        translation.language_code: translation
        for translation in existing.translations
    }
    for new_values in (course_translation_values(data, "da"), course_translation_values(data, "en")):
        language_code = new_values["language_code"]
        translation = translations_by_language.get(language_code)
        if translation is None:
            existing.translations.append(CourseTranslation(**new_values))
        else:
            source_hash = course_embedding_text_hash(
                embedding_document_from_values(data.course_number, new_values)
            )
            if translation.embedding_text_hash != source_hash:
                invalidate_translation_embedding(translation)
            for key, value in new_values.items():
                setattr(translation, key, value)
    existing.content_hash = digest
    session.flush()
    return "updated"


def record_failure(session: Session, course_number: str, academic_year: str, source_url: str, exc: Exception) -> None:
    failure = session.scalar(
        select(ImportFailure).where(
            ImportFailure.course_number == course_number,
            ImportFailure.academic_year == academic_year,
        )
    )
    if failure is None:
        failure = ImportFailure(
            course_number=course_number,
            academic_year=academic_year,
            source_url=source_url,
            error_type=type(exc).__name__,
            error_message=str(exc)[:4000],
        )
        session.add(failure)
    else:
        failure.error_type = type(exc).__name__
        failure.error_message = str(exc)[:4000]
        failure.attempts += 1


def clear_failure(session: Session, course_number: str, academic_year: str) -> None:
    failure = session.scalar(
        select(ImportFailure).where(
            ImportFailure.course_number == course_number,
            ImportFailure.academic_year == academic_year,
        )
    )
    if failure is not None:
        session.delete(failure)
