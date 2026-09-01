import re

from langdetect import detect


SUPPORTED_LANGUAGES = {"da", "en"}

_DANISH_MARKERS = {
    "anbefal": 2,
    "anbefale": 2,
    "hej": 2,
    "hvad": 2,
    "hvem": 2,
    "hvordan": 2,
    "hvornår": 2,
    "hvorfor": 2,
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
    "studieordning": 2,
    "studieplan": 2,
    "uddannelse": 2,
    "uddannelser": 2,
    "specialisering": 2,
    "specialiseringer": 2,
    "underviser": 2,
}

_ENGLISH_MARKERS = {
    "course": 2,
    "courses": 2,
    "hello": 2,
    "how": 2,
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
}


def _marker_score(tokens: set[str], markers: dict[str, int]) -> int:
    return sum(weight for marker, weight in markers.items() if marker in tokens)


def detect_user_language(text: str, *, default: str = "en") -> str:
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

    try:
        language = detect(text)
    except Exception:
        return default
    return language if language in SUPPORTED_LANGUAGES else default
