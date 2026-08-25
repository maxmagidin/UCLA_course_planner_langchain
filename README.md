# UCLA Course Planner — LangChain / LangGraph

[![CI](https://github.com/maxmagidin/UCLA_course_planner_langchain/actions/workflows/ci.yml/badge.svg?branch=langchain-migration)](https://github.com/maxmagidin/UCLA_course_planner_langchain/actions/workflows/ci.yml)

> [!WARNING]
> **Work in progress.** This project is being actively rebuilt and extended. It
> was reworked from the original ASI:One/Agentverse course-planning project to
> LangChain and LangGraph, and new planning, data, and user-experience features
> are now being built on top of that migration.

This version keeps the original project's UCLA data sources and scheduling
domain logic, but replaces the eight-process `uagents` message pipeline with
one typed, checkpointed LangGraph workflow.

## Project history

This project began as the ASI:One hackathon-winning
[original UCLA Course Planner multi-agent pipeline](https://github.com/matthewdo823-ui/UCLA_course_planner_agent):
eight independent agents built with
[Fetch.ai uAgents](https://uagents.fetch.ai/docs), published through
[Agentverse](https://agentverse.ai/), and accessible from
[ASI:One](https://asi1.ai/). The historical entry point is preserved in the
[original Agentverse listing](https://agentverse.ai/agents/details/agent1qvzm8976yty6m5zvtfpdhp55mxy0qdf6mhhzc557tvgs4gwv85ck6g7qpng),
and the original architecture and source remain available in the original
repository linked above.

The `langchain-migration` branch is an active rework and continuation of that
project. Its orchestration was rewritten with LangChain and LangGraph, and this
version was taken off the ASI:One/Agentverse platform. Development is now
building on top of the migrated workflow. It runs directly as a local web app,
HTTP API, CLI, or Python library. The old ASI:One adapter remains in the
repository only as a compatibility reference; it is not the deployed runtime.

## Architecture

```text
user / CLI / web API / Agent Chat Protocol
          |
 configured-model structured intake
          |
  PlannerState (thread_id + run_id)
          |
  retrieve classes
             |
 prerequisite agent             <- official UCLA Catalog, deterministic
      /      |       \
 enrollment ratings  grades     <- explicit parallel branches
      \      |       /
       merge evidence
             |
     deterministic schedule solver
             |
       deterministic ranking
             |
        evidence-first report
```

The model is used only for optional conversational intake. The prerequisite
agent reads the server-rendered data in the
[official UCLA Catalog](https://catalog.registrar.ucla.edu/), parses enforced
AND/OR and corequisite groups, and compares them with reviewed completed
coursework. Missing or ambiguous catalog evidence is never treated as proof of
eligibility. Retrieval, eligibility, hard constraints, schedule generation,
ranking, and reporting stay deterministic and testable. Direct planning does
not need an API key.

## Fork and run it

The repository contains both the FastAPI/LangGraph backend and the complete
Vite frontend. A fork does not need a hosted service or a project-owned model
key. Install Python 3.10+ and Node 22+, then run:

```bash
git clone -b langchain-migration https://github.com/maxmagidin/UCLA_course_planner_langchain.git
cd UCLA_course_planner_langchain
make setup
make run
```

Open <http://127.0.0.1:8765/app/>. `make setup` creates `.venv`, installs the
Python and npm dependencies, and builds the frontend. `make run` rebuilds the
frontend and serves the entire application from FastAPI. The checked-in GitHub
Actions workflow performs the same frontend build and backend test suite for
pushes and pull requests.

To configure the pieces manually:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
.venv/bin/python -m uvicorn course_planner.api:app --host 127.0.0.1 --port 8765
```

## Browser workflow

The React application is a complete interface over the same public API used by
the CLI and Python entrypoint:

1. **DARS:** upload a PDF or paste text, then review separately classified
   completed, in-progress, remaining, and unclassified course codes. Only the
   completed list unlocks prerequisites.
2. **Student:** confirm the profile fields DARS supplied and fill any gaps.
   Model-assisted autofill is optional.
3. **Plan:** choose one published quarter or an academic year. Assign required
   and preferred courses yourself, or auto-place remaining audit courses in
   their earliest prerequisite-safe term using the official catalog. Then set
   unit ranges, schedule constraints, and ranking preferences.
4. **Results:** compare section-level schedules, evidence freshness, partial
   failures, and downloadable Markdown reports.

In academic-year mode, catalog-based auto-placement respects prerequisite
order before the run, and the top valid schedule from each term is added to
completed coursework before the next term runs. Corequisites must appear in
the same selected schedule or already be complete. Section-level results still
depend on published UCLA Schedule of Classes data; unpublished future terms
are clearly returned as partial or failed rather than fabricated.

For frontend development, run the backend and Vite dev server in separate
terminals. Vite proxies `/api` to FastAPI:

```bash
make backend       # http://127.0.0.1:8765
make frontend-dev  # http://127.0.0.1:5173
```

The frontend uses Vite, React, TypeScript, Tailwind CSS, local shadcn-style
components, Radix primitives, and Lucide icons. `frontend/components.json`
keeps it compatible with the shadcn CLI, while the generated component source
remains owned by this repository.

## Bring your own key

No key is needed for DARS parsing, retrieval, prerequisite checks, schedule
generation, ranking, or reporting. The collapsed **Optional model autofill**
panel accepts an OpenAI, OpenRouter, ASI:One, or custom OpenAI-compatible key
only when a user wants natural-language intake.

The key remains in React component memory and is sent only with the `/api/intake`
request. It is represented as a Pydantic secret and is not written to planner
state, reports, checkpoints, browser storage, or API responses. Fork owners can
also configure a model through environment variables for CLI or server-owned
flows:

To exercise the CLI with the same profile:

```bash
python -m course_planner.agent examples/profile.json
```

Set the model configuration in the environment; do not put API keys in source files:

```bash
export MODEL_PROVIDER="openai_compatible"
export MODEL_API_KEY="..."
export MODEL_BASE_URL="https://api.openai.com/v1"
export MODEL_NAME="gpt-4o-mini"
```

Any provider that exposes an OpenAI-compatible chat-completions API can use
the same code. Only the key, base URL, and model name change. ASI:One is an
optional preset:

```bash
export MODEL_PROVIDER="asi_one"
export MODEL_API_KEY="..."
export MODEL_BASE_URL="https://api.asi1.ai/v1"
export MODEL_NAME="asi1"
```

This optional preset uses ASI:One only as the model API. It does not publish
the migrated application to ASI:One or Agentverse.

BYOK base URLs must use HTTPS and literal localhost/private-network targets
are rejected by default so a public fork does not expose an obvious server-side
request-forgery path. A developer intentionally connecting a local compatible
model can set `ALLOW_INSECURE_MODEL_BASE_URLS=true` and
`ALLOW_PRIVATE_MODEL_BASE_URLS=true`; do not enable those flags on a public
deployment. Production operators should also enforce an outbound hostname
allowlist at the network layer.

## Static hosting and GitHub Pages

Vite can build the frontend for GitHub Pages, but Pages cannot run the Python
backend. To publish a fully working browser demo, deploy FastAPI separately,
set `VITE_API_BASE_URL` to that HTTPS API during the frontend build, set
`VITE_BASE_PATH` to the repository path, and allow the Pages origin with the
backend `FRONTEND_ORIGINS` environment variable. Never use a project-owned
provider key in a public browser build; keep the existing BYOK request path.

Optional LangSmith tracing:

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY="..."
export LANGSMITH_PROJECT="ucla-course-planner"
```

## Run the graph locally

Create a profile JSON. The term is intentionally required so the planner does
not silently plan against an old quarter:

```json
{
  "name": "Alex Student",
  "major": "Computer Science",
  "year": "junior",
  "gpa": 3.6,
  "units_completed": 96,
  "enrollment_pass": "pass_1",
  "pass_open_datetime": "2026-08-28 09:00",
  "term": "Fall 2026",
  "dars_courses": ["COM SCI 31", "MATH 31A"],
  "required_courses": ["COM SCI 111"],
  "preferred_courses": ["COM SCI 118"],
  "hard_constraints": ["No classes before 10:00 am", "Friday off"],
  "format_preference": "any",
  "min_units": 12,
  "max_units": 16
}
```

Then (or use the checked-in `examples/profile.json`):

```bash
python -m course_planner.agent profile.json
```

The public Python entrypoint is also available:

```python
from course_planner.graph import run_planner
from course_planner.planner_models import StudentProfile

result = run_planner(StudentProfile.model_validate(profile_dict))
print(result.report_markdown)
```

The `/chat` endpoint accepts a conversation plus a transient `model` object:

```json
{
  "conversation": [{"role": "user", "content": "I am Alex, a junior Computer Science major..."}],
  "model": {
    "provider": "openai_compatible",
    "api_key": "the-user's-key",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini"
  }
}
```

This is BYOK at the application boundary. Use HTTPS, do not log request bodies,
and do not send provider keys through Agent Chat Protocol messages. For a
multi-user production service, encrypt or avoid storing keys and preferably
keep the key only in the user's browser or server-side secret manager.

## User documents and data coverage

- A profile can include `dars_courses` directly.
- The HTTP `/chat` and `/intake` endpoints accept either `dars_text` or a
  base64-encoded `dars_pdf_base64`. The PDF is parsed locally and course codes
  are extracted deterministically before planning.
- The default local path reads live UCLA classes/current enrollment and public
  UCLA grade distributions, plus current official UCLA Catalog descriptions
  for every candidate's prerequisite check. It caps expansion at 12 courses
  per department so a first run stays bounded.
- Enrollment availability is a section-specific heuristic with an explicit
  confidence label, not a calibrated probability. TBA/unparseable meeting
  times are surfaced as incomplete conflict checks.
- Historical quarter lookups and Bruinwalk scraping are opt-in because those
  sources add many slow requests and can require a local Playwright browser:

  ```bash
  export PLANNER_ENABLE_HISTORICAL_ENROLLMENT=true
  export PLANNER_ENABLE_BRUINWALK=true
  ```

  `PLANNER_ENABLE_GRADES=false` skips grade-sheet loading, and
  `PLANNER_MAX_COURSES_PER_DEPARTMENT=20` changes the default course cap.
- A separate course-reader upload is not yet a first-class evidence source.
  It should be added as another typed retrieval tool and evidence record rather
  than silently mixing arbitrary PDF text into the model prompt.

Each `run_planner` call uses an isolated LangGraph `InMemorySaver` by default.
Pass a database-backed checkpointer plus stable `thread_id`/`run_id` values in
production when a user must change a constraint and resume an existing run.

## Legacy ASI:One compatibility surface

The current project is not published on ASI:One or Agentverse. Its supported
entry points are the local web app, HTTP API, CLI, and `run_planner()` Python
function described above.

For historical compatibility, `python run_all.py` can still start one Agent
Chat Protocol surface instead of the original eight workers. The adapter lives
in `course_planner/asi_surface.py` and does three things:

1. Acknowledge an incoming `ChatMessage`.
2. Accumulate the conversation and ask the configured model provider for a
   validated `StudentProfile` using LangChain structured output.
3. Invoke the same graph and return the Markdown report.

If somebody deliberately republishes it, that adapter can make the product
appear as one UCLA Course Planner agent in Agentverse or an ASI:One-compatible
chat client. It is not published by this branch. The graph remains reusable
from a web app, CLI, or API; the surface is only a transport adapter. You do not
need to use it: call `run_planner(profile)` from your own application.

The provider factory lives in `course_planner/model_provider.py`. The graph
does not know which model provider is being used. If the planner itself should
delegate to Agentverse agents, add ASI:One `planner_mode` and a stable
`x-session-id` through the optional compatibility path; do not enable it for
the core planner by default because the application already has an explicit
graph and hard constraints.

## Important migration notes

- `course_planner/agents/` is retained only as a compatibility reference. The
  new runtime does not launch those workers.
- The schedule solver now lives in the side-effect-free
  `course_planner/scheduling.py` domain module. FastAPI and LangGraph do not
  import or initialize legacy `uagents` workers.
- The old runtime bugs were corrected in the compatibility files: the schedule
  message loop, the grade-distribution early return, the stale term, and the
  committed ASI key.
- Recommended production follow-ups are a persistent database checkpointer,
  background jobs with progress/cancellation for long horizons, broader DARS
  fixture coverage, and calibrated enrollment-risk evaluation.
