from langdetect import detect


SUPPORTED_LANGUAGES = {"da", "en"}


def detect_user_language(text: str, *, default: str = "en") -> str:
    try:
        language = detect(text)
    except Exception:
        return default
    return language if language in SUPPORTED_LANGUAGES else default
