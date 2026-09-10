"""
Course Q&A service with Groq Responses API and remote MCP tools.

This service replaces the old subprocess-based MCP implementation with
a clean Groq Responses API integration. Groq calls the MCP server
directly via Streamable HTTP.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.models.course import Course
from app.services.language_service import detect_user_language


logger = logging.getLogger(__name__)


class CourseQAError(RuntimeError):
    """Raised when a course answer cannot be obtained from Groq."""

    def __init__(self, message: str, *, code: str = "unavailable") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class MCPToolResult:
    name: str
    arguments: dict[str, Any]
    data: dict[str, Any]


@dataclass
class MCPAnswer:
    reply: str
    tool_results: list[MCPToolResult] = field(default_factory=list)


def _tool_results(output: list) -> list[MCPToolResult]:
    """Read factual results, never assistant-generated JSON, for UI cards."""
    results = []
    for item in output:
        if getattr(item, "type", None) != "mcp_call" or getattr(item, "error", None):
            continue
        try:
            data = json.loads(item.output)
            arguments = json.loads(item.arguments)
            if isinstance(data, dict) and data.get("isError"):
                continue
            if isinstance(data, dict) and "content" in data:
                data = json.loads(next(
                    block["text"] for block in data["content"] if block.get("type") == "text"
                ))
        except (ValueError, TypeError, KeyError, AttributeError, StopIteration):
            continue
        if isinstance(data, dict) and isinstance(arguments, dict) and "error" not in data:
            results.append(MCPToolResult(name=item.name, arguments=arguments, data=data))
    return results


def _detect_language(text: str) -> str:
    return detect_user_language(text)


# ---------------------------------------------------------------------------
# Remote MCP with Groq Responses API
# ---------------------------------------------------------------------------


def _build_system_prompt(language: str, academic_year: str) -> str:
    """Build system prompt for Groq with language instruction."""
    if language == "da":
        lang_instruction = (
            "DU SKAL SVARE UDELUKKENDE PÅ DANSK. Bevar officielle engelske kursus- og "
            "studieprogramnavne, men skriv alle forklaringer, overskrifter og overgange på dansk"
        )
    elif language == "en":
        lang_instruction = "DU SKAL SVARE PÅ ENGLSK"
    else:
        lang_instruction = "DU SKAL SVARE PÅ ENGLSK"

    return (
        "Du er en hjælpende DTU-studeguide for studerende ved Danmarks Tekniske Universitet.\n\n"
        f"{lang_instruction}.\n\n"
        "Du har adgang til en række skrivebeskyttede databaseværktøjer. Vælg selv, om et "
        "spørgsmål kræver værktøjer, hvilke værktøjer der er relevante, og hvor mange kald "
        "der er nødvendige for et fyldestgørende svar. Du må også svare uden værktøjskald, "
        "når spørgsmålet ikke kræver konkrete DTU-data.\n"
        f"Brug studieåret {academic_year}, medmindre brugeren udtrykkeligt angiver et andet.\n"
        f"Når et valgt værktøj har sprogfeltet, skal search_language være '{language}' "
        f"og response_language være '{language}'. Lad q være et kort, kanonisk engelsk emne; "
        "sprogfeltet styrer sproget i de returnerede tekster.\n"
        "Konkrete DTU-fakta skal verificeres med de tilgængelige værktøjer — gæt aldrig data.\n"
        "Specialiseringer er valgfrie studieveje. Beskriv aldrig en specialiserings kursuspulje som "
        "obligatorisk for alle på programmet; respekter de returnerede requirement-roller.\n"
        "Forstå hele brugerens spørgsmål, og besvar det direkte med en begrundet vurdering. "
        "Du må ræsonnere over brugerens interesser og de hentede oplysninger. Skeln mellem "
        "dokumenterede DTU-fakta og din egen foreløbige anbefaling; opfind aldrig uddannelser, "
        "kursusindhold, adgangskrav eller kildelinks.\n"
        "Værktøjsopslag er baggrund for svaret, ikke automatisk anbefalinger til brugeren. "
        "Vis kun de kurser, uddannelser og kildelinks, der er relevante for det aktuelle spørgsmål. "
        "Ved spørgsmål om kursusrækkefølge eller forudsætninger: fokuser på de nævnte kurser "
        "og deres anbefalede eller obligatoriske forudsætninger; tilføj ikke en generel "
        "kursusliste eller en uddannelsesanbefaling. Der vises ingen automatiske resultatkort "
        "efter dit svar, så medtag relevante resultater og deres officielle links i selve svaret, "
        "når brugeren beder om en søgning eller anbefaling.\n"
        "Ved valg mellem uddannelser: indhent tilstrækkelige officielle oplysninger om hver relevant "
        "uddannelse, sammenhold deres indhold med brugerens interesser, og forklar hvad der taler for hvert valg. "
        "Start med din vurdering, når der er grundlag for den. Hvis et navn er tvetydigt eller "
        "ikke findes, forklar usikkerheden uden at opfinde et officielt match.\n"
        "Et kursussøgeresultat beviser IKKE, at et kursus indgår i en bestemt uddannelse, "
        "er et kernefag eller kan vælges som valgfag. Kun studieplanens krav kan dokumentere "
        "den slags tilknytning. Uden en matchende studieplan: giv en generel, tydeligt "
        "foreløbig faglig vurdering og forklar at DTU-uddannelsen ikke er verificeret. "
        "Udled aldrig uddannelsens niveau fra niveauet på enkelte kurser. "
        "En pulje med valgmuligheder betyder ikke, at hvert kursus er obligatorisk. "
        "Bevar forskellen på obligatoriske kurser og krav om at vælge fra en pulje. "
        "Påstande om løn, jobmuligheder og adgang til videre uddannelse kræver også belæg; "
        "lad være med at tilføje dem alene ud fra kursustitler.\n"
        "Bed kun om afklaring, når manglende oplysninger væsentligt hindrer et nyttigt svar. "
        "Et spørgsmål om at studere X eller Y handler allerede om uddannelsesvalg; spørg ikke "
        "om brugeren mener kurser eller uddannelser. En kort interesse kan mødes med en nyttig "
        "indledende vurdering og et relevant opfølgende spørgsmål.\n"
        "Tidligere bruger- og assistentbeskeder er samtalehistorik. Besvar den seneste "
        "brugerbesked, brug historikken til referencer og præferencer, og følg eksplicitte emneskift. "
        "Tidligere assistentsvar og oplysninger fra brugeren er ikke verificerede DTU-kilder.\n"
        "Hilsner og generel vejledning kræver ikke værktøjskald. Konkrete DTU-oplysninger "
        "skal bygge på værktøjsdata. Henvis til de returnerede officielle kildelinks.\n"
        "Ved kursussøgning: respekter niveau, ECTS, undervisningssprog og periode. "
        "Brug result_mode='summary' til almindelige søgninger og anbefalinger. Brug kun "
        "result_mode='all', når brugeren udtrykkeligt beder om alle eller en komplet liste. "
        "Et all-resultat med next_offset er ikke en komplet liste; hent da de nødvendige sider, "
        "indtil next_offset er null. Kald aldrig en begrænset liste komplet.\n"
        "Hvis et værktøj returnerer en fejl, forklar det kort til brugeren.\n"
        "Never format course results as Markdown tables.\n"
        "The chat displays plain text. Avoid Markdown tables, heading markers, bold markers "
        "and invented citation markers. Use paragraphs and simple bullet lists, with official "
        "source URLs returned by tools when available.\n"
        "Present courses as a readable bullet list.\n"
        "Put the course number and title on the first line and ECTS and level on the following line.\n"
        "Do not place multiple courses on the same line.\n"
        "Always sort every course list by course number in ascending order before presenting it.\n"
        "Tilpas længden til spørgsmålet: korte svar til enkle spørgsmål og udførlige "
        "forklaringer til sammenligninger og studievejledning. Et enkelt spørgsmål om "
        "hvilken uddannelse der passer bedst bør normalt besvares i nogle få afsnit med "
        "de vigtigste forskelle; undlad lange kursuskataloger, medmindre brugeren beder om dem. "
        "Undgå fyld.\n"
    )


def answer_with_remote_mcp(
    question: str,
    academic_year: str | None = None,
    *,
    response_language: str | None = None,
) -> str:
    """Compatibility wrapper for services that only need the answer text."""
    return respond_with_remote_mcp(
        question, academic_year, response_language=response_language,
    ).reply


def respond_with_remote_mcp(
    question: str,
    academic_year: str | None = None,
    *,
    response_language: str | None = None,
    messages: list[dict[str, str]] | None = None,
) -> MCPAnswer:
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

    from openai import APITimeoutError, OpenAI, OpenAIError

    language = response_language if response_language in {"da", "en"} else _detect_language(question)
    selected_academic_year = academic_year or settings.default_academic_year
    endpoint = settings.mcp_server_url.rstrip("/")
    if not endpoint.endswith("/mcp"):
        endpoint += "/mcp"

    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        timeout=settings.chat_timeout,
        max_retries=0,
    )

    # Remote MCP tool definition — Groq contacts the server directly
    tools = [
        {
            "type": "mcp",
            "server_label": "dtu_courses",
            "server_url": endpoint,
            "headers": {"Authorization": f"Bearer {settings.mcp_token}"},
            "server_description": "Read-only access to official DTU courses, study plans, and specializations.",
            "allowed_tools": [
                "get_course",
                "get_courses",
                "search_courses",
                "get_new_courses",
                "get_study_plan",
                "get_specializations",
            ],
            "require_approval": "never",
        }
    ]

    try:
        response = client.responses.create(
            model=settings.groq_model,
            instructions=_build_system_prompt(language, selected_academic_year),
            input=messages if messages is not None else question,
            tools=tools,
            tool_choice="auto",
            temperature=settings.groq_temperature,
            max_output_tokens=settings.chat_max_output_tokens,
        )
    except OpenAIError as exc:
        error_code = "timeout" if isinstance(exc, APITimeoutError) else "upstream"
        logger.exception(
            "Groq Responses API request failed error_type=%s",
            type(exc).__name__,
        )
        raise CourseQAError("Groq request failed", code=error_code) from exc

    output = response.output or []
    status = getattr(response, "status", None)
    response_id = getattr(response, "id", None)
    tool_names = [
        item.name
        for item in output
        if getattr(item, "type", None) == "mcp_call" and getattr(item, "name", None)
    ]
    logger.info(
        "Groq Responses API completed response_id=%s status=%s mcp_call_count=%d mcp_tools=%s",
        response_id,
        status,
        len(tool_names),
        tool_names,
    )

    if status == "incomplete":
        details = getattr(response, "incomplete_details", None)
        reason = details.get("reason") if isinstance(details, dict) else getattr(details, "reason", None)
        reason = reason or "unknown"
        logger.warning(
            "Groq response incomplete response_id=%s reason=%s mcp_call_count=%d mcp_tools=%s",
            response_id,
            reason,
            len(tool_names),
            tool_names,
        )
        raise CourseQAError(f"Groq response was incomplete: {reason}", code="incomplete")

    if status in {"failed", "cancelled"}:
        logger.error("Groq response ended with status=%s response_id=%s", status, response_id)
        raise CourseQAError(f"Groq response status was {status}", code="upstream")

    # Extract final text output from response
    if not output:
        logger.error("Groq returned no output response_id=%s status=%s", response_id, status)
        raise CourseQAError("Groq returned no output", code="empty")

    tool_results = _tool_results(output)
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return MCPAnswer(reply=output_text.strip(), tool_results=tool_results)

    text_parts = []
    for item in output:
        if hasattr(item, "content") and item.content:
            for content in item.content:
                if hasattr(content, "text") and content.text:
                    text_parts.append(content.text)

    content = " ".join(text_parts).strip()
    if not content:
        logger.error("Groq returned an empty answer response_id=%s status=%s", response_id, status)
        raise CourseQAError("Groq returned an empty answer", code="empty")

    return MCPAnswer(reply=content, tool_results=tool_results)


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
