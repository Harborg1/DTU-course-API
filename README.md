# DTU Course API

Produktionsorienteret kursusanbefaler, importer og REST API til det officielle DTU-kursuskatalog. Projektet henter kurser for 2026/2027 fra DTU, gemmer dem i PostgreSQL 17 og giver studerende anbefalinger gennem en responsiv chat-hjemmeside. Det eksisterende API kan også bruges fra Microsoft Copilot Studio.

## Arkitektur

```text
DTU Course Base
       ↓
    Importer
       ↓
  PostgreSQL
       ↓
    FastAPI
   ↙   ↓   ↘
Web-chat MCP  Beskyttet REST API
          ↑             ↓
        Groq    Copilot Studio
```

Kursusdata hentes som struktureret XML, valideres og gemmes lokalt. API-laget bruger services og dependency-injected SQLAlchemy-sessions. PostgreSQLs genererede `tsvector` vægter titler som A, beskrivelse og indhold som B samt læringsmål og forudsætninger som C.

## Officiel datakilde

Kursusnumre og kursusdata hentes fra DTU Kursusbasens officielle `CourseWebServiceV2`. `GetCourse` leverer de årgangsspecifikke kursusdata som XML, som gemmes uden HTML-parsing. Ingen uofficiel database bruges.

## Hurtig start med Docker

Kopiér miljøfilen og skift især API-nøglen:

```bash
cp .env.example .env
docker compose up --build
```

Compose starter PostgreSQL 17 med en persistent `postgres_data` volume, venter på databasen, kører `alembic upgrade head` og starter API'et på `http://localhost:8000`.

```bash
curl http://localhost:8000/health
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/import/status
```

API-dokumentation findes på `/docs`, `/redoc` og `/openapi.json`.

Hjemmesiden findes på `/`. Den sender brugerens samtalekontekst til `POST /api/chat`, hvor emne, niveau, ECTS, periode og sprog udledes, og der søges direkte i de officielle kursusdata. Browseren modtager aldrig den interne `API_KEY`.

## Lokal Python-installation

Projektet målretter Python 3.12:

Se også den separate trin-for-trin-guide i [`VENV_SETUP.md`](VENV_SETUP.md), som dækker Windows CMD, PowerShell, Linux, macOS og VS Code.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Ved lokal kørsel skal `DATABASE_URL` pege på en PostgreSQL-instans, typisk `postgresql+psycopg://dtu:dtu@localhost:5432/dtu_courses`. Opret eller opgrader skemaet med:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

## Miljøvariabler

| Variabel | Formål |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL med psycopg-driver |
| `API_KEY` | Hemmelig nøgle til `X-API-Key`; må ikke committes |
| `DTU_BASE_URL` | Officiel DTU-base-URL |
| `DEFAULT_ACADEMIC_YEAR` | Standardårgang, `2026-2027` |
| `IMPORT_REQUEST_DELAY` | Pause mellem DTU-requests i sekunder |
| `LOG_LEVEL` | Fx `INFO` eller `DEBUG` |
| `GROQ_API_KEY` | Groq API-nøgle til chatten |
| `GROQ_MODEL` | Groq-model; standard er `openai/gpt-oss-120b` |
| `MCP_TOKEN` | Lang, tilfældig bearer token, der beskytter `/mcp` |
| `MCP_SERVER_URL` | Offentlig HTTPS-base-URL, fx `https://app.example.com` |

Chatten bruger Groqs Responses API. Groq kalder de skrivebeskyttede MCP-tools
`get_course`, `search_courses` og `get_study_plan` på `/mcp`; browseren får aldrig
adgang til `GROQ_API_KEY` eller `MCP_TOKEN`.

## Import

Hjælpescripterne bruger timeout, genforsøg med eksponentiel backoff, begrænset parallelitet, et tydeligt User-Agent og validering af XML-svarene.

```bash
# Hent kun alle publicerede kursusnumre (ét nummer pr. linje)
python scripts/get_all_course_numbers.py --catalog-version 2026/2027

# Gem kursusnumrene i en fil
python scripts/get_all_course_numbers.py --catalog-version 2026/2027 > course_numbers.txt

# Gem GetCourse XML for hvert kursus i data/course_information/
python scripts/get_all_course_information.py --year-group 2026/2027
```

### Studieplaner

Studieplaner gemmes separat fra kursuskataloget i `study_programs`, `study_plan_sections`,
`study_plan_courses`, `study_plan_requirements` og `study_plan_requirement_courses`. Regler som
obligatoriske kurser, “vælg ét af”, samlede ECTS-krav og minimums-ECTS fra en kurspulje bevares
som strukturerede krav. Kandidatsider behandles med deres særskilte struktur for programme provision,
polytechnical foundation, programme specific course pools, speciale og valgkursusgrænser. Kurser i
underkrav genbruger samme studieplanspost og tælles derfor ikke dobbelt.

Importér én studieplan i Docker:

```bash
docker compose exec api python -m importer.study_plan_cli \
  --url https://student.dtu.dk/studieordninger/Bachelor/anvendt-matematik/studieplan

docker compose exec api python -m importer.study_plan_cli \
  --url https://www.dtu.dk/english/education/graduate/msc-programmes/applied-chemistry/curriculum
```

Eller importér alle understøttede DTU-URL'er i en fil:

```bash
docker compose exec api python -m importer.study_plan_cli --urls-file app/data/program_urls.txt
```

Chatten genkender derefter spørgsmål som “Jeg studerer Anvendt Matematik – hvordan er studiet
opbygget, og hvilke kurser er obligatoriske?” og returnerer både en forklaring og et struktureret
`studyPlan`-objekt.

Slutrapporten viser discovered, imported, updated, unchanged og failed og gemmes i audit-tabellen `import_runs`. UPSERT-nøglen er `(course_number, academic_year)`, så en senere årgang ikke overskriver tidligere data. For et nyt år bruges blot fx. `--academic-year 2027-2028`, når den officielle DTU-liste findes.

## API

Alle `/api/v1`-endpoints kræver `X-API-Key`. `/health` er offentlig. Pagination har standard `limit=20`, maksimum 50 og `offset=0`.

| Metode og sti | Formål |
|---|---|
| `GET /` | Offentlig chat-hjemmeside |
| `GET /health` | API- og databasekontrol |
| `GET /api/info` | Offentlig serviceinformation |
| `POST /api/chat` | Offentlige, kildehenviste kursusanbefalinger |
| `GET /api/v1/courses/search` | Full-text-søgning og filtre |
| `GET /api/v1/courses` | Sideinddelt liste med strukturerede filtre |
| `GET /api/v1/courses/{course_number}` | Komplet kursus for valgt årgang |
| `GET /api/v1/import/status` | Kursusantal, seneste import og fejlantal |

Search understøtter `q`, `academic_year`, `ects`, `level`, `period`, `schedule`, `department`, `language`, `campus`, `limit` og `offset`. Niveau normaliseres til blandt andet `BSc`, `MSc` og `PhD`; sprog normaliseres til blandt andet `Danish` og `English`.

```bash
curl -G http://localhost:8000/api/v1/courses/search \
  -H "X-API-Key: $API_KEY" \
  --data-urlencode "q=machine learning" \
  --data-urlencode "academic_year=2026-2027" \
  --data-urlencode "ects=5" \
  --data-urlencode "period=E"

curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/api/v1/courses/01001?academic_year=2026-2027"
```

Søgeresultater indeholder kun kompakte felter, højst 500 tegn af beskrivelsen, `relevanceScore` og den officielle `sourceUrl`. Brug detail-endpointet til forudsætninger, eksamen, indhold og læringsmål.

## Tests

Tests bruger gemte, reducerede HTML-fixtures baseret på verificerede bachelor- og kandidatsider for
2026/2027 og laver ingen live requests:

```bash
pytest -q
```

De dækker parservariationer, manglende valgfrie felter, forkert studieår, søgning, filtre, pagination, detailvisning, 404, API-key, UPSERT, dubletter og importfejl.

## Copilot Studio og Custom Connector

Swagger 2.0-definitionen ligger i [`connector/swagger.json`](connector/swagger.json). Før import skal `host` ændres fra `api.example.com` til API'ets offentlige HTTPS-host; `basePath` skal fortsat være `/api/v1`.

1. Deploy API'et på en offentligt tilgængelig HTTPS-adresse.
2. Ret `host` i `connector/swagger.json`.
3. Gå i Power Apps eller Power Automate → Custom connectors → New custom connector → Import an OpenAPI file.
4. Upload `connector/swagger.json`, opret connectoren og angiv API-nøglen ved forbindelsen.
5. Test `SearchCourses` og `GetCourse` i connectorens testfane.
6. Åbn agenten i Copilot Studio, vælg Tools → Add a tool → Connector, og tilføj begge operationer.
7. Instruér Copilot i først at kalde `SearchCourses`, vælge højst fem relevante kandidater og kun kalde `GetCourse` på de kandidater, hvor detaljer skal verificeres.
8. Publicér agenten og kontrollér, at officielle `sourceUrl`-links følger svarene.

## Deployment

Containeren kan deployes på enhver platform med Docker og en PostgreSQL 17-database. Sæt secrets i platformens secret store, kør Alembic som release/start-step, eksponér port 8000 via HTTPS og brug en persistent administreret PostgreSQL-database. Kør importerjobbet som et separat planlagt job; kør ikke flere fulde imports parallelt mod DTU.

### Vercel preview

Vercel kører FastAPI-applikationen fra `app.main:app` som én Python Function i Paris-regionen tæt på Supabase. Docker og Docker Compose bruges fortsat kun lokalt. Den fulde DTU-import skal køres lokalt eller i et separat job og ikke fra en Vercel-request.

1. Log ind og link den lokale mappe:

   ```bash
   vercel login
   vercel link
   ```

2. Tilføj `DATABASE_URL`, `API_KEY`, `DEFAULT_ACADEMIC_YEAR`, `DTU_BASE_URL`, `LOG_LEVEL`, `GROQ_API_KEY`, `GROQ_MODEL`, `MCP_TOKEN` og `MCP_SERVER_URL` som Preview environment variables i Vercel. `MCP_SERVER_URL` skal være deploymentets offentlige HTTPS-base-URL, og `MCP_TOKEN` skal være en separat lang, tilfældig secret. Brug Supabases transaction pooler på port 6543 til `DATABASE_URL`. Tilføj ikke `MIGRATION_DATABASE_URL` til Vercel.
3. Kontrollér konfigurationen lokalt med `vercel dev`.
4. Opret preview med `vercel deploy` og verificér `/`, `/health`, et autentificeret søgekald og et MCP-kald med `Authorization: Bearer $MCP_TOKEN`.
5. Tilføj de samme nødvendige variabler til Production og kør først `vercel deploy --prod`, når previewet er godkendt.

Python er fastlåst til 3.12 i `.python-version`. `requirements.txt` indeholder kun runtime-afhængigheder til Vercel, `requirements-import.txt` tilføjer importer og Alembic, og `requirements-dev.txt` tilføjer testværktøjer.
