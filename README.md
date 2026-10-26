# DTU Course MCP Server

Projektet samler officielle oplysninger om DTU-kurser, studieplaner og
specialiseringer i PostgreSQL og eksponerer dem som seks skrivebeskyttede
MCP-værktøjer til Microsoft Copilot Studio.

```text
DTU-kilder → importere → PostgreSQL/Supabase → FastAPI /mcp → Copilot Studio
```

## MCP-værktøjer

| Værktøj | Formål |
|---|---|
| `search_courses` | Søg efter kurser med emne og strukturerede filtre |
| `get_course` | Hent alle relevante oplysninger om ét kursus |
| `get_courses` | Hent op til 20 kendte kursusnumre samlet |
| `get_new_courses` | Sammenlign to katalogårgange |
| `get_study_plan` | Hent en uddannelses studieplan og krav |
| `get_specializations` | Hent specialiseringer og deres kursuskrav |

MCP-serveren bruger stateless Streamable HTTP på `/mcp` og kræver:

```http
Authorization: Bearer <MCP_TOKEN>
```

FastAPI forbinder til databasen via `DATABASE_URL`. MCP-tokenet giver ikke
direkte databaseadgang.

## Konfiguration

Opret lokal konfiguration og angiv som minimum databaseforbindelsen, et langt
tilfældigt MCP-token og serverens offentlige URL:

```bash
cp .env.example .env
```

```dotenv
DATABASE_URL=postgresql+psycopg://...
MCP_TOKEN=<generate-a-long-random-secret>
MCP_SERVER_URL=https://your-domain.vercel.app
```

`MCP_SERVER_URL` bruges til MCP-transportens host- og origin-beskyttelse.

## Lokal udvikling

Projektet kræver Python 3.12. Den komplette lokale stack kan startes med:

```bash
docker compose up --build
```

Applikationen er derefter tilgængelig på `http://localhost:8000`:

- `/` viser serviceinformation som JSON.
- `/health` kontrollerer databaseforbindelsen.
- `/mcp` er den beskyttede MCP-transport.

Kør den offline testsuite med:

```bash
pytest -q
```

## Data og import

`importer/` henter og parser data fra DTU Kursusbasen og DTU's officielle
studieordningssider. Rå snapshots ligger i `app/data/`, mens Alembic-revisioner
ligger i `migrations/`. Disse dele bruges til at vedligeholde databasen, men er
ekskluderet fra Vercels runtime-bundle.

En mindre XML-import kan afprøves efter migrationerne:

```bash
python -m importer.course_xml_cli --academic-year 2026-2027 --limit 20
```

Se `scripts/update_supabase.md` for den fulde opdateringsproces.

## Projektstruktur

| Mappe | Indhold |
|---|---|
| `app/mcp_server/` | MCP-transport, autentifikation og de seks værktøjer |
| `app/services/` | Søgning, katalogsammenligning og fælles logik |
| `app/models/` | SQLAlchemy-modeller |
| `app/api/routes/` | Status- og health-endpoints |
| `importer/` | Import af kurser, studieplaner og specialiseringer |
| `app/data/` | Lokale snapshots og URL-lister til importarbejdet |
| `migrations/` | Databaseskemaets revisionshistorik |
| `tests/` | Offline tests for MCP, database og importere |
