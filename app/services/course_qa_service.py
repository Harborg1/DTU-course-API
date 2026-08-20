from langdetect import detect

from app.config import get_settings
from app.models.course import Course


_LANG_NAMES = {
    "da": "dansk",
    "en": "engelsk",
    "de": "tysk",
    "fr": "fransk",
    "es": "spansk",
    "sv": "svensk",
    "no": "norsk",
    "nl": "hollandsk",
    "fi": "finsk",
}


class CourseQAError(RuntimeError):
    """Raised when a course answer cannot be obtained from Groq."""


def _detect_language(text: str) -> str:
    try:
        return detect(text)
    except Exception:
        return "da"


def _build_system_prompt(course: Course, language: str) -> str:
    lang_name = _LANG_NAMES.get(language, "sproget")

    prompt = (
        "Du er en hjælpende kursusguide for DTU-studerende. "
        f"Svar på {lang_name}. Brug kun de oplyste kursuselementer til at besvare spørgsmål. "
        "Hvis et felt ikke er relevant for spørgsmålet, eller hvis du ikke kan besvare "
        "spørgsmålet baseret på de oplyste elementer, så sig det kort og præcist. "
        "Svar kort og præcist — højst 3 sætninger."
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
    return f"{prompt}\n\nKursusdata:\n{course_info}"


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
