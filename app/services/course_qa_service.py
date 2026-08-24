"""
Course Q&A service with Groq Responses API and remote MCP tools.

This service replaces the old subprocess-based MCP implementation with
a clean Groq Responses API integration. Groq calls the MCP server
directly via Streamable HTTP.
"""

import logging

from app.config import get_settings
from app.models.course import Course
from app.services.language_service import detect_user_language


logger = logging.getLogger(__name__)

class CourseQAError(RuntimeError):
    """Raised when a course answer cannot be obtained from Groq."""


def _detect_language(text: str) -> str:
    return detect_user_language(text)


# ---------------------------------------------------------------------------
# Remote MCP with Groq Responses API
# ---------------------------------------------------------------------------


def _build_system_prompt(language: str, academic_year: str) -> str:
    """Build system prompt for Groq with language instruction."""
    if language == "da":
        lang_instruction = "DU SKAL SVARE PÅ DANSK"
    elif language == "en":
        lang_instruction = "DU SKAL SVARE PÅ ENGLSK"
    else:
        lang_instruction = "DU SKAL SVARE PÅ ENGLSK"

    return (
        "Du er en hjælpende DTU-studeguide for studerende ved Danmarks Tekniske Universitet.\n\n"
        f"{lang_instruction}.\n\n"
        "Du har adgang til databasen via værktøjer, der automatisk kaldes når nødvendigt.\n"
        f"Brug studieåret {academic_year}, medmindre brugeren udtrykkeligt angiver et andet.\n"
        f"Når du kalder search_courses, skal search_language være '{language}'.\n"
        f"Når du kalder get_course, skal response_language være '{language}'.\n"
        "Brug altid værktøjerne til at hente fakta fra databasen — gæt aldrig data.\n"
        "Brug get_specializations til spørgsmål om specialiseringer og deres kursuskrav.\n"
        "Besvar kun på baggrund af data fra værktøjerne.\n"
        "Hvis et værktøj returnerer en fejl, forklar det kort til brugeren.\n"
        "Svar kort og præcist — højst 3 sætninger.\n"
    )


def answer_with_remote_mcp(question: str, academic_year: str | None = None) -> str:
    """Answer using Groq Responses API with remote MCP tools.

    Groq decides which tool to call, the MCP server executes it via
    Streamable HTTP, results are passed back to Groq for natural
    language response.
    """
    settings = get_settings()
    if not settings.groq_api_key:
        raise CourseQAError("GROQ_API_KEY is not configured")

    if not settings.mcp_server_url:
        raise CourseQAError("MCP_SERVER_URL is not configured")

    if not settings.mcp_token:
        raise CourseQAError("MCP_TOKEN is not configured")

    from openai import OpenAI, OpenAIError

    language = _detect_language(question)
    selected_academic_year = academic_year or settings.default_academic_year
    endpoint = settings.mcp_server_url.rstrip("/")
    if not endpoint.endswith("/mcp"):
        endpoint += "/mcp"

    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        timeout=30.0,
        max_retries=1,
    )

    # Remote MCP tool definition — Groq contacts the server directly
    tools = [
        {
            "type": "mcp",
            "server_label": "dtu_courses",
            "server_url": endpoint,
            "headers": {"Authorization": f"Bearer {settings.mcp_token}"},
            "server_description": "Read-only access to official DTU courses, study plans, and specializations.",
            "allowed_tools": ["get_course", "search_courses", "get_study_plan", "get_specializations"],
            "require_approval": "never",
        }
    ]

    try:
        response = client.responses.create(
            model=settings.groq_model,
            instructions=_build_system_prompt(language, selected_academic_year),
            input=question,
            tools=tools,
            temperature=settings.groq_temperature,
            max_output_tokens=1000,
            max_tool_calls=3,
        )
    except OpenAIError as exc:
        logger.exception("Groq Responses API request failed")
        raise CourseQAError("Groq request failed") from exc

    # Extract final text output from response
    if not response.output:
        raise CourseQAError("Groq returned no output")

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    text_parts = []
    for item in response.output:
        if hasattr(item, "content") and item.content:
            for content in item.content:
                if hasattr(content, "text") and content.text:
                    text_parts.append(content.text)

    content = " ".join(text_parts).strip()
    if not content:
        raise CourseQAError("Groq returned an empty answer")

    return content


# ---------------------------------------------------------------------------
# Backwards compatibility — direct course Q&A (no MCP)
# ---------------------------------------------------------------------------


def _build_system_prompt_direct(course: Course, language: str) -> str:
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
    """Legacy — direct course Q&A without MCP (used as fallback)."""
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
                {"role": "system", "content": _build_system_prompt_direct(course, language)},
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
