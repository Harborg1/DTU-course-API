import hashlib
import re
import unicodedata
from functools import lru_cache
from typing import Any

from app.config import Settings, get_settings


EMBEDDING_TEXT_FIELDS = (
    ("Title", "title"),
    ("Description", "description"),
    ("Content", "content"),
    ("Learning objectives", "learning_objectives"),
)
MAX_EMBEDDING_CHARACTERS = 24_000


class EmbeddingServiceError(RuntimeError):
    """Raised when course embeddings cannot be generated safely."""


def normalize_embedding_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip()


def build_course_embedding_document(
    *,
    course_number: str,
    title: str,
    description: str | None = None,
    content: str | None = None,
    learning_objectives: str | None = None,
) -> str:
    values = {
        "title": title,
        "description": description,
        "content": content,
        "learning_objectives": learning_objectives,
    }
    parts = [f"Course number: {normalize_embedding_text(course_number)}"]
    for label, field in EMBEDDING_TEXT_FIELDS:
        value = normalize_embedding_text(values[field])
        if value:
            parts.append(f"{label}: {value}")
    return "\n".join(parts)[:MAX_EMBEDDING_CHARACTERS].rstrip()


def course_embedding_text_hash(document: str) -> str:
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


def embedding_document_from_translation(
    course_number: str,
    translation: Any,
) -> str:
    return build_course_embedding_document(
        course_number=course_number,
        title=translation.title,
        description=translation.description,
        content=translation.content,
        learning_objectives=translation.learning_objectives,
    )


def embedding_document_from_values(
    course_number: str,
    values: dict[str, Any],
) -> str:
    return build_course_embedding_document(
        course_number=course_number,
        title=values["title"],
        description=values.get("description"),
        content=values.get("content"),
        learning_objectives=values.get("learning_objectives"),
    )


class EmbeddingService:
    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self.settings = settings or get_settings()
        if not self.settings.embedding_api_key and client is None:
            raise EmbeddingServiceError("EMBEDDING_API_KEY is not configured")
        if client is None:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.settings.embedding_api_key,
                timeout=self.settings.embedding_timeout,
                max_retries=2,
            )
        self.client = client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            raise EmbeddingServiceError("Embedding inputs must not be empty")
        try:
            response = self.client.embeddings.create(
                input=texts,
                model=self.settings.embedding_model,
                dimensions=self.settings.embedding_dimensions,
                encoding_format="float",
            )
        except Exception as exc:
            raise EmbeddingServiceError("OpenAI embedding request failed") from exc

        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        if len(vectors) != len(texts):
            raise EmbeddingServiceError("OpenAI returned an unexpected number of embeddings")
        if any(len(vector) != self.settings.embedding_dimensions for vector in vectors):
            raise EmbeddingServiceError("OpenAI returned an unexpected embedding dimension")
        return vectors

    def embed_query(self, query: str) -> list[float]:
        normalized = normalize_embedding_text(query)
        if not normalized:
            raise EmbeddingServiceError("The semantic search query is empty")
        return self.embed_texts([normalized])[0]


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
