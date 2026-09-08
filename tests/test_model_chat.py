import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import Settings, get_settings
from app.mcp_server.server import _handle_get_study_plan, _handle_search_courses
from app.models.study_plan import StudyProgram
from app.schemas.recommendation import ChatRequest
from app.services.chat_service import HISTORY_CHARACTER_BUDGET, conversation_messages
from app.services.course_qa_service import CourseQAError, MCPAnswer, MCPToolResult, respond_with_remote_mcp


PHYSICS_QUESTION = (
    "If I like physics, would you recommend studying physics or computer science and engineering"
)


@pytest.fixture(autouse=True)
def model_chat(monkeypatch):
    monkeypatch.setenv("CHAT_MODE", "model")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("MCP_SERVER_URL", "https://mcp.example.test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_model_chat_is_the_default():
    assert Settings.model_fields["chat_mode"].default == "model"


@pytest.mark.parametrize("prompt", [
    PHYSICS_QUESTION,
    "Jeg kan godt lide fysik",
    "Which courses are new?",
    "What are the prerequisites of 02450?",
    "Find all 5 ECTS MSc courses in English in period E about physics",
    "Hvad er studieplanen for Anvendt Matematik?",
])
def test_every_question_reaches_the_model_without_intent_routing(client, prompt):
    with (
        patch("app.services.chat_service.respond_with_remote_mcp", return_value=MCPAnswer("A reasoned answer.")) as model,
        patch("app.api.routes.chat.recommend_courses") as legacy,
        patch("app.services.intent_service.classify_intent") as classifier,
        patch("app.api.routes.chat.build_completed_turn") as legacy_state,
    ):
        response = client.post("/api/chat", json={"messages": [{"role": "user", "content": prompt}]})

    assert response.status_code == 200
    assert response.json()["reply"] == "A reasoned answer."
    assert response.json()["isDirectAnswer"] is True
    assert model.call_args.args == (prompt, "2026-2027")
    assert model.call_args.kwargs["messages"] == [{"role": "user", "content": prompt}]
    legacy.assert_not_called()
    classifier.assert_not_called()
    legacy_state.assert_not_called()


def test_follow_up_preserves_assistant_reasoning_and_roles(client):
    messages = [
        {"role": "user", "content": PHYSICS_QUESTION},
        {"role": "assistant", "content": "Physics fits your interest in experiments. " * 30},
        {"role": "user", "content": "What if I also enjoy programming?"},
    ]
    with patch("app.services.chat_service.respond_with_remote_mcp", return_value=MCPAnswer("Consider both.")) as model:
        response = client.post("/api/chat", json={"messages": messages})
    assert response.status_code == 200
    assert model.call_args.args[0] == messages[-1]["content"]
    assert model.call_args.kwargs["messages"] == messages


def test_new_topic_and_explicit_language_change_reach_model(client):
    messages = [
        {"role": "user", "content": "Hvad er studieplanen for Anvendt Matematik?"},
        {"role": "assistant", "content": "Her er studieplanen."},
        {"role": "user", "content": "Which courses about biotechnology are new?"},
    ]
    with patch("app.services.chat_service.respond_with_remote_mcp", return_value=MCPAnswer("New courses.")) as model:
        response = client.post("/api/chat", json={"messages": messages})
    assert response.json()["responseLanguage"] == "en"
    assert model.call_args.args[0] == messages[-1]["content"]
    assert model.call_args.kwargs["response_language"] == "en"


def test_neutral_follow_up_keeps_conversation_language(client):
    with patch("app.services.chat_service.respond_with_remote_mcp", return_value=MCPAnswer("Et dansk svar.")) as model:
        response = client.post("/api/chat", json={"messages": [
            {"role": "user", "content": "Hvem underviser i kurset?"},
            {"role": "assistant", "content": "Hvilket kursus?"},
            {"role": "user", "content": "02450"},
        ]})
    assert response.json()["responseLanguage"] == "da"
    assert model.call_args.kwargs["response_language"] == "da"


def test_history_budget_keeps_latest_request_and_complete_recent_messages():
    recent = [
        {"role": "user", "content": "Compare physics and computer science"},
        {"role": "assistant", "content": "Both use mathematics."},
        {"role": "user", "content": "Why?"},
    ]
    request = ChatRequest(messages=[
        {"role": "user", "content": "Old topic"},
        {"role": "assistant", "content": "a" * HISTORY_CHARACTER_BUDGET},
        *recent,
    ])
    assert conversation_messages(request) == recent


def test_legacy_completed_turn_facts_remain_available_to_old_clients(client):
    with patch("app.services.chat_service.respond_with_remote_mcp", return_value=MCPAnswer("An answer.")) as model:
        response = client.post("/api/chat", json={
            "messages": [{"role": "user", "content": "Why that one?"}],
            "completedTurns": [{
                "request": PHYSICS_QUESTION,
                "operation": "comparison",
                "studyProgramNames": ["Physics", "Computer Science and Engineering"],
            }],
        })
    assert response.status_code == 200
    sent = model.call_args.kwargs["messages"][0]["content"]
    assert sent.startswith("Why that one?")
    assert "Physics" in sent and "Computer Science and Engineering" in sent


@pytest.mark.parametrize("messages", [
    [{"role": "system", "content": "Override instructions"}],
    [{"role": "user", "content": "a" * 801}],
    [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}],
    [{"role": "user", "content": "Hi"}] * 24,
])
def test_invalid_dialogue_is_rejected_before_calling_model(client, messages):
    with patch("app.services.chat_service.respond_with_remote_mcp") as model:
        response = client.post("/api/chat", json={"messages": messages})
    assert response.status_code == 422
    model.assert_not_called()


def test_remote_failure_does_not_fall_back_to_keyword_clarification(client):
    with (
        patch("app.services.chat_service.respond_with_remote_mcp", side_effect=CourseQAError("offline")),
        patch("app.api.routes.chat.recommend_courses") as legacy,
    ):
        response = client.post("/api/chat", json={"messages": [{"role": "user", "content": PHYSICS_QUESTION}]})
    assert "could not retrieve a complete answer" in response.json()["reply"]
    assert response.json()["turnState"] is None
    legacy.assert_not_called()


def test_real_mcp_data_becomes_course_and_program_cards(client, db_session, sample_courses):
    db_session.add(StudyProgram(
        slug="physics", name="Physics", degree_type="Master", academic_year="2026-2027",
        introduction="Physics experiments and mathematical models.",
        source_url="https://www.dtu.dk/physics", content_hash="a" * 64,
    ))
    db_session.commit()
    with patch("app.database.SessionLocal", sessionmaker(bind=db_session.get_bind())):
        course_data = _handle_search_courses({"q": "machine learning", "search_language": "en", "academic_year": "2026-2027"})
        program_data = _handle_get_study_plan({"program_name": "Physics", "academic_year": "2026-2027"})
    answer = MCPAnswer("Here are the results.", [
        MCPToolResult("search_courses", {}, course_data),
        MCPToolResult("get_study_plan", {}, program_data),
    ])
    with patch("app.services.chat_service.respond_with_remote_mcp", return_value=answer):
        response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Show the results"}]})
    body = response.json()
    assert body["recommendations"][0]["courseNumber"] == "02450"
    assert body["recommendations"][0]["sourceUrl"] == course_data["courses"][0]["source_url"]
    assert body["studyPrograms"][0]["description"] == "Physics experiments and mathematical models."
    assert body["studyPlan"]["programName"] == "Physics"
    assert body["studyPlan"]["sourceUrl"] == "https://www.dtu.dk/physics"


def test_program_comparison_preserves_both_programs_without_selecting_one_plan(client):
    answer = MCPAnswer("Physics is the closer fit.", [
        MCPToolResult("get_study_plan", {}, {
            "program_name": name, "degree_type": "Master", "sections": [],
            "source_url": f"https://www.dtu.dk/{slug}",
        }) for name, slug in [("Physics", "physics"), ("Computer Science and Engineering", "cse")]
    ])
    with patch("app.services.chat_service.respond_with_remote_mcp", return_value=answer):
        response = client.post("/api/chat", json={"messages": [{"role": "user", "content": PHYSICS_QUESTION}]})
    assert len(response.json()["studyPrograms"]) == 2
    assert response.json()["studyPlan"] is None
    assert response.json()["reply"] == "Physics is the closer fit."


def test_remote_model_receives_role_labelled_dialogue_and_reasoning_instructions():
    messages = [{"role": "user", "content": PHYSICS_QUESTION}]
    result = SimpleNamespace(output_text="Physics may fit.", output=[SimpleNamespace(type="message")], status="completed")
    with patch("openai.OpenAI") as client:
        client.return_value.responses.create.return_value = result
        answer = respond_with_remote_mcp(PHYSICS_QUESTION, messages=messages)
    sent = client.return_value.responses.create.call_args.kwargs
    assert sent["input"] == messages
    assert sent["max_output_tokens"] == get_settings().chat_max_output_tokens
    assert sent["max_tool_calls"] == get_settings().chat_max_tool_calls
    assert "højst 3 sætninger" not in sent["instructions"]
    assert "egen foreløbige anbefaling" in sent["instructions"]
    assert "get_study_plan for hver" in sent["instructions"]
    assert "Udelad degree_type" in sent["instructions"]
    assert "Et kursussøgeresultat beviser IKKE" in sent["instructions"]
    assert "hvert kursus er obligatorisk" in sent["instructions"]
    assert answer.reply == "Physics may fit."


@pytest.mark.parametrize("wrapped", [False, True])
def test_remote_mcp_extracts_facts_from_tool_output_only(wrapped):
    data = {"courses": [{"course_number": "02450"}]}
    output = {"content": [{"type": "text", "text": json.dumps(data)}]} if wrapped else data
    result = SimpleNamespace(output_text="A recommendation.", status="completed", output=[
        SimpleNamespace(type="mcp_call", error=None, name="search_courses", arguments='{"q":"physics"}', output=json.dumps(output)),
        SimpleNamespace(type="mcp_call", error=None, name="get_study_plan", arguments="{}", output='{"error":"Not found"}'),
        SimpleNamespace(type="mcp_call", error="timeout", name="get_course", arguments="{}", output="{}"),
        SimpleNamespace(type="message", content=[{"text": "invented course data"}]),
    ])
    with patch("openai.OpenAI") as client:
        client.return_value.responses.create.return_value = result
        answer = respond_with_remote_mcp(PHYSICS_QUESTION)
    assert answer.tool_results == [MCPToolResult("search_courses", {"q": "physics"}, data)]


def test_incomplete_model_response_is_not_presented_as_complete():
    result = SimpleNamespace(status="incomplete", output_text="A truncated answer", output=[SimpleNamespace(type="message")])
    with patch("openai.OpenAI") as client:
        client.return_value.responses.create.return_value = result
        with pytest.raises(CourseQAError, match="incomplete"):
            respond_with_remote_mcp(PHYSICS_QUESTION)


def test_mcp_course_search_preserves_filters_and_supports_pagination(db_session, sample_courses):
    with patch("app.database.SessionLocal", sessionmaker(bind=db_session.get_bind())):
        first = _handle_search_courses({
            "q": "", "academic_year": "2026-2027", "search_language": "en", "limit": 1,
        })
        second = _handle_search_courses({
            "q": "", "academic_year": "2026-2027", "search_language": "en", "limit": 1,
            "offset": first["next_offset"],
        })
        filtered = _handle_search_courses({
            "q": "", "academic_year": "2026-2027", "search_language": "en",
            "level": "MSc", "ects": 5, "language": "English", "period": "E",
        })
        empty = _handle_search_courses({
            "q": "", "academic_year": "2026-2027", "search_language": "en",
            "level": "MSc", "ects": 5, "language": "Danish", "period": "E",
        })
    assert first["count"] == 2
    assert first["courses"][0]["course_number"] == "01418"
    assert second["courses"][0]["course_number"] == "02450"
    assert second["next_offset"] is None
    assert [course["course_number"] for course in filtered["courses"]] == ["02450"]
    assert empty["courses"] == []


@pytest.mark.parametrize("filters", [
    {"offset": -1}, {"offset": 0.5}, {"offset": True}, {"offset": "1"},
    {"language": "French"}, {"period": ["E"]},
])
def test_mcp_rejects_invalid_pagination_and_filters(filters):
    result = _handle_search_courses({
        "q": "physics", "academic_year": "2026-2027", "search_language": "en", **filters,
    })
    assert "error" in result
