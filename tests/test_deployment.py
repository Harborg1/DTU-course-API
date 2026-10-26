import json
from pathlib import Path

from app.api.routes.root import router, service_info

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_api_info_route_describes_the_service_without_authentication():
    assert "/api/info" in {route.path for route in router.routes}
    assert service_info().model_dump(by_alias=True) == {
        "name": "DTU Course MCP Server",
        "status": "ok",
        "mcpEndpoint": "/mcp",
        "documentationUrl": "/docs",
        "healthUrl": "/health",
    }


def test_homepage_is_public_service_metadata(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == service_info().model_dump(by_alias=True)


def test_removed_web_chat_and_rest_routes_are_not_exposed(client):
    assert client.post("/api/chat", json={}).status_code == 404
    assert client.get("/api/v1/courses").status_code == 404
    assert client.get("/static/app.js").status_code == 404


def test_python_runtime_is_pinned_to_312():
    assert (PROJECT_ROOT / ".python-version").read_text().strip() == "3.12"


def test_vercel_configuration_targets_fastapi_in_paris():
    config = json.loads((PROJECT_ROOT / "vercel.json").read_text())

    assert config["framework"] == "fastapi"
    assert config["regions"] == ["cdg1"]
    assert config["functions"]["app/main.py"]["maxDuration"] == 60
