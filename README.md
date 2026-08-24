# UCLA Course Planner — LangChain / LangGraph

This version keeps the original UCLA data sources and scheduling domain logic,
but replaces the eight-process `uagents` message pipeline with one typed,
checkpointed LangGraph workflow.

## Architecture

```text
user / CLI / web API / Agent Chat Protocol
          |
 configured-model structured intake
          |
  PlannerState (thread_id + run_id)
          |
  retrieve classes
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

The model is used only for optional conversational intake. Retrieval,
prerequisite filtering, hard constraints, schedule generation, ranking, and
reporting stay deterministic and testable. Direct planning does not need an
API key.

## Install

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.10 or newer is required.

## Test it now in the browser

```bash
source .venv/bin/activate
uvicorn course_planner.api:app --reload
```

Open <http://127.0.0.1:8000>. The form is prefilled with three Fall 2026
Computer Science courses that currently produce valid schedule candidates.
Click **Run direct plan**; no model key is needed. The planner uses the live
UCLA Schedule of Classes, so this path requires internet access.

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
  UCLA grade distributions. It caps expansion at 12 courses per department so
  a first run stays bounded.
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

## External usage and optional ASI:One surface

`python run_all.py` now starts one Agent Chat Protocol surface instead of eight
workers. The adapter lives in `course_planner/asi_surface.py` and does three
things:

1. Acknowledge an incoming `ChatMessage`.
2. Accumulate the conversation and ask the configured model provider for a
   validated `StudentProfile` using LangChain structured output.
3. Invoke the same graph and return the Markdown report.

That makes the product appear as one UCLA Course Planner agent in Agentverse or
an ASI:One-compatible chat client. The graph remains reusable from a web app,
CLI, or API; the surface is only a transport adapter. You do not need to use
this surface at all: call `run_planner(profile)` from your own application.

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
- The next production step is a persistent checkpointer plus broader
  prerequisite-matching and ranking regression coverage.
