"""Optional HTTP API with transient bring-your-own-key support.

This is intentionally separate from the Agent Chat Protocol adapter. A client
may send a provider key for a single intake request; the key is not written to
PlannerState, checkpoints, reports, or logs by this module.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from course_planner.documents import (
    extract_course_codes,
    extract_dars_hints,
    extract_text_from_pdf_base64,
)
from course_planner.graph import run_planner
from course_planner.intake import extract_profile
from course_planner.planner_models import ModelConfig, PlannerResult, StudentProfile


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=50_000)


class ChatRequest(BaseModel):
    conversation: list[ConversationMessage] = Field(min_length=1, max_length=100)
    model: ModelConfig
    dars_text: str | None = Field(default=None, max_length=2_000_000)
    dars_pdf_base64: str | None = Field(default=None, max_length=30_000_000)


class IntakeRequest(ChatRequest):
    pass


class PlanRequest(BaseModel):
    profile: StudentProfile
    dars_text: str | None = Field(default=None, max_length=2_000_000)
    dars_pdf_base64: str | None = Field(default=None, max_length=30_000_000)


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


class DarsParseRequest(BaseModel):
    dars_text: str | None = Field(default=None, max_length=2_000_000)
    dars_pdf_base64: str | None = Field(default=None, max_length=30_000_000)


class DarsParseResponse(BaseModel):
    source: Literal["text", "pdf"]
    character_count: int
    course_codes: list[str]
    profile_hints: dict[str, str | float]


app = FastAPI(title="UCLA Course Planner", version="0.4.0")

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
        allow_methods=["GET", "POST", "OPTIONS"],
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


@app.post("/dars/parse", response_model=DarsParseResponse)
@app.post("/api/dars/parse", response_model=DarsParseResponse)
async def parse_dars(request: DarsParseRequest) -> DarsParseResponse:
    text = await asyncio.to_thread(
        _document_text, request.dars_text, request.dars_pdf_base64
    )
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Paste DARS text or upload a readable DARS PDF")
    return DarsParseResponse(
        source="pdf" if request.dars_pdf_base64 else "text",
        character_count=len(text),
        course_codes=extract_course_codes(text),
        profile_hints=extract_dars_hints(text),
    )


@app.post("/intake", response_model=StudentProfile)
@app.post("/api/intake", response_model=StudentProfile)
async def intake(request: IntakeRequest) -> StudentProfile:
    conversation = await asyncio.to_thread(_add_document_context, request)
    profile = await _extract_profile_with_provider(conversation, request.model)
    return await asyncio.to_thread(
        _apply_dars, profile, request.dars_text, request.dars_pdf_base64
    )


@app.post("/plan", response_model=PlannerResult)
@app.post("/api/plan", response_model=PlannerResult)
async def plan(request: PlanRequest) -> PlannerResult:
    profile = await asyncio.to_thread(
        _apply_dars, request.profile, request.dars_text, request.dars_pdf_base64
    )
    return await asyncio.to_thread(run_planner, profile)


@app.post("/plan/horizon", response_model=HorizonPlanResponse)
@app.post("/api/plan/horizon", response_model=HorizonPlanResponse)
async def plan_horizon(request: HorizonPlanRequest) -> HorizonPlanResponse:
    return await asyncio.to_thread(_run_horizon, request)


@app.post("/chat", response_model=dict[str, Any])
@app.post("/api/chat", response_model=dict[str, Any])
async def chat(request: ChatRequest) -> dict[str, Any]:
    conversation = await asyncio.to_thread(_add_document_context, request)
    profile = await _extract_profile_with_provider(conversation, request.model)
    profile = await asyncio.to_thread(
        _apply_dars, profile, request.dars_text, request.dars_pdf_base64
    )
    result = await asyncio.to_thread(run_planner, profile)
    return {"profile": profile.model_dump(mode="json"), "result": result.model_dump(mode="json")}


def _run_horizon(request: HorizonPlanRequest) -> HorizonPlanResponse:
    horizon_run_id = str(uuid4())
    completed = list(dict.fromkeys(request.profile.dars_courses))
    units_completed = request.profile.units_completed
    term_results: list[HorizonTermResult] = []
    planned_term_count = 0

    for index, term in enumerate(request.terms, start=1):
        term_profile = request.profile.model_copy(update={
            "term": term.term,
            "dars_courses": completed.copy(),
            "required_courses": list(dict.fromkeys(term.required_courses)),
            "preferred_courses": list(dict.fromkeys(term.preferred_courses)),
            "min_units": term.min_units,
            "max_units": term.max_units,
            "units_completed": units_completed,
        })
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
            units_completed += float((top_candidate or {}).get("total_units", 0.0) or 0.0)
        term_results.append(HorizonTermResult(
            term=term.term,
            planned_courses=planned_courses,
            completed_courses_after_term=completed.copy(),
            result=result,
        ))

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


async def _extract_profile_with_provider(
    conversation: list[dict[str, str]], model: ModelConfig
) -> StudentProfile:
    try:
        return await asyncio.to_thread(extract_profile, conversation, model)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Model-assisted intake failed. Check the API key, provider, "
                "model name, and the details you supplied."
            ),
        ) from exc


def _add_document_context(request: ChatRequest) -> list[dict[str, str]]:
    conversation = [item.model_dump() for item in request.conversation]
    text = _document_text(request.dars_text, request.dars_pdf_base64)
    if text:
        codes = extract_course_codes(text)
        conversation.append({
            "role": "user",
            "content": "DARS document course codes extracted deterministically: " + ", ".join(codes),
        })
    return conversation


def _document_text(dars_text: str | None, dars_pdf_base64: str | None) -> str | None:
    if dars_pdf_base64:
        try:
            return extract_text_from_pdf_base64(dars_pdf_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not read DARS PDF: {exc}") from exc
    return dars_text


def _apply_dars(
    profile: StudentProfile,
    dars_text: str | None,
    dars_pdf_base64: str | None,
) -> StudentProfile:
    text = _document_text(dars_text, dars_pdf_base64)
    if not text:
        return profile
    codes = extract_course_codes(text)
    return profile.model_copy(update={"dars_text": text, "dars_courses": sorted(set(profile.dars_courses + codes))})
