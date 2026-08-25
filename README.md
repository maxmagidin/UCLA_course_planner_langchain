# UCLA Course Planner — LangChain / LangGraph

[![CI](https://github.com/maxmagidin/UCLA_course_planner_langchain/actions/workflows/ci.yml/badge.svg?branch=langchain-migration)](https://github.com/maxmagidin/UCLA_course_planner_langchain/actions/workflows/ci.yml)

> [!WARNING]
> **Work in progress.** This project was moved from ASI:One/Agentverse to
> LangChain and LangGraph and is still being developed.

A UCLA course planner with a Vite/React frontend and FastAPI backend. Upload or
paste a DARS, review the parsed courses, and build a plan for one quarter or an
academic year. The core planner does not require an API key.

## Background

This is a rework of the ASI:One hackathon-winning
[original UCLA Course Planner](https://github.com/matthewdo823-ui/UCLA_course_planner_agent).
The original version used eight Fetch.ai uAgents and was published through
[Agentverse](https://agentverse.ai/) and [ASI:One](https://asi1.ai/). Its
[Agentverse listing is still available here](https://agentverse.ai/agents/details/agent1qvzm8976yty6m5zvtfpdhp55mxy0qdf6mhhzc557tvgs4gwv85ck6g7qpng).

The refactor uses LangGraph for orchestration while keeping the planner
compatible with different model providers and independent of the ASI platform.
Docker makes it easier for other Bruins to run it themselves.

This branch replaces that runtime with one LangGraph workflow. It is no longer
hosted on ASI:One or Agentverse. The old adapter remains in the repository for
reference and compatibility.

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
- Supports optional model-assisted profile autofill with a user-provided key.

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

## Optional bring-your-own-key autofill

DARS parsing, prerequisite checks, schedule generation, ranking, and reporting
do not use a model. A key is only needed for the optional natural-language
autofill panel.

The browser sends that key only to `/api/intake`. It is not stored in browser
storage, planner checkpoints, reports, or job records.

Fork owners can also configure an OpenAI-compatible provider in `.env`:

```bash
MODEL_PROVIDER=openai_compatible
MODEL_API_KEY=your-key
MODEL_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o-mini
```

ASI:One can still be used as an optional model provider, but doing so does not
republish this application to ASI:One or Agentverse.

## API and persistence

The full OpenAPI documentation is available at `/docs`. Main routes include:

- `POST /api/dars/parse`
- `POST /api/intake`
- `POST /api/roadmap/suggest`
- `POST /api/plan`
- `POST /api/plan/horizon/jobs`
- `GET /api/jobs/{job_id}`
- `DELETE /api/jobs/{job_id}`

Graph checkpoints and background jobs use SQLite at
`.data/planner.sqlite3`, or `/app/.data/planner.sqlite3` in Docker. Raw DARS
text is removed before job requests and graph state are persisted. Other job
and result fields can still contain student information, so protect the
database file.

Background-job settings are documented in `.env.example`:

- `PLANNER_JOB_WORKERS`
- `PLANNER_MAX_QUEUED_JOBS`
- `PLANNER_JOB_RETENTION_DAYS`

## Optional data sources

Quick local runs use current UCLA enrollment, UCLA Catalog entries, and public
grade data. Slower sources are disabled by default:

```bash
PLANNER_ENABLE_HISTORICAL_ENROLLMENT=true
PLANNER_ENABLE_BRUINWALK=true
```

The default Docker image does not include the Playwright browser binary needed
for Bruinwalk scraping. Grade loading can be disabled with
`PLANNER_ENABLE_GRADES=false`.

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

## Legacy compatibility

`python run_all.py` starts the remaining Agent Chat Protocol compatibility
surface. It is not the default runtime and is not published through Agentverse.

## License

Licensed under the [MIT License](LICENSE). The original repository and
third-party services retain their own terms.
