"""Validated semantic fallback for resolving user text to known database entities."""

import logging
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import get_settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SemanticCandidate:
    id: str
    name: str
    aliases: tuple[str, ...] = ()


class SemanticMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None
    confidence: float = Field(ge=0, le=1)


def resolve_semantic_candidate(
    text: str,
    candidates: list[SemanticCandidate],
    *,
    entity_type: str,
    context: str | None = None,
) -> str | None:
    """Return a validated candidate ID when deterministic matching was insufficient."""
    settings = get_settings()
    if not settings.semantic_resolution_enabled or not settings.groq_api_key or not candidates:
        return None

    candidate_by_id = {candidate.id: candidate for candidate in candidates}
    candidate_lines = []
    for candidate in candidates:
        aliases = ", ".join(candidate.aliases)
        suffix = f"; aliases: {aliases}" if aliases else ""
        candidate_lines.append(f"- id={candidate.id}; name={candidate.name}{suffix}")

    instructions = (
        f"Resolve the {entity_type} mentioned by the user to exactly one candidate from the supplied list. "
        "Use semantic meaning, abbreviations, translations, and spelling variants. "
        "Return candidate_id=null when no candidate is clearly mentioned or when the request is ambiguous. "
        "Never create an ID and never select a candidate from broad topical similarity alone."
    )
    if context:
        instructions += f" Context: {context}"

    prompt = f"User text:\n{text}\n\nCandidates:\n" + "\n".join(candidate_lines)

    from openai import OpenAI, OpenAIError

    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        timeout=settings.semantic_resolution_timeout,
        max_retries=0,
    )
    try:
        response = client.responses.parse(
            model=settings.groq_model,
            instructions=instructions,
            input=prompt,
            text_format=SemanticMatch,
            temperature=0,
        )
        match = response.output_parsed
    except (OpenAIError, ValidationError, ValueError, TypeError):
        logger.warning("Semantic %s resolution failed", entity_type, exc_info=True)
        return None

    if not isinstance(match, SemanticMatch):
        return None
    if match.candidate_id not in candidate_by_id:
        logger.warning("Semantic resolver returned an unknown %s ID", entity_type)
        return None
    if match.confidence < settings.semantic_resolution_min_confidence:
        return None
    return match.candidate_id
