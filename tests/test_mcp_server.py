"""Tests for the MCP Streamable HTTP server at /mcp.

Covers:
- Authentication (401/403, Bearer token)
- Tool discovery (POST JSON-RPC tools/list)
- Tool calls: get_course, search_courses, get_study_plan, get_specializations
- Input validation (missing fields, invalid course numbers, caps)
- Groq configuration (missing MCP_TOKEN / MCP_SERVER_URL raises CourseQAError)
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
import anyio
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from starlette.applications import Starlette

from app.config import get_settings
from app.database import get_db
from app.main import app


@pytest.fixture
def test_client(db_session):
    """Override DB session for test client."""
    def override_db():
        yield db_session

    mcp_session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    app.dependency_overrides[get_db] = override_db
    with patch("app.database.SessionLocal", mcp_session_factory):
        with TestClient(app) as client:
            yield client
    app.dependency_overrides.clear()


def _auth_headers(token: str | None = None) -> dict[str, str]:
    if token is None:
        token = get_settings().mcp_token
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
    }


def _send_jsonrpc(test_client, method, params=None, request_id=1):
    """Helper to send a JSON-RPC request to the MCP endpoint."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id,
    }
    if params is not None:
        payload["params"] = params
    return test_client.post(
        "/mcp",
        headers=_auth_headers(),
        json=payload,
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_mcp_without_authorization_returns_401(test_client):
    response = test_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
    )
    assert response.status_code in (401, 403)


def test_mcp_with_wrong_token_returns_403(test_client):
    response = test_client.post(
        "/mcp",
        headers=_auth_headers("wrong-token"),
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
    )
    assert response.status_code in (401, 403)


def test_mcp_with_valid_token_succeeds(test_client):
    mcp_token = get_settings().mcp_token
    response = test_client.post(
        "/mcp",
        headers=_auth_headers(mcp_token),
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------


def test_discovery_returns_four_tools(test_client):
    response = _send_jsonrpc(test_client, "tools/list")
    assert response.status_code == 200

    body = response.json()
    tools = body["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    assert tool_names == {"get_course", "search_courses", "get_study_plan", "get_specializations"}


def test_discovery_get_course_schema(test_client):
    response = _send_jsonrpc(test_client, "tools/list")
    body = response.json()
    tools = body["result"]["tools"]
    course_tool = next(t for t in tools if t["name"] == "get_course")
    assert "course_number" in course_tool["inputSchema"]["required"]
    assert "academic_year" in course_tool["inputSchema"]["required"]


def test_discovery_search_courses_schema(test_client):
    response = _send_jsonrpc(test_client, "tools/list")
    body = response.json()
    tools = body["result"]["tools"]
    search_tool = next(t for t in tools if t["name"] == "search_courses")
    assert "q" in search_tool["inputSchema"]["required"]
    assert "academic_year" in search_tool["inputSchema"]["required"]
    assert "level" in search_tool["inputSchema"]["properties"]
    assert "ects" in search_tool["inputSchema"]["properties"]
    assert "search_language" in search_tool["inputSchema"]["required"]


def test_discovery_get_study_plan_schema(test_client):
    response = _send_jsonrpc(test_client, "tools/list")
    body = response.json()
    tools = body["result"]["tools"]
    plan_tool = next(t for t in tools if t["name"] == "get_study_plan")
    assert "program_name" in plan_tool["inputSchema"]["required"]
    assert "academic_year" in plan_tool["inputSchema"]["required"]


def test_discovery_get_specializations_schema(test_client):
    response = _send_jsonrpc(test_client, "tools/list")
    body = response.json()
    tools = body["result"]["tools"]
    specialization_tool = next(t for t in tools if t["name"] == "get_specializations")
    assert "program_name" in specialization_tool["inputSchema"]["required"]
    assert "academic_year" in specialization_tool["inputSchema"]["required"]
    assert "specialization_name" in specialization_tool["inputSchema"]["properties"]


# ---------------------------------------------------------------------------
# get_course tool
# ---------------------------------------------------------------------------


def _make_course(course_number="02450", academic_year="2026-2027", **kwargs):
    from app.models.course import Course, CourseTranslation
    from datetime import datetime, timezone

    defaults = {
        "title": "Introduction to Machine Learning",
        "title_en": "Introduction to Machine Learning",
        "title_da": "Introduktion til Machine Learning",
        "ects": 5,
        "level": "MSc",
        "course_type": "MSc",
        "language": "English",
        "department": "DTU Compute",
        "period": "E",
        "schedule": "E2A",
        "campus": "Campus Lyngby",
        "description": "Supervised learning and model evaluation",
        "description_da": "Datamodellering med beslutningstræer",
        "description_en": "Supervised learning and decision trees",
        "content": "machine learning algorithms",
        "content_da": "Maskinlæringsalgoritmer",
        "content_en": "Machine learning algorithms",
        "source_url": f"https://kurser.dtu.dk/course/{academic_year}/{course_number}",
        "content_hash": "a" * 64,
        "imported_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    translated_fields = (
        "title", "description", "content", "learning_objectives", "prerequisites",
        "mandatory_prerequisites", "teaching_methods", "literature", "remarks",
    )
    translations = {"da": {"language_code": "da-DK"}, "en": {"language_code": "en-GB"}}
    for field in translated_fields:
        generic = defaults.pop(field, None)
        translations["da"][field] = defaults.pop(f"{field}_da", None) or generic
        translations["en"][field] = defaults.pop(f"{field}_en", None) or generic
    defaults["course_number"] = course_number
    defaults["academic_year"] = academic_year
    return Course(
        **defaults,
        translations=[CourseTranslation(**values) for values in translations.values()],
    )


def test_get_course_valid_returns_course_json(test_client, db_session):
    db_session.add(
        _make_course(
            "02450",
            "2026-2027",
            course_responsible="Ada Lovelace",
            teachers="Ada Lovelace, Alan Turing",
            responsible_people=[
                {"name": "Ada Lovelace", "email": "ada@example.com", "primary": True},
                {"name": "Alan Turing", "email": "alan@example.com", "primary": False},
            ],
        )
    )
    db_session.commit()

    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "get_course",
        "arguments": {
            "course_number": "02450",
            "academic_year": "2026-2027",
        },
    })
    assert response.status_code == 200
    body = response.json()
    content = json.loads(body["result"]["content"][0]["text"])
    assert content["course_number"] == "02450"
    assert "title" in content
    assert content["ects"] is not None
    assert content["course_responsible"] == "Ada Lovelace"
    assert content["teachers"] == "Ada Lovelace, Alan Turing"
    assert content["responsible_people"][0]["email"] == "ada@example.com"


def test_get_course_handler_includes_responsible_people_without_http(db_session):
    from sqlalchemy.orm import sessionmaker

    from app.mcp_server.server import _handle_get_course

    db_session.add(
        _make_course(
            "02452",
            "2026-2027",
            course_responsible="Georgios Arvanitidis",
            teachers="Georgios Arvanitidis, Morten Mørup",
            responsible_people=[
                {"name": "Georgios Arvanitidis", "email": "gear@dtu.dk", "primary": True},
                {"name": "Morten Mørup", "email": "mmor@dtu.dk", "primary": False},
            ],
            recommended_prerequisite_course_numbers=["01017", "02101", "02105", "02180"],
        )
    )
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    with patch("app.database.SessionLocal", factory):
        content = _handle_get_course(
            {
                "course_number": "02452",
                "academic_year": "2026-2027",
                "response_language": "da",
            }
        )

    assert content["course_responsible"] == "Georgios Arvanitidis"
    assert content["teachers"] == "Georgios Arvanitidis, Morten Mørup"
    assert content["responsible_people"][1]["email"] == "mmor@dtu.dk"
    assert content["recommended_prerequisite_course_numbers"] == [
        "01017",
        "02101",
        "02105",
        "02180",
    ]


def test_get_course_not_found_returns_error(test_client):
    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "get_course",
        "arguments": {
            "course_number": "99999",
            "academic_year": "2026-2027",
        },
    })
    assert response.status_code == 200
    body = response.json()
    content = json.loads(body["result"]["content"][0]["text"])
    assert "error" in content


def test_get_course_invalid_course_number_returns_error(test_client):
    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "get_course",
        "arguments": {
            "course_number": "abc",
            "academic_year": "2026-2027",
        },
    })
    assert response.status_code == 200
    body = response.json()
    content = json.loads(body["result"]["content"][0]["text"])
    assert "error" in content


def test_get_course_wrong_academic_year_returns_error(test_client, db_session):
    db_session.add(_make_course("02450", "2025-2026"))
    db_session.commit()

    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "get_course",
        "arguments": {
            "course_number": "02450",
            "academic_year": "2020-2021",
        },
    })
    assert response.status_code == 200
    body = response.json()
    content = json.loads(body["result"]["content"][0]["text"])
    assert "error" in content


# ---------------------------------------------------------------------------
# search_courses tool
# ---------------------------------------------------------------------------


def test_search_courses_returns_results(test_client, db_session):
    db_session.add(_make_course("02291", "2026-2027", title="System Integration", title_en="System Integration", title_da="Systemintegration"))
    db_session.commit()

    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "search_courses",
        "arguments": {
            "q": "machine learning",
            "academic_year": "2026-2027",
            "search_language": "en",
        },
    })
    assert response.status_code == 200
    body = response.json()
    content = json.loads(body["result"]["content"][0]["text"])
    assert "courses" in content


def test_search_courses_limits_results(test_client):
    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "search_courses",
        "arguments": {
            "q": "",
            "academic_year": "2026-2027",
            "search_language": "en",
            "limit": 100,
        },
    })
    assert response.status_code == 200
    body = response.json()
    content = json.loads(body["result"]["content"][0]["text"])
    assert content["returned"] <= 20


def test_search_courses_returns_selected_results_in_ascending_course_number_order(
    test_client,
    db_session,
):
    db_session.add_all(
        [
            _make_course("02450", "2026-2027", title="Machine Learning"),
            _make_course("01418", "2026-2027", title="Applied Mathematics"),
        ]
    )
    db_session.commit()

    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "search_courses",
        "arguments": {
            "q": "",
            "academic_year": "2026-2027",
            "search_language": "en",
        },
    })

    content = json.loads(response.json()["result"]["content"][0]["text"])
    assert [course["course_number"] for course in content["courses"]] == ["01418", "02450"]


def test_search_courses_with_level_filter(test_client, db_session):
    db_session.add(_make_course("02450", "2026-2027"))
    db_session.commit()

    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "search_courses",
        "arguments": {
            "q": "",
            "academic_year": "2026-2027",
            "search_language": "en",
            "level": "MSc",
        },
    })
    assert response.status_code == 200
    body = response.json()
    content = json.loads(body["result"]["content"][0]["text"])
    for course_item in content["courses"]:
        assert course_item["level"] == "MSc"


def test_search_courses_uses_requested_danish_text(test_client, db_session):
    db_session.add(_make_course("02450", "2026-2027"))
    db_session.commit()

    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "search_courses",
        "arguments": {
            "q": "beslutningstræer",
            "academic_year": "2026-2027",
            "search_language": "da",
        },
    })

    content = json.loads(response.json()["result"]["content"][0]["text"])
    assert content["search_language"] == "da"
    assert content["courses"][0]["title"] == "Introduktion til Machine Learning"


# ---------------------------------------------------------------------------
# get_study_plan tool
# ---------------------------------------------------------------------------


def test_get_study_plan_not_found_returns_error(test_client):
    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "get_study_plan",
        "arguments": {
            "program_name": "nonexistent_program_xyz",
            "academic_year": "2026-2027",
        },
    })
    assert response.status_code == 200
    body = response.json()
    content = json.loads(body["result"]["content"][0]["text"])
    assert "error" in content


def test_get_study_plan_empty_name_returns_error(test_client):
    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "get_study_plan",
        "arguments": {
            "program_name": "",
            "academic_year": "2026-2027",
        },
    })
    assert response.status_code == 200
    body = response.json()
    content = json.loads(body["result"]["content"][0]["text"])
    assert "error" in content


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


def test_unknown_tool_returns_error(test_client):
    response = _send_jsonrpc(test_client, "tools/call", {
        "name": "delete_course",
        "arguments": {},
    })
    assert response.status_code == 200
    body = response.json()
    content = json.loads(body["result"]["content"][0]["text"])
    assert "error" in content


# ---------------------------------------------------------------------------
# Groq configuration tests
# ---------------------------------------------------------------------------


def test_answer_with_remote_mcp_without_mcp_token_raises():
    from app.services.course_qa_service import CourseQAError, answer_with_remote_mcp

    os.environ["MCP_TOKEN"] = ""
    os.environ["MCP_SERVER_URL"] = "https://example.vercel.app"
    get_settings.cache_clear()

    try:
        with pytest.raises(CourseQAError, match="MCP_TOKEN"):
            answer_with_remote_mcp("hvad er 02450?")
    finally:
        os.environ["MCP_TOKEN"] = "test-mcp-token"
        os.environ["MCP_SERVER_URL"] = ""
        get_settings.cache_clear()


def test_answer_with_remote_mcp_without_mcp_server_url_raises():
    from app.services.course_qa_service import CourseQAError, answer_with_remote_mcp

    os.environ["MCP_SERVER_URL"] = ""
    get_settings.cache_clear()

    try:
        with pytest.raises(CourseQAError, match="MCP_SERVER_URL"):
            answer_with_remote_mcp("hvad er 02450?")
    finally:
        os.environ["MCP_SERVER_URL"] = "https://example.vercel.app"
        get_settings.cache_clear()


def test_answer_with_remote_mcp_without_groq_key_raises():
    from app.services.course_qa_service import CourseQAError, answer_with_remote_mcp

    os.environ["GROQ_API_KEY"] = ""
    get_settings.cache_clear()

    try:
        with pytest.raises(CourseQAError, match="GROQ_API_KEY"):
            answer_with_remote_mcp("hvad er 02450?")
    finally:
        os.environ["GROQ_API_KEY"] = "test-groq-key"
        get_settings.cache_clear()


def test_remote_mcp_uses_correct_groq_headers():
    from app.services.course_qa_service import answer_with_remote_mcp

    mock_response = MagicMock()
    mock_response.output = [MagicMock(content=[MagicMock(text="Test answer")])]

    mcp_token = get_settings().mcp_token
    mcp_server_url = "https://example.vercel.app"

    with patch("openai.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.responses.create.return_value = mock_response

        os.environ["MCP_SERVER_URL"] = mcp_server_url
        get_settings.cache_clear()

        try:
            answer_with_remote_mcp("Hvad er machine learning?")
        finally:
            get_settings.cache_clear()

        # The OpenAI client receives api_key in its constructor kwargs
        client_kwargs = MockClient.call_args.kwargs
        assert client_kwargs["api_key"] == "test-groq-key"

        # tools are passed to .responses.create()
        call_kwargs = instance.responses.create.call_args.kwargs

        tools = call_kwargs["tools"]
        assert len(tools) == 1
        assert tools[0]["type"] == "mcp"
        assert tools[0]["server_label"] == "dtu_courses"
        assert tools[0]["server_url"] == mcp_server_url + "/mcp"
        assert tools[0]["headers"]["Authorization"] == f"Bearer {mcp_token}"
        assert tools[0]["allowed_tools"] == [
            "get_course",
            "search_courses",
            "get_study_plan",
            "get_specializations",
        ]
        assert call_kwargs["max_output_tokens"] == 1000
        assert call_kwargs["max_tool_calls"] == 3
        assert "2026-2027" in call_kwargs["instructions"]


def test_remote_mcp_returns_final_text():
    from app.services.course_qa_service import answer_with_remote_mcp

    mock_response = MagicMock()
    mock_response.output = [MagicMock(content=[MagicMock(text="The answer is 42.")])]

    with patch("openai.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.responses.create.return_value = mock_response

        answer = answer_with_remote_mcp("What is the answer?")

    assert answer == "The answer is 42."


def test_remote_mcp_uses_explicit_danish_response_language():
    from app.services.course_qa_service import answer_with_remote_mcp

    mock_response = MagicMock()
    mock_response.output = [MagicMock(content=[MagicMock(text="Et dansk svar.")])]

    with patch("openai.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.responses.create.return_value = mock_response

        answer = answer_with_remote_mcp(
            "Sammenlign de to engelske programnavne",
            response_language="da",
        )

    instructions = instance.responses.create.call_args.kwargs["instructions"]
    assert "SVARE UDELUKKENDE PÅ DANSK" in instructions
    assert "forklaringer, overskrifter og overgange på dansk" in instructions
    assert answer == "Et dansk svar."


def test_remote_mcp_empty_output_raises():
    from app.services.course_qa_service import CourseQAError, answer_with_remote_mcp

    mock_response = MagicMock()
    mock_response.output = []

    with patch("openai.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.responses.create.return_value = mock_response

        with pytest.raises(CourseQAError, match="no output"):
            answer_with_remote_mcp("test")
