from langdetect import detect

from app.config import get_settings
from app.models.course import Course


_LANG_NAMES = {
    "da": "dansk",
    "en": "engelsk",
}


class CourseQAError(RuntimeError):
    """Raised when a course answer cannot be obtained from Groq."""


def _detect_language(text: str) -> str:
    try:
        lang = detect(text)
        if lang in _LANG_NAMES:
            return lang
        return "en"  # fallback til engelsk
    except Exception:
        return "en"


def _build_system_prompt(course: Course, language: str) -> str:
    if language == "da":
        lang_instruction = "DU SKAL SVARE PÅ DANSK"
    elif language == "en":
        lang_instruction = "DU SKAL SVARE PÅ ENGLSK"
    else:
        lang_instruction = "DU SKAL SVARE PÅ ENGLSK"

    prompt = (
        "Du er en hjælpende kursusguide for DTU-studerende.\n\n"
        f"{lang_instruction}. Brug kun de oplyste kursuselementer til at besvare spørgsmålet.\n"
        "Hvis et felt ikke er relevant for spørgsmålet, så sig det kort og præcist.\n"
        "Svar kort og præcist — højst 3 sætninger.\n\n"
        "Kursusdata:\n"
    )

    fields = []
    for field_name in [
        "course_number", "title", "title_da", "title_en", "ects", "level",
        "course_type", "language", "department", "period", "schedule",
        "campus", "prerequisites", "mandatory_prerequisites", "exam",
        "evaluation", "description", "content", "learning_objectives",
        "course_responsible", "teachers", "source_url",
    ]:
        value = getattr(course, field_name, None)
        if value is not None:
            fields.append(f"{field_name}: {value}")
    course_info = "\n".join(fields)
    return f"{prompt}{course_info}"


def answer_course_question(course: Course, question: str) -> str:
    settings = get_settings()
    if not settings.groq_api_key:
        raise CourseQAError("GROQ_API_KEY is not configured")

    from openai import OpenAI, OpenAIError

    language = _detect_language(question)

    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        timeout=20.0,
        max_retries=1,
    )

    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": _build_system_prompt(course, language)},
                {"role": "user", "content": question},
            ],
            temperature=settings.groq_temperature,
            max_tokens=500,
        )
    except OpenAIError as exc:
        raise CourseQAError("Groq request failed") from exc

    content = response.choices[0].message.content if response.choices else None
    if not content or not content.strip():
        raise CourseQAError("Groq returned an empty answer")
    return content.strip()
