# Repository Guidelines

## Project Structure & Module Organization

`app/` contains the FastAPI application and read-only MCP server. Route handlers live in `app/api/routes/`, database models in `app/models/`, import schemas in `app/schemas/`, MCP tools in `app/mcp_server/`, and shared querying logic in `app/services/`. Static source snapshots belong in `app/data/`. DTU HTML discovery, parsing, and import workflows are isolated in `importer/`. Alembic revisions live in `migrations/versions/`, and operational helpers in `scripts/`. Tests mirror runtime and import areas in `tests/test_*.py`; parser fixtures belong in `tests/fixtures/`.

## Build, Test, and Development Commands

- `python3.12 -m venv .venv && source .venv/bin/activate` creates the supported Python environment.
- `python -m pip install -r requirements-dev.txt` installs runtime, importer, migration, and test dependencies.
- `cp .env.example .env` creates local configuration; set the database URL, MCP token, and public MCP URL.
- `docker compose up --build` starts PostgreSQL 17, applies migrations, and serves the API on port 8000.
- `alembic upgrade head` updates a locally configured database schema.
- `uvicorn app.main:app --reload` runs the API with live reload.
- `pytest -q` runs the complete offline test suite.
- `python -m importer.course_xml_cli --academic-year 2026-2027 --limit 20` performs a small XML importer smoke test after migrations.

## Coding Style & Naming Conventions

Use four-space indentation, PEP 8 naming (`snake_case` functions/modules, `PascalCase` classes), explicit type annotations, and modern Python 3.12 syntax. Keep route handlers and MCP handlers thin when shared querying logic belongs in services. Follow the existing SQLAlchemy 2 typed mapping style (`Mapped[...]`, `mapped_column`). No formatter or linter is currently enforced; keep imports grouped as standard library, third-party, then local, and match surrounding line-wrapping conventions.

## Testing Guidelines

Use pytest and name files `test_<feature>.py` and cases `test_<behavior>`. Reuse fixtures from `tests/conftest.py`. Parser tests must use reduced saved HTML fixtures—never live DTU requests. Cover successful behavior and relevant validation, authentication, missing-data, database, and import-failure paths. There is no configured coverage threshold; every behavior change should include focused regression tests.

## Commit & Pull Request Guidelines

Recent history generally uses short imperative subjects, increasingly with Conventional Commit prefixes such as `feat:` and `fix(mcp):`. Keep each commit focused. Pull requests should explain the user-visible change, note schema or environment-variable changes, link the issue when applicable, and report test commands run. Update migrations, `.env.example`, MCP documentation, or README documentation when their contracts change. Never commit `.env`, tokens, database credentials, local databases, caches, or virtual environments.
