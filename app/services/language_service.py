import re

from langdetect import detect


SUPPORTED_LANGUAGES = {"da", "en"}

_DANISH_MARKERS = {
    "anbefal": 2,
    "anbefale": 2,
    "dansk": 2,
    "fortsæt": 2,
    "hej": 2,
    "hvad": 2,
    "hvem": 2,
    "hvordan": 2,
    "hvornår": 2,
    "hvorfor": 2,
    "ja": 2,
    "kursus": 2,
    "kurset": 2,
    "kurser": 2,
    "matematik": 2,
    "sammenlign": 2,
    "sammenligne": 2,
    "sammenligning": 2,
    "studerer": 2,
    "studie": 2,
    "studier": 2,
    "studieguide": 2,
    "studieordning": 2,
    "studieplan": 2,
    "uddannelse": 2,
    "uddannelser": 2,
    "specialisering": 2,
    "specialiseringer": 2,
    "underviser": 2,
    "uddyb": 2,
    "uddybe": 2,
}

_ENGLISH_MARKERS = {
    "course": 2,
    "courses": 2,
    "elaborate": 2,
    "english": 2,
    "hello": 2,
    "how": 2,
    "please": 1,
    "recommend": 2,
    "programme": 2,
    "programmes": 2,
    "student": 2,
    "study": 1,
    "specialisation": 2,
    "specialisations": 2,
    "specialities": 2,
    "speciality": 2,
    "specialization": 2,
    "specializations": 2,
    "specialties": 2,
    "specialty": 2,
    "teaches": 2,
    "what": 2,
    "when": 2,
    "where": 2,
    "who": 2,
    "why": 2,
    "yes": 2,
}


def _marker_score(tokens: set[str], markers: dict[str, int]) -> int:
    return sum(weight for marker, weight in markers.items() if marker in tokens)


def detect_explicit_user_language(text: str) -> str | None:
    """Detect a language only when the message contains useful evidence.

    Short identifiers such as course numbers and degree abbreviations are
    language-neutral. Returning ``None`` for them lets callers preserve the
    language of the conversation instead of silently switching to English.
    """
    normalized = text.casefold()
    tokens = set(re.findall(r"[a-zæøå]+", normalized))
    danish_score = _marker_score(tokens, _DANISH_MARKERS)
    english_score = _marker_score(tokens, _ENGLISH_MARKERS)
    if any(character in normalized for character in "æøå"):
        danish_score += 2
    if danish_score > english_score:
        return "da"
    if english_score > danish_score:
        return "en"

    # A single unrecognised word is commonly a name, acronym, or terse
    # follow-up and does not carry enough evidence for a language switch.
    if len(tokens) < 2:
        return None

    try:
        language = detect(text)
    except Exception:
        return None
    return language if language in SUPPORTED_LANGUAGES else None


def detect_user_language(text: str, *, default: str = "en") -> str:
    """Detect Danish or English, falling back to ``default`` when uncertain."""
    return detect_explicit_user_language(text) or default


def resolve_response_language(
    latest_message: str,
    *,
    previous_messages: list[str] | None = None,
    previous_languages: list[str | None] | None = None,
    inferred_language: str | None = None,
    default: str = "en",
) -> str:
    """Resolve response language without losing conversation context."""
    explicit_language = detect_explicit_user_language(latest_message)
    if explicit_language is not None:
        return explicit_language

    for language in reversed(previous_languages or []):
        if language in SUPPORTED_LANGUAGES:
            return language

    for message in reversed(previous_messages or []):
        language = detect_explicit_user_language(message)
        if language is not None:
            return language

    if inferred_language in SUPPORTED_LANGUAGES:
        return inferred_language
    return default
