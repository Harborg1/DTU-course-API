# DTU Course API

DTU Course API samler officielle oplysninger om DTU-kurser, studieplaner og
specialiseringer i én database. Data kan bruges gennem en chat, et REST API
eller MCP-værktøjer til AI-klienter.

Alle resultater bygger på importerede DTU-kilder og indeholder links tilbage
til de officielle sider.

## Sådan er systemet bygget

```text
DTU Kursusbasen og DTU's studieordninger
                    │
                    ▼
         Import og strukturering af data
                    │
                    ▼
          PostgreSQL med pgvector
                    │
                    ▼
                 FastAPI
          ┌─────────┼─────────┐
          ▼         ▼         ▼
         Chat    REST API    MCP
```

Systemet består af fire hoveddele:

1. **Importerne** henter kursusdata som XML fra DTU Kursusbasen og læser
   studieplaner og specialiseringer fra DTU's officielle sider.
2. **PostgreSQL** gemmer data struktureret og adskilt efter akademisk år.
   Danske og engelske kursustekster gemmes separat. PostgreSQL full-text search
   og pgvector bruges til tekstbaseret og semantisk søgning.
3. **FastAPI** indeholder søgning, filtre, opslag og chat-endpoints.
4. **Chatten** bruger en sprogmodel, som kan slå data op gennem de
   skrivebeskyttede MCP-værktøjer og vedlægge officielle kildelinks.

## Hvilke data er tilgængelige?

### Kurser

For hvert importeret akademisk år kan systemet blandt andet levere:

- kursusnummer, dansk og engelsk titel
- ECTS, niveau og kursustype
- institut, campus og undervisningssprog
- undervisningsperiode og skemaplacering
- beskrivelse, fagligt indhold og læringsmål
- anbefalede og obligatoriske forudsætninger
- undervisningsformer, eksamen og evaluering
- kursusansvarlige og undervisere
- kurser, som ikke kan give merit sammen
- tidligere kursusnumre
- link til den officielle kursusside

Kurser kan søges efter fritekst og filtreres efter blandt andet årgang, ECTS,
niveau, periode, skema, institut, undervisningssprog og campus. Søgningen kan
bruge både danske og engelske kursustekster.

### Studieplaner

Importerede studieplaner indeholder:

- uddannelsens navn, gradstype og introduktion
- studieplanens sektioner og kurser
- obligatoriske og valgfrie kurser
- regler som "vælg ét af", minimum antal kurser og minimum ECTS
- kursernes rolle, ECTS og skemaplacering
- link til den officielle studieordning

### Specialiseringer

Specialiseringer er knyttet til de relevante kandidatuddannelser. Systemet
bevarer forskellen mellem obligatoriske kurser, valgmuligheder, anbefalede
kurser og udgåede kurser, som stadig kan tælle med i kravene.

### Ændringer mellem årgange

Når flere årgange er importeret, kan systemet finde kurser, der er kommet til
siden den foregående årgang. DTU's oplysninger om tidligere kursusnumre bruges
til at skelne mellem helt nye kurser og kurser, som blot har fået nyt nummer.

## Adgang til data

Den offentlige chat findes på `/`. Den kan søge efter kurser, forklare
studieplaner, vise specialiseringer og sammenligne katalogårgange.

Det beskyttede REST API bruger headeren `X-API-Key`:

| Endpoint | Indhold |
|---|---|
| `GET /api/v1/courses/search` | Søgning og filtrering i kurser |
| `GET /api/v1/courses` | Sideinddelt kursusliste |
| `GET /api/v1/courses/{course_number}` | Alle oplysninger om ét kursus |
| `GET /api/v1/import/status` | Antal kurser og status for seneste import |

Interaktiv API-dokumentation findes på `/docs`. En Swagger-definition til
Microsoft Copilot Studio ligger i
[`connector/swagger.json`](connector/swagger.json).

MCP-serveren ligger på `/mcp` og tilbyder følgende skrivebeskyttede værktøjer:

| Værktøj | Formål |
|---|---|
| `search_courses` | Søg efter kurser med relevante filtre |
| `get_course` | Hent ét kursus |
| `get_courses` | Hent flere kendte kursusnumre samlet |
| `get_new_courses` | Sammenlign to katalogårgange |
| `get_study_plan` | Hent en uddannelses studieplan og dens krav |
| `get_specializations` | Hent en uddannelses specialiseringer og kursuskrav |

## Kør projektet lokalt

Projektet kræver Docker. Opret en lokal konfiguration ud fra eksemplet og start
derefter API og database:

```bash
cp .env.example .env
docker compose up --build
```

Applikationen er derefter tilgængelig på `http://localhost:8000`.

## Projektets vigtigste mapper

| Mappe | Indhold |
|---|---|
| `app/api/routes/` | REST- og chat-endpoints |
| `app/services/` | Søgning, anbefalinger og forretningslogik |
| `app/models/` | Databasemodeller for kurser og studieplaner |
| `app/mcp_server/` | MCP-server og værktøjer til AI-klienter |
| `app/web/` | Den offentlige chatbrugerflade |
| `importer/` | Import af kurser, studieplaner og specialiseringer |
| `app/data/study_information/` | Lokale HTML-snapshots af studieplaner og specialiseringer |
| `migrations/` | Ændringer til databaseskemaet |
| `connector/` | Connector-definition til Microsoft Copilot Studio |

## Datakilder

Kursusnumre og kursusoplysninger kommer fra DTU Kursusbasens officielle
`CourseWebServiceV2`. Studieplaner og specialiseringer kommer fra DTU's
officielle studieordningssider. Deres rå HTML gemmes i
`app/data/study_information/`, før den parses og importeres. Importerne gemmer
data lokalt, så almindelige søgninger og chatsvar ikke kræver et live opslag
hos DTU.
