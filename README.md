# UCLA Course Planner — LangChain / LangGraph

[![CI](https://github.com/maxmagidin/UCLA_course_planner_langchain/actions/workflows/ci.yml/badge.svg?branch=langchain-migration)](https://github.com/maxmagidin/UCLA_course_planner_langchain/actions/workflows/ci.yml)

> [!WARNING]
> **Work in progress.** The core planner is deterministic and model-independent.
> Optional preference translation supports OpenAI-compatible APIs and native
> Anthropic Claude through LangChain.

A UCLA course planner with a Vite/React frontend and FastAPI backend. Upload or
paste a DARS, review the parsed courses, and build a plan for one quarter or an
academic year. The core planner does not require an API key.

## Architecture

The planner uses LangGraph to orchestrate ordinary Python retrieval, parsing,
validation, scheduling, and ranking steps. Those steps remain independent of
any model platform. Optional natural-language enhancement uses a transient,
request-scoped OpenAI or Anthropic configuration supplied by the client. No
server-owned model credentials are required or read.

### What deterministic means here

The planner does not ask a language model to read UCLA pages, decide whether a
prerequisite is satisfied, build schedules, or assign scores. Instead:

1. `httpx` makes ordinary HTTPS requests to the public UCLA Schedule of
   Classes and Catalog endpoints, Bruinwalk pages, and published grade-data
   spreadsheets.
2. Purpose-built parsers read known JSON, HTML, and CSV fields into typed
   records. PDF text extraction and explicit patterns classify DARS courses;
   the user reviews those classifications before planning.
3. Prerequisite code evaluates catalog expressions against confirmed completed
   courses. The schedule solver enumerates compatible lecture and discussion
   combinations, then rejects time, unit, day-off, and format violations.
4. Ranking code applies the visible numeric weights to the resulting facts.
   Missing or unparseable evidence is reported as missing or partial rather
   than guessed.

For the same reviewed inputs, source snapshot, and settings, these rules
produce the same result. Live results can still change when UCLA changes a
section, enrollment count, instructor, or catalog description. “Deterministic”
describes how evidence is processed; it does not freeze changing source data.

LangGraph is the workflow engine, not the source of academic judgment. It runs
the retrieval branches, joins their typed results, and records progress and
source status. The optional model can only propose edits to planning
preferences from a strict allow-list. It cannot alter DARS facts, catalog
facts, prerequisites, ratings, schedule generation, or ranking code.

## What it does

- Parses DARS text or PDF uploads locally.
- Separates completed, in-progress, remaining, and unclassified courses for
  review.
- Checks prerequisites and corequisites against the UCLA Catalog.
- Plans one quarter or Fall through Spring, with optional Summer.
- Carries completed courses forward between quarters.
- Builds section-level schedules using UCLA Schedule of Classes data.
- Applies unit, time, day-off, and format constraints.
- Shows data freshness, enrollment-risk labels, and partial failures.
- Supports optional model-assisted preference proposals with a user-provided
  key. Proposals are typed, allow-listed, and always require review.

## Run with Docker

Docker is the quickest way to run the full frontend and backend. Install Docker
Desktop, or Docker Engine with the Compose plugin, then run:

```bash
git clone -b langchain-migration https://github.com/maxmagidin/UCLA_course_planner_langchain.git
cd UCLA_course_planner_langchain
docker compose up --build
```

Open:

- App: <http://localhost:8765/app/>
- API docs: <http://localhost:8765/docs>
- Readiness check: <http://localhost:8765/api/ready>

No API key is required. For optional configuration:

```bash
cp .env.example .env
docker compose up --build
```

The `.env` file is ignored by Git and excluded from the Docker build context.

Common commands:

```bash
docker compose up --build -d    # start in the background
docker compose ps               # check container health
docker compose logs -f planner  # follow logs
docker compose down             # stop and keep planner data
```

SQLite data is stored in the `planner-data` Docker volume and survives normal
restarts. `docker compose down --volumes` permanently deletes that local data.

To update a checkout:

```bash
git pull
docker compose build --pull
docker compose up -d
```

## Run from source

Requires Python 3.10+ and Node 22+.

```bash
git clone -b langchain-migration https://github.com/maxmagidin/UCLA_course_planner_langchain.git
cd UCLA_course_planner_langchain
make setup
make run
```

Open <http://localhost:8765/app/>.

For frontend development, run these in separate terminals:

```bash
make backend       # FastAPI on http://localhost:8765
make frontend-dev  # Vite on http://localhost:5173
```

Vite proxies `/api` requests to FastAPI during development.

## How planning works

1. Upload a DARS PDF, paste DARS text, or enter completed courses manually.
2. Review the parsed course categories. Only confirmed completed courses count
   toward prerequisite eligibility.
3. Confirm the student profile and choose a quarter or academic year.
4. Assign courses manually or auto-place remaining courses by prerequisite
   order.
5. Set unit and schedule constraints, then run the planner.
6. Review schedules, warnings, source status, and the downloadable report.

The prerequisite check reads official UCLA Catalog entries. Missing or unclear
catalog information is shown for review instead of assuming eligibility.
Section-level results require a published UCLA Schedule of Classes term, so
future quarters may return partial results until UCLA publishes them.

## CLI and Python

Run the checked-in example profile:

```bash
.venv/bin/python -m course_planner.agent examples/profile.json
```

With Docker:

```bash
docker compose exec planner python -m course_planner.agent examples/profile.json
```

Python entrypoint:

```python
from course_planner.graph import run_planner
from course_planner.planner_models import StudentProfile

profile = StudentProfile.model_validate(profile_dict)
result = run_planner(profile)
print(result.report_markdown)
```

## Optional bring-your-own-key enhancement

DARS parsing, prerequisite checks, schedule generation, ranking, and reporting
do not use a model. `POST /api/planning/enhance` optionally uses OpenAI,
Anthropic Claude, or a custom OpenAI-compatible model to return a typed
preference patch for user review. Hosted providers normally need a key; a
local model may not. Any supplied key is never returned, persisted, or read
from process environment.

The easiest local BYOK flow is:

1. Start the app and open <http://localhost:8765/app/>.
2. Continue to planning configuration and expand **Optional preference
   translation**.
3. Choose **OpenAI**, **Anthropic Claude**, or **Custom / local model**.
4. For a hosted provider, paste its API key. Confirm the model and base URL,
   then describe the preferences in plain language.
5. Select **Translate preferences**, compare the current and suggested inputs,
   and explicitly apply the proposal if it is correct.

The defaults are `gpt-4o-mini` at `https://api.openai.com/v1` for OpenAI and
`claude-haiku-4-5-20251001` at `https://api.anthropic.com` for Claude. Claude
uses LangChain's native Anthropic integration, not an OpenAI compatibility
shim. Use **Custom / local model** for Ollama, vLLM, or a third-party service
that implements OpenAI chat completions.

The key exists in the browser field and request memory while that one call is
running, travels through the local FastAPI backend to the selected provider,
and is cleared from frontend state when the request finishes. It is not stored
in local storage, the planner job, graph state, SQLite, or the response. For a
local hosted-provider run, pasting a restricted project key into the password
field is the simplest path; putting a key in `.env` has no effect by design.

### Run your own local model

Ollama publishes an OpenAI-compatible endpoint. For example, install and start
Ollama, then download the default local model:

```bash
ollama pull llama3.2
ollama serve
```

With the planner running in Docker, select **Custom / local model** and use:

```text
Model: llama3.2
Base URL: http://host.docker.internal:11434/v1
API key: leave blank
```

When running the planner directly from source instead of Docker, use
`http://127.0.0.1:11434/v1`. Other OpenAI-compatible servers work the same way:
enter their model identifier, base URL, and a key if that server requires one.
The model must return the strict preference-patch JSON contract; invalid model
output is rejected and never changes the planning inputs.

Local HTTP endpoints are accepted only for the custom-model provider, only
while `PLANNER_PUBLIC_DEPLOYMENT=false`, and only for loopback or Docker's
`host.docker.internal`. Arbitrary LAN/private addresses remain blocked. Public
deployments require HTTPS and `MODEL_HOST_ALLOWLIST`; configure the
comma-separated provider hostnames the service may contact, such as
`api.openai.com,api.anthropic.com`.

See Ollama's [OpenAI compatibility documentation](https://docs.ollama.com/api/openai-compatibility)
for its supported endpoint and model-management commands.

## How current and future UCLA data is handled

The application retrieves data when a plan runs; it does not need an LLM or a
manually trained knowledge base for each academic year.

| Source | How it is read | What happens for a new term or year |
| --- | --- | --- |
| UCLA Schedule of Classes | UCLA's public search response and course-detail endpoints | A label such as `Fall 2027` is converted to UCLA's `27F` term code. Once UCLA publishes that term, the same scraper can retrieve it without a code release. Before publication, the plan reports partial or missing section data. |
| UCLA Catalog | The requested course page's embedded structured data | The catalog year is derived from the requested quarter. Fall starts a new academic catalog year; Winter, Spring, and Summer use the preceding Fall's catalog year. |
| Current enrollment | Section enrollment, capacity, and waitlist fields in the live Schedule of Classes | New counts are fetched on each planning run. They are snapshots, so the result records when they were fetched. |
| Historical enrollment | Up to four recent published quarters from UCLA sources | The bounded lookback window advances with the calendar. Independent course lookups run in a small worker pool; final-only records are not misrepresented as day-one or day-seven snapshots. |
| Bruinwalk | Known fields on current course and professor pages, with instructor/course identity checks | Current pages are fetched at run time. If Bruinwalk changes its page structure, the parser returns no rating or a partial source status until it is updated. |
| Grade distributions | Published spreadsheet CSV exports | Existing configured sheets are downloaded and parsed automatically. A newly published spreadsheet must be added to the source list; the program does not discover arbitrary new grade sheets. |

Any source can change an endpoint or page structure. Retrieval failures are
isolated by source, visible in the result, and do not authorize a model to fill
in missing facts. Parser fixtures and live smoke tests are the maintenance
mechanism when a source changes.

## API and persistence

The full OpenAPI documentation is available at `/docs`. Main routes include:

- `POST /api/dars/parse`
- `POST /api/planning/enhance`
- `POST /api/roadmap/suggest`
- `POST /api/plan`
- `POST /api/plan/horizon/jobs`
- `GET /api/jobs/{job_id}`
- `DELETE /api/jobs/{job_id}`

Background jobs use SQLite at `.data/planner.sqlite3`, or
`/app/.data/planner.sqlite3` in Docker. Graph checkpoints remain in memory by
default because the current workflow has no pause/resume boundary; set
`PLANNER_PERSIST_GRAPH_CHECKPOINTS=true` only when implementing resume with an
appropriate retention policy. Raw DARS text is removed before job requests and
graph state are persisted. Other job and result fields can still contain
student information, so protect the database file.

Background-job settings are documented in `.env.example`:

- `PLANNER_JOB_WORKERS`
- `PLANNER_MAX_QUEUED_JOBS`
- `PLANNER_JOB_RETENTION_DAYS`
- `PLANNER_PERSIST_GRAPH_CHECKPOINTS`

## Data-source controls

Current enrollment, UCLA Catalog entries, public grade data, historical
enrollment, and Bruinwalk enrichment are enabled by default. To trade evidence
for a faster local run, individual slower sources can be disabled:

```bash
PLANNER_ENABLE_HISTORICAL_ENROLLMENT=false
PLANNER_ENABLE_BRUINWALK=false
PLANNER_ENABLE_GRADES=false
```

Enrollment risk is a heuristic, not a probability or enrollment guarantee.
Meeting times marked TBA or left unparsed have incomplete conflict checks.

## GitHub Pages

GitHub Pages can host the Vite build but cannot run FastAPI. A working Pages
deployment needs a separately hosted backend. Set `VITE_API_BASE_URL` during
the frontend build and allow the Pages origin with `FRONTEND_ORIGINS` on the
backend.

## Development

Run the same checks used by GitHub Actions:

```bash
make check
npm --prefix frontend run build
```

Tests mock UCLA network requests. Parser changes should include a de-identified
fixture. Do not commit DARS reports, student identifiers, API keys, or cookies.

## Deployment notes

- The SQLite job runner is intended for one application process. The Docker
  image uses one Uvicorn worker for this reason.
- Public multi-user hosting still needs authentication, encrypted student-data
  storage, and an appropriate retention policy.
- A multi-instance deployment should use a managed database and external task
  queue instead of the local SQLite worker.
- UCLA data retrieval requires outbound network access.

## License

Licensed under the [MIT License](LICENSE). The original repository and
third-party services retain their own terms.
