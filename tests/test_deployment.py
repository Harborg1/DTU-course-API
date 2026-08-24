import json
from pathlib import Path

from app.api.routes.root import router, service_info

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_api_info_route_describes_the_service_without_authentication():
    assert "/api/info" in {route.path for route in router.routes}
    assert service_info().model_dump(by_alias=True) == {
        "name": "DTU Course API",
        "status": "ok",
        "documentationUrl": "/docs",
        "healthUrl": "/health",
    }


def test_homepage_is_public_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Course Compass" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_homepage_defaults_to_english_and_has_language_toggle(client):
    response = client.get("/")

    assert '<html lang="en">' in response.text
    assert "Your personal course guide" in response.text
    assert 'data-language="en" aria-pressed="true"' in response.text
    assert 'data-language="da" aria-pressed="false"' in response.text


def test_chat_message_styles_preserve_model_line_breaks():
    styles = (PROJECT_ROOT / "app" / "web" / "static" / "styles.css").read_text()

    assert ".message p { margin: 0; white-space: pre-wrap; }" in styles


def test_python_runtime_is_pinned_to_312():
    assert (PROJECT_ROOT / ".python-version").read_text().strip() == "3.12"


def test_vercel_configuration_targets_fastapi_in_paris():
    config = json.loads((PROJECT_ROOT / "vercel.json").read_text())

    assert config["framework"] == "fastapi"
    assert config["regions"] == ["cdg1"]
    assert config["functions"]["app/main.py"]["maxDuration"] == 60
