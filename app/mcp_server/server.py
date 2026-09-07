"""
Remote MCP server with Streamable HTTP transport.

Exposes read-only database tools for courses, catalogue changes, study plans,
and specializations at the /mcp endpoint on the FastAPI application.
All tools use the existing SQLAlchemy session factory and always
require an academic_year parameter.

Built with the official MCP Python SDK (mcp >= 1.0.0).
Stateless — suitable for serverless deployments.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from mcp.server import Server
from mcp.server.request_state import ServerRequestContext
from mcp.server.streamable_http import TransportSecuritySettings
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    Tool,
)
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_ACADEMIC_YEAR_PATTERN = re.compile(r"^(\d{4})-(\d{4})$")

# ---------------------------------------------------------------------------
# Tool schemas (MCP inputSchema)
# ---------------------------------------------------------------------------

_GET_COURSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "course_number": {
            "type": "string",
            "description": "The 5-digit course number (e.g. '02150')",
            "pattern": "^[0-9]{5}$",
        },
        "academic_year": {
            "type": "string",
            "description": "Academic year filter (e.g. '2026-2027')",
            "pattern": "^[0-9]{4}-[0-9]{4}$",
        },
        "response_language": {
            "type": "string",
            "description": "Preferred response language; use 'da' for Danish and 'en' for English",
            "enum": ["da", "en"],
        },
    },
    "required": ["course_number", "academic_year"],
}

_SEARCH_COURSES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "q": {
            "type": "string",
            "description": "Search keyword or phrase",
        },
        "academic_year": {
            "type": "string",
            "description": "Academic year filter (e.g. '2026-2027')",
            "pattern": "^[0-9]{4}-[0-9]{4}$",
        },
        "search_language": {
            "type": "string",
            "description": "Language for returned titles and descriptions; use 'da' or 'en'",
            "enum": ["da", "en"],
        },
        "level": {
            "type": "string",
            "description": "Course level filter (e.g. 'BSc', 'MSc', 'PhD')",
        },
        "ects": {
            "type": "number",
            "description": "Filter by ECTS credits (e.g. 5, 7.5, 10)",
            "exclusiveMinimum": 0,
            "maximum": 120,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of results to return (max 20)",
            "minimum": 1,
            "maximum": 20,
        },
    },
    "required": ["q", "academic_year", "search_language"],
}

_GET_NEW_COURSES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "academic_year": {
            "type": "string",
            "description": "The newer academic year to inspect (e.g. '2026-2027')",
            "pattern": "^[0-9]{4}-[0-9]{4}$",
        },
        "previous_academic_year": {
            "type": "string",
            "description": "Optional comparison year; defaults to the immediately preceding academic year",
            "pattern": "^[0-9]{4}-[0-9]{4}$",
        },
        "response_language": {
            "type": "string",
            "description": "Language for returned titles; use 'da' or 'en'",
            "enum": ["da", "en"],
        },
        "level": {
            "type": "string",
            "description": "Optional course level filter",
            "enum": ["BSc", "MSc", "PhD"],
        },
        "q": {
            "type": "string",
            "description": "Optional subject keyword or phrase, preferably canonical English",
        },
        "ects": {
            "type": "number",
            "description": "Optional exact ECTS filter (e.g. 5, 7.5, 10)",
            "exclusiveMinimum": 0,
            "maximum": 120,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of course entries to return (max 200)",
            "minimum": 1,
            "maximum": 200,
        },
    },
    "required": ["academic_year", "response_language"],
}

_GET_STUDY_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "program_name": {
            "type": "string",
            "description": "Name of the study program (e.g. 'Software Technology')",
        },
        "academic_year": {
            "type": "string",
            "description": "Academic year filter (e.g. '2026-2027')",
            "pattern": "^[0-9]{4}-[0-9]{4}$",
        },
        "degree_type": {
            "type": "string",
            "description": "Optional degree type, normally Bachelor or Master",
            "enum": ["Bachelor", "Master"],
        },
    },
    "required": ["program_name", "academic_year"],
}

_GET_SPECIALIZATIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "program_name": {
            "type": "string",
            "description": "Name of the MSc study program (e.g. 'Computer Science and Engineering')",
        },
        "specialization_name": {
            "type": "string",
            "description": "Optional specialization name; omit it to list every specialization for the program",
        },
        "academic_year": {
            "type": "string",
            "description": "Academic year used to select the imported study program (e.g. '2026-2027')",
            "pattern": "^[0-9]{4}-[0-9]{4}$",
        },
    },
    "required": ["program_name", "academic_year"],
}

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_COURSE_TOOL = Tool(
    name="get_course",
    description=(
        "Get details for a single DTU course by its 5-digit course number. "
        "Returns course information including title, ECTS, level, description, "
        "prerequisites, and more."
    ),
    inputSchema=_GET_COURSE_SCHEMA,
)

_SEARCH_COURSES_TOOL = Tool(
    name="search_courses",
    description=(
        "Search for DTU courses by keyword and optional filters. "
        "Searches both Danish and English course text, merges duplicate courses, and uses "
        "search_language only to select the language of returned titles and descriptions. "
        "Returns the selected matching courses in ascending course-number order, "
        "with localized titles and descriptions."
    ),
    inputSchema=_SEARCH_COURSES_SCHEMA,
)

_GET_NEW_COURSES_TOOL = Tool(
    name="get_new_courses",
    description=(
        "Compare two imported DTU course catalogues and list courses whose number is absent "
        "from the previous year. Uses DTU PreviousCourse metadata to distinguish courses that "
        "received a new number from courses that were newly created. Can filter the result by "
        "subject keyword, exact ECTS credits, and course level."
    ),
    inputSchema=_GET_NEW_COURSES_SCHEMA,
)

_GET_STUDY_PLAN_TOOL = Tool(
    name="get_study_plan",
    description=(
        "Get the full study plan for a DTU study program. "
        "Returns sections, requirements, courses, and ECTS breakdown."
    ),
    inputSchema=_GET_STUDY_PLAN_SCHEMA,
)

_GET_SPECIALIZATIONS_TOOL = Tool(
    name="get_specializations",
    description=(
        "List optional official DTU specialization paths for an MSc program, or get the structured course "
        "requirements for one named specialization. A specialization's requirements are not automatically "
        "mandatory for every student in the programme. Distinguishes mandatory, choice, recommended, and "
        "historical courses."
    ),
    inputSchema=_GET_SPECIALIZATIONS_SCHEMA,
)

ALL_TOOLS: list[Tool] = [
    _COURSE_TOOL,
    _SEARCH_COURSES_TOOL,
    _GET_NEW_COURSES_TOOL,
    _GET_STUDY_PLAN_TOOL,
    _GET_SPECIALIZATIONS_TOOL,
]

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _academic_year(arguments: dict[str, Any]) -> str | None:
    value = str(arguments.get("academic_year", "")).strip()
    match = _ACADEMIC_YEAR_PATTERN.fullmatch(value)
    if not match or int(match.group(2)) != int(match.group(1)) + 1:
        return None
    return value


def _handle_get_course(arguments: dict[str, Any]) -> dict[str, Any]:
    course_number = str(arguments.get("course_number", "")).strip()
    if not course_number or len(course_number) != 5 or not course_number.isdigit():
        return {"error": "course_number must be exactly 5 digits"}
    academic_year = _academic_year(arguments)
    if academic_year is None:
        return {"error": "academic_year must contain consecutive years, e.g. 2026-2027"}

    from app.database import SessionLocal
    from app.models.course import Course
    from sqlalchemy import select

    session = SessionLocal()
    try:
        course = session.execute(
            select(Course).where(
                Course.course_number == course_number,
                Course.academic_year == academic_year,
            )
        ).scalar_one_or_none()

        if not course:
            return {"error": f"Course {course_number} not found in {academic_year}"}

        response_language = arguments.get("response_language")
        if response_language == "da":
            localized_title = course.title_da or course.title_en or course.title
            localized_description = course.description_da or course.description_en or course.description
            localized_content = course.content_da or course.content_en or course.content
            localized_objectives = course.learning_objectives_da or course.learning_objectives_en or course.learning_objectives
            localized_prerequisites = course.prerequisites_da or course.prerequisites_en or course.prerequisites
        else:
            localized_title = course.title_en or course.title_da or course.title
            localized_description = course.description_en or course.description_da or course.description
            localized_content = course.content_en or course.content_da or course.content
            localized_objectives = course.learning_objectives_en or course.learning_objectives_da or course.learning_objectives
            localized_prerequisites = course.prerequisites_en or course.prerequisites_da or course.prerequisites

        return {
            "course_number": course.course_number,
            "title": localized_title,
            "title_da": course.title_da,
            "title_en": course.title_en,
            "ects": float(course.ects) if course.ects else None,
            "level": course.level,
            "course_type": course.course_type,
            "language": course.language,
            "department": course.department,
            "period": course.period,
            "schedule": course.schedule,
            "campus": course.campus,
            "prerequisites": localized_prerequisites,
            "recommended_prerequisite_course_numbers": (
                course.recommended_prerequisite_course_numbers
            ),
            "mandatory_prerequisites": course.mandatory_prerequisites,
            "exam": course.exam,
            "evaluation": course.evaluation,
            "description": localized_description,
            "content": localized_content,
            "learning_objectives": localized_objectives,
            "course_responsible": course.course_responsible,
            "teachers": course.teachers,
            "responsible_people": course.responsible_people,
            "previous_course_numbers": course.previous_course_numbers,
            "source_url": course.source_url,
        }
    finally:
        session.close()


def _handle_search_courses(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("q", "")).strip()
    academic_year = _academic_year(arguments)
    if academic_year is None:
        return {"error": "academic_year must contain consecutive years, e.g. 2026-2027"}
    level = arguments.get("level")
    search_language = arguments.get("search_language")
    if search_language not in {"da", "en"}:
        return {"error": "search_language must be 'da' or 'en'"}
    try:
        limit = max(1, min(int(arguments.get("limit", 10)), 20))
    except (TypeError, ValueError):
        return {"error": "limit must be an integer between 1 and 20"}
    try:
        ects = Decimal(str(arguments["ects"])) if arguments.get("ects") is not None else None
    except (InvalidOperation, ValueError):
        return {"error": "ects must be a number"}
    if ects is not None and not Decimal("0") < ects <= Decimal("120"):
        return {"error": "ects must be greater than 0 and at most 120"}

    from app.database import SessionLocal
    from app.services.search_service import search_courses

    session = SessionLocal()
    try:
        result = search_courses(
            session=session,
            q=query,
            academic_year=academic_year,
            ects=ects,
            level=level,
            period=None,
            language=None,
            search_language=search_language,
            search_all_languages=True,
            limit=limit,
            offset=0,
        )

        selected_courses = sorted(
            result.courses[:limit],
            key=lambda item: item[0].course_number.casefold(),
        )
        courses = [
            {
                "course_number": course.course_number,
                "title": (
                    course.title_da or course.title_en or course.title
                    if search_language == "da"
                    else course.title_en or course.title_da or course.title
                ),
                "description": (
                    course.description_da or course.description_en or course.description
                    if search_language == "da"
                    else course.description_en or course.description_da or course.description
                ),
                "ects": float(course.ects) if course.ects else None,
                "level": course.level,
                "source_url": course.source_url,
            }
            for course, _score in selected_courses
        ]

        return {
            "query": query,
            "search_language": search_language,
            "count": result.count,
            "returned": len(courses),
            "courses": courses,
        }
    finally:
        session.close()


def _handle_get_new_courses(arguments: dict[str, Any]) -> dict[str, Any]:
    academic_year = _academic_year(arguments)
    if academic_year is None:
        return {"error": "academic_year must contain consecutive years, e.g. 2026-2027"}
    response_language = arguments.get("response_language")
    if response_language not in {"da", "en"}:
        return {"error": "response_language must be 'da' or 'en'"}
    level = arguments.get("level")
    if level not in {None, "BSc", "MSc", "PhD"}:
        return {"error": "level must be BSc, MSc, or PhD"}
    query = str(arguments.get("q") or "").strip()
    try:
        ects = Decimal(str(arguments["ects"])) if arguments.get("ects") is not None else None
    except (InvalidOperation, ValueError):
        return {"error": "ects must be a number"}
    if ects is not None and not Decimal("0") < ects <= Decimal("120"):
        return {"error": "ects must be greater than 0 and at most 120"}
    previous_academic_year = None
    if arguments.get("previous_academic_year") is not None:
        previous_academic_year = _academic_year(
            {"academic_year": arguments["previous_academic_year"]}
        )
        if previous_academic_year is None:
            return {
                "error": "previous_academic_year must contain consecutive years, e.g. 2025-2026"
            }
    try:
        limit = max(1, min(int(arguments.get("limit", 200)), 200))
    except (TypeError, ValueError):
        return {"error": "limit must be an integer between 1 and 200"}

    from app.database import SessionLocal
    from app.services.course_change_service import CatalogComparisonError, get_new_courses

    session = SessionLocal()
    try:
        try:
            result = get_new_courses(
                session,
                academic_year,
                previous_academic_year,
                level=level,
                topic=query or None,
                ects=ects,
            )
        except CatalogComparisonError as exc:
            return {"error": str(exc)}

        courses = []
        for item in result.courses[:limit]:
            course = item.course
            title = (
                course.title_da or course.title_en or course.title
                if response_language == "da"
                else course.title_en or course.title_da or course.title
            )
            courses.append(
                {
                    "course_number": course.course_number,
                    "title": title,
                    "ects": float(course.ects) if course.ects is not None else None,
                    "level": course.level,
                    "classification": item.classification,
                    "previous_course_numbers": list(item.previous_course_numbers),
                    "source_url": course.source_url,
                }
            )
        return {
            "academic_year": result.academic_year,
            "previous_academic_year": result.previous_academic_year,
            "level": result.level,
            "query": result.topic,
            "ects": float(result.ects) if result.ects is not None else None,
            "total": len(result.courses),
            "created_count": result.created_count,
            "renumbered_count": result.renumbered_count,
            "returned": len(courses),
            "courses": courses,
        }
    finally:
        session.close()


def _handle_get_study_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    program_name = str(arguments.get("program_name", "")).strip()
    if not program_name:
        return {"error": "program_name is required"}
    academic_year = _academic_year(arguments)
    if academic_year is None:
        return {"error": "academic_year must contain consecutive years, e.g. 2026-2027"}
    degree_type = arguments.get("degree_type")
    if degree_type not in (None, "Bachelor", "Master"):
        return {"error": "degree_type must be Bachelor or Master"}

    from app.database import SessionLocal
    from app.models.study_plan import StudyPlanRequirement, StudyPlanRequirementCourse, StudyPlanSection, StudyProgram
    from sqlalchemy import and_, func, or_, select
    from sqlalchemy.orm import selectinload

    session = SessionLocal()
    try:
        start_year = int(academic_year[:4])
        year_filter = or_(
            StudyProgram.academic_year == academic_year,
            and_(
                StudyProgram.academic_year.is_(None),
                or_(StudyProgram.valid_from_year.is_(None), StudyProgram.valid_from_year <= start_year),
                or_(StudyProgram.valid_to_year.is_(None), StudyProgram.valid_to_year >= start_year),
            ),
        )
        filters = [year_filter]
        if degree_type:
            filters.append(StudyProgram.degree_type == degree_type)
        options = (
            selectinload(StudyProgram.sections).selectinload(StudyPlanSection.courses),
            selectinload(StudyProgram.sections)
            .selectinload(StudyPlanSection.requirements)
            .selectinload(StudyPlanRequirement.course_links)
            .selectinload(StudyPlanRequirementCourse.course),
        )

        exact = select(StudyProgram).where(
            *filters, func.lower(StudyProgram.name) == program_name.casefold()
        ).options(*options)
        programs = list(session.scalars(exact).unique())
        if not programs:
            partial = select(StudyProgram).where(
                *filters, StudyProgram.name.ilike(f"%{program_name}%")
            ).options(*options).limit(3)
            programs = list(session.scalars(partial).unique())

        if len(programs) > 1:
            return {
                "error": "Study program name is ambiguous",
                "matches": [program.name for program in programs],
            }
        program = programs[0] if programs else None

        if not program:
            return {"error": "Study program not found"}

        sections = []
        for section in program.sections:
            section_data = {
                "name": section.name,
                "description": section.description,
                "courses": [
                    {
                        "course_number": c.course_number,
                        "title": c.title,
                        "ects": float(c.ects) if c.ects else None,
                        "requirement_role": c.requirement_role,
                    }
                    for c in section.courses
                ],
                "requirements": [
                    {
                        "requirement_type": r.requirement_type,
                        "description": r.description,
                        "required_ects": float(r.required_ects) if r.required_ects else None,
                        "required_count": r.required_count,
                        "courses": [
                            {
                                "course_number": link.course.course_number,
                                "title": link.course.title,
                            }
                            for link in r.course_links
                        ],
                    }
                    for r in section.requirements
                ],
            }
            sections.append(section_data)

        return {
            "program_name": program.name,
            "degree_type": program.degree_type,
            "academic_year": program.academic_year or academic_year,
            "sections": sections,
        }
    finally:
        session.close()


def _handle_get_specializations(arguments: dict[str, Any]) -> dict[str, Any]:
    program_name = str(arguments.get("program_name", "")).strip()
    if not program_name:
        return {"error": "program_name is required"}
    academic_year = _academic_year(arguments)
    if academic_year is None:
        return {"error": "academic_year must contain consecutive years, e.g. 2026-2027"}
    specialization_name = str(arguments.get("specialization_name", "")).strip()

    from app.database import SessionLocal
    from app.models.specialization import (
        SpecializationRequirement,
        SpecializationRequirementCourse,
        StudySpecialization,
    )
    from app.models.study_plan import StudyProgram
    from sqlalchemy import and_, func, or_, select
    from sqlalchemy.orm import selectinload

    session = SessionLocal()
    try:
        start_year = int(academic_year[:4])
        year_filter = or_(
            StudyProgram.academic_year == academic_year,
            and_(
                StudyProgram.academic_year.is_(None),
                or_(StudyProgram.valid_from_year.is_(None), StudyProgram.valid_from_year <= start_year),
                or_(StudyProgram.valid_to_year.is_(None), StudyProgram.valid_to_year >= start_year),
            ),
        )
        programs = list(
            session.scalars(
                select(StudyProgram).where(
                    year_filter,
                    StudyProgram.degree_type == "Master",
                    func.lower(StudyProgram.name) == program_name.casefold(),
                )
            )
        )
        if not programs:
            programs = list(
                session.scalars(
                    select(StudyProgram)
                    .where(
                        year_filter,
                        StudyProgram.degree_type == "Master",
                        StudyProgram.name.ilike(f"%{program_name}%"),
                    )
                    .limit(3)
                )
            )
        if len(programs) > 1:
            return {"error": "Study program name is ambiguous", "matches": [item.name for item in programs]}
        if not programs:
            return {"error": "Study program not found"}
        program = programs[0]

        filters = [StudySpecialization.program_id == program.id]
        if specialization_name:
            filters.append(StudySpecialization.name.ilike(f"%{specialization_name}%"))
        options = (
            selectinload(StudySpecialization.courses),
            selectinload(StudySpecialization.requirements)
            .selectinload(SpecializationRequirement.course_links)
            .selectinload(SpecializationRequirementCourse.course),
        )
        specializations = list(
            session.scalars(
                select(StudySpecialization)
                .where(*filters)
                .options(*options)
                .order_by(StudySpecialization.position)
            ).unique()
        )
        if specialization_name and not specializations:
            return {"error": "Specialization not found", "program_name": program.name}

        return {
            "program_name": program.name,
            "academic_year": program.academic_year or academic_year,
            "specializations_are_optional": True,
            "specializations": [
                {
                    "name": specialization.name,
                    "slug": specialization.slug,
                    "is_optional": True,
                    "description": specialization.description,
                    "source_url": specialization.source_url,
                    "requirements": [
                        {
                            "requirement_type": requirement.requirement_type,
                            "description": requirement.description,
                            "required_ects": (
                                float(requirement.required_ects)
                                if requirement.required_ects is not None
                                else None
                            ),
                            "required_count": requirement.required_count,
                            "courses": [
                                {
                                    "course_number": link.course.course_number,
                                    "title": link.course.title,
                                    "ects": float(link.course.ects) if link.course.ects is not None else None,
                                    "role": link.course.role,
                                    "is_terminated": link.course.is_terminated,
                                }
                                for link in sorted(
                                    requirement.course_links, key=lambda item: item.course.position
                                )
                            ],
                        }
                        for requirement in specialization.requirements
                    ],
                }
                for specialization in specializations
            ],
        }
    finally:
        session.close()


_TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "get_course": _handle_get_course,
    "search_courses": _handle_search_courses,
    "get_new_courses": _handle_get_new_courses,
    "get_study_plan": _handle_get_study_plan,
    "get_specializations": _handle_get_specializations,
}


def _json_result(data: dict[str, Any], is_error: bool = False) -> CallToolResult:
    """Build a CallToolResult from a dict."""
    return CallToolResult(
        is_error=is_error,
        content=[
            {
                "type": "text",
                "text": json.dumps(data, ensure_ascii=False),
            }
        ],
    )


# ---------------------------------------------------------------------------
# Callback handlers for Server.__init__
# ---------------------------------------------------------------------------


async def _on_list_tools(
    _ctx: ServerRequestContext[Any, Any],
    _params: PaginatedRequestParams | None,
) -> ListToolsResult:
    return ListToolsResult(tools=ALL_TOOLS)


async def _on_call_tool(
    _ctx: ServerRequestContext[Any, Any],
    params: CallToolRequestParams,
) -> CallToolResult:
    name = params.name
    arguments: dict[str, Any] = params.arguments or {}

    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return _json_result({"error": f"Unknown tool: {name}"}, is_error=True)

    try:
        result = await asyncio.to_thread(handler, arguments)
        return _json_result(result, is_error="error" in result)
    except Exception as exc:
        logger.exception("Tool '%s' failed", name)
        return _json_result({"error": f"Tool execution failed: {exc}"}, is_error=True)


# ---------------------------------------------------------------------------
# MCP transport factory
# ---------------------------------------------------------------------------


class _BearerTokenMiddleware:
    """Minimal constant-time bearer authentication around the MCP ASGI app."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            authorization = headers.get(b"authorization", b"").decode("latin-1")
            scheme, _, supplied_token = authorization.partition(" ")
            if scheme.casefold() != "bearer" or not hmac.compare_digest(supplied_token, self._token):
                response = JSONResponse(
                    {"error": "Unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def transport_security_for_url(server_url: str) -> TransportSecuritySettings:
    """Allow local test hosts plus the exact public hostname configured for Groq."""
    allowed_hosts = ["127.0.0.1:*", "localhost:*", "testserver"]
    allowed_origins = ["http://127.0.0.1:*", "http://localhost:*"]
    parsed = urlsplit(server_url)
    if parsed.netloc:
        allowed_hosts.append(parsed.netloc)
        allowed_origins.append(f"{parsed.scheme}://{parsed.netloc}")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def create_mcp_transport(
    mcp_token: str,
    transport_security: TransportSecuritySettings | None = None,
) -> tuple[ASGIApp, StreamableHTTPSessionManager]:
    """Create a fresh MCP ASGI app and its one-shot session manager.

    Each FastAPI lifespan needs a new transport because the MCP SDK session
    manager deliberately cannot be restarted after shutdown.

    The returned app is configured with:
    - Streamable HTTP transport (stateless for serverless)
    - Bearer token authentication
    - DNS rebinding protection for production

    Parameters
    ----------
    mcp_token:
        The secret token that clients must present as ``Authorization: Bearer``.
    transport_security:
        Optional DNS-rebinding protection settings. Defaults to permissive
        settings for local development (will be overridden in production
        by the ``TransportSecuritySettings`` with allowed hosts).
    """
    server = Server(
        name="dtu_course_api",
        description="Read-only DTU course and study plan database tools.",
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )
    mcp_app = server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=transport_security or transport_security_for_url(""),
    )
    return _BearerTokenMiddleware(mcp_app, mcp_token), server.session_manager
