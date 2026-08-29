"""FastAPI boundary for deterministic planning and optional BYOK enhancement."""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from course_planner.documents import (
    classify_dars_courses,
    extract_course_codes,
    extract_dars_hints,
    extract_text_from_pdf_base64,
)
from course_planner.graph import run_planner
from course_planner.intake import PreferenceValidationError, enhance_planning
from course_planner.jobs import JobQueueFull, get_job_manager
from course_planner.persistence import database_ready
from course_planner.planner_models import (
    EnhancementContext,
    EnhancementResponse,
    ModelConfig,
    PlannerResult,
    StudentProfile,
)
from course_planner.roadmap import suggest_roadmap
from course_planner.terms import parse_ucla_term


class PlanningEnhanceRequest(BaseModel):
    model_config = {"extra": "forbid"}

    description: str = Field(min_length=1, max_length=10_000)
    context: EnhancementContext
    model: ModelConfig


class PlanRequest(BaseModel):
    model_config = {"extra": "forbid"}

    profile: StudentProfile


class HorizonTerm(BaseModel):
    term: str = Field(min_length=1, max_length=80)
    required_courses: list[str] = Field(default_factory=list, max_length=30)
    preferred_courses: list[str] = Field(default_factory=list, max_length=30)
    min_units: int = Field(default=12, ge=0, le=30)
    max_units: int = Field(default=16, ge=0, le=30)

    @model_validator(mode="after")
    def validate_unit_range(self) -> HorizonTerm:
        if self.max_units < self.min_units:
            raise ValueError("max_units must be greater than or equal to min_units")
        return self

    @model_validator(mode="after")
    def validate_term(self) -> HorizonTerm:
        self.term = parse_ucla_term(self.term).label
        return self


class HorizonPlanRequest(BaseModel):
    profile: StudentProfile
    terms: list[HorizonTerm] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def prevent_cross_term_duplicates(self) -> HorizonPlanRequest:
        assigned: dict[str, str] = {}
        duplicates: set[str] = set()
        for term in self.terms:
            for raw_code in term.required_courses + term.preferred_courses:
                code = " ".join(raw_code.upper().split())
                if not code:
                    continue
                previous = assigned.get(code)
                if previous and previous != term.term:
                    duplicates.add(code)
                assigned[code] = term.term
        if duplicates:
            raise ValueError(
                "Assign each course to one term only: " + ", ".join(sorted(duplicates))
            )
        return self


class HorizonTermResult(BaseModel):
    term: str
    planned_courses: list[str]
    completed_courses_after_term: list[str]
    result: PlannerResult


class HorizonPlanResponse(BaseModel):
    run_id: str
    status: Literal["completed", "partial", "failed"]
    terms: list[HorizonTermResult]
    completed_courses: list[str]


class RoadmapRequest(BaseModel):
    profile: StudentProfile
    courses: list[str] = Field(min_length=1, max_length=60)
    terms: list[HorizonTerm] = Field(min_length=1, max_length=4)


class RoadmapTermResponse(BaseModel):
    term: str
    courses: list[str]
    total_units: float


class RoadmapResponse(BaseModel):
    terms: list[RoadmapTermResponse]
    unplaced_courses: list[str]
    warnings: list[str]


class PlannerJobResponse(BaseModel):
    id: str
    kind: str
    status: Literal[
        "queued",
        "running",
        "cancelling",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
    ]
    progress: int = Field(ge=0, le=100)
    message: str
    result: HorizonPlanResponse | None = None
    error: str = ""
    created_at: str
    updated_at: str


class DarsParseRequest(BaseModel):
    model_config = {"extra": "forbid"}

    dars_text: str | None = Field(default=None, max_length=2_000_000)
    dars_pdf_base64: str | None = Field(default=None, max_length=30_000_000)


class DarsParseResponse(BaseModel):
    source: Literal["text", "pdf"]
    character_count: int
    course_codes: list[str]
    completed_courses: list[str]
    in_progress_courses: list[str]
    remaining_courses: list[str]
    unclassified_courses: list[str]
    profile_hints: dict[str, str | float]
    profile_draft: dict[str, Any]
    course_buckets: dict[str, list[str]]
    provenance: dict[str, str]
    missing_fields: list[str]
    warnings: list[str]


@asynccontextmanager
async def _lifespan(_: FastAPI):
    manager = get_job_manager()
    yield
    manager.shutdown()


app = FastAPI(title="UCLA Course Planner", version="0.6.0", lifespan=_lifespan)


@app.middleware("http")
async def security_headers(request: FastAPIRequest, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith(("/api/", "/jobs/", "/plan/", "/dars/")):
        response.headers["Cache-Control"] = "no-store"
    return response


_frontend_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]
if _frontend_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

_frontend_dist_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if (_frontend_dist_dir / "index.html").exists():
    app.mount("/app", StaticFiles(directory=_frontend_dist_dir, html=True), name="app")
else:
    _frontend_setup_page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Build the UCLA Course Planner frontend</title></head>
<body style="font:16px/1.6 system-ui;max-width:720px;margin:80px auto;padding:0 24px">
<h1>Frontend build needed</h1><p>The API is running. Build the Vite frontend, then restart this server:</p>
<pre style="padding:16px;background:#f3f4f6;border-radius:10px">cd frontend\nnpm install\nnpm run build</pre>
</body></html>"""

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    def unbuilt_frontend(path: str = "") -> HTMLResponse:
        return HTMLResponse(_frontend_setup_page, status_code=503)


@app.get("/", include_in_schema=False)
def frontend() -> RedirectResponse:
    return RedirectResponse(url="/app/")


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
@app.get("/api/ready")
def ready() -> dict[str, Any]:
    storage_ready, storage_detail = database_ready()
    workers = get_job_manager().ready()
    if not storage_ready or not workers["ready"]:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "storage": storage_detail,
                "workers": workers,
            },
        )
    return {
        "status": "ready",
        "storage": "sqlite",
        "workers": workers,
    }


@app.post("/api/dars/parse", response_model=DarsParseResponse)
async def parse_dars(request: DarsParseRequest) -> DarsParseResponse:
    text = await asyncio.to_thread(
        _document_text, request.dars_text, request.dars_pdf_base64
    )
    if not text or not text.strip():
        raise HTTPException(
            status_code=400, detail="Paste DARS text or upload a readable DARS PDF"
        )
    classified = classify_dars_courses(text)
    hints = extract_dars_hints(text)
    course_buckets = {
        "completed": classified["completed"],
        "in_progress": classified["in_progress"],
        "remaining": classified["remaining"],
        "unclassified": classified["unclassified"],
    }
    profile_draft = {
        **hints,
        "dars_courses": classified["completed"],
        "dars_in_progress_courses": classified["in_progress"],
        "dars_remaining_courses": classified["remaining"] + classified["unclassified"],
    }
    missing_fields = [
        field for field in ("name", "major", "term") if field not in hints
    ]
    warnings = [
        "Course classification is reviewable; only confirmed completed courses should be used for eligibility."
    ]
    if classified["unclassified"]:
        warnings.append("Some course codes could not be classified and require review.")
    return DarsParseResponse(
        source="pdf" if request.dars_pdf_base64 else "text",
        character_count=len(text),
        course_codes=extract_course_codes(text),
        completed_courses=classified["completed"],
        in_progress_courses=classified["in_progress"],
        remaining_courses=classified["remaining"],
        unclassified_courses=classified["unclassified"],
        profile_hints=hints,
        profile_draft=profile_draft,
        course_buckets=course_buckets,
        provenance={field: "dars" for field in hints},
        missing_fields=missing_fields,
        warnings=warnings,
    )


@app.post("/api/planning/enhance", response_model=EnhancementResponse)
async def planning_enhance(request: PlanningEnhanceRequest) -> EnhancementResponse:
    try:
        return await asyncio.to_thread(
            enhance_planning,
            request.description,
            request.context,
            request.model,
        )
    except PreferenceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Model enhancement failed") from exc


@app.post("/plan", response_model=PlannerResult)
@app.post("/api/plan", response_model=PlannerResult)
async def plan(request: PlanRequest) -> PlannerResult:
    return await asyncio.to_thread(run_planner, request.profile)


@app.post("/plan/horizon", response_model=HorizonPlanResponse)
@app.post("/api/plan/horizon", response_model=HorizonPlanResponse)
async def plan_horizon(request: HorizonPlanRequest) -> HorizonPlanResponse:
    return await asyncio.to_thread(_run_horizon, request)


@app.post("/plan/horizon/jobs", response_model=PlannerJobResponse, status_code=202)
@app.post("/api/plan/horizon/jobs", response_model=PlannerJobResponse, status_code=202)
async def create_horizon_job(request: HorizonPlanRequest) -> PlannerJobResponse:
    try:
        job = await asyncio.to_thread(
            get_job_manager().submit,
            "horizon",
            request.model_dump(mode="json"),
            _run_horizon_job,
        )
    except (JobQueueFull, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return PlannerJobResponse.model_validate(job)


@app.get("/jobs/{job_id}", response_model=PlannerJobResponse)
@app.get("/api/jobs/{job_id}", response_model=PlannerJobResponse)
async def get_planner_job(job_id: str) -> PlannerJobResponse:
    job = await asyncio.to_thread(get_job_manager().get, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Planner job not found")
    return PlannerJobResponse.model_validate(job)


@app.delete("/jobs/{job_id}", response_model=PlannerJobResponse, status_code=202)
@app.delete("/api/jobs/{job_id}", response_model=PlannerJobResponse, status_code=202)
async def cancel_planner_job(job_id: str) -> PlannerJobResponse:
    job = await asyncio.to_thread(get_job_manager().cancel, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Planner job not found")
    return PlannerJobResponse.model_validate(job)


@app.post("/roadmap/suggest", response_model=RoadmapResponse)
@app.post("/api/roadmap/suggest", response_model=RoadmapResponse)
async def roadmap_suggestion(request: RoadmapRequest) -> RoadmapResponse:
    suggestion = await asyncio.to_thread(
        suggest_roadmap,
        request.profile.dars_courses,
        request.courses,
        [(term.term, term.max_units) for term in request.terms],
    )
    return RoadmapResponse(
        terms=[
            RoadmapTermResponse(
                term=term.term,
                courses=term.courses,
                total_units=term.total_units,
            )
            for term in suggestion.terms
        ],
        unplaced_courses=suggestion.unplaced_courses,
        warnings=suggestion.warnings,
    )


def _run_horizon_job(
    payload: dict[str, Any],
    progress: Callable[[int, str], None],
    cancel_event: threading.Event,
) -> dict[str, Any]:
    request = HorizonPlanRequest.model_validate(payload)
    return _run_horizon(
        request,
        progress_callback=progress,
        cancel_event=cancel_event,
    ).model_dump(mode="json")


def _run_horizon(
    request: HorizonPlanRequest,
    *,
    progress_callback: Callable[[int, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> HorizonPlanResponse:
    horizon_run_id = str(uuid4())
    completed = list(dict.fromkeys(request.profile.dars_courses))
    units_completed = request.profile.units_completed
    term_results: list[HorizonTermResult] = []
    planned_term_count = 0

    for index, term in enumerate(request.terms, start=1):
        if cancel_event and cancel_event.is_set():
            break
        if progress_callback:
            progress_callback(
                5 + int((index - 1) / len(request.terms) * 90),
                f"Planning {term.term} ({index} of {len(request.terms)}).",
            )
        term_profile = request.profile.model_copy(
            update={
                "term": term.term,
                "dars_courses": completed.copy(),
                "required_courses": list(dict.fromkeys(term.required_courses)),
                "preferred_courses": list(dict.fromkeys(term.preferred_courses)),
                "min_units": term.min_units,
                "max_units": term.max_units,
                "units_completed": units_completed,
            }
        )
        result = run_planner(
            term_profile,
            thread_id=horizon_run_id,
            run_id=f"{horizon_run_id}-term-{index}",
        )
        top_candidate = result.candidates[0] if result.candidates else None
        planned_courses = [
            str(course.get("course_code", ""))
            for course in (top_candidate or {}).get("courses", [])
            if course.get("course_code")
        ]
        if planned_courses:
            planned_term_count += 1
            completed = list(dict.fromkeys(completed + planned_courses))
            units_completed += float(
                (top_candidate or {}).get("total_units", 0.0) or 0.0
            )
        term_results.append(
            HorizonTermResult(
                term=term.term,
                planned_courses=planned_courses,
                completed_courses_after_term=completed.copy(),
                result=result,
            )
        )
        if progress_callback:
            progress_callback(
                5 + int(index / len(request.terms) * 90),
                f"Finished {term.term} ({index} of {len(request.terms)}).",
            )

    if planned_term_count == len(request.terms):
        status: Literal["completed", "partial", "failed"] = "completed"
    elif planned_term_count:
        status = "partial"
    else:
        status = "failed"

    return HorizonPlanResponse(
        run_id=horizon_run_id,
        status=status,
        terms=term_results,
        completed_courses=completed,
    )


def _document_text(dars_text: str | None, dars_pdf_base64: str | None) -> str | None:
    if dars_pdf_base64:
        try:
            return extract_text_from_pdf_base64(dars_pdf_base64)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Could not read DARS PDF: {exc}"
            ) from exc
    return dars_text
