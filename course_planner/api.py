"""Optional HTTP API with transient bring-your-own-key support.

This is intentionally separate from the Agent Chat Protocol adapter. A client
may send a provider key for a single intake request; the key is not written to
PlannerState, checkpoints, reports, or logs by this module.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from course_planner.graph import run_planner
from course_planner.intake import extract_profile
from course_planner.documents import extract_course_codes, extract_text_from_pdf_base64
from course_planner.planner_models import ModelConfig, PlannerResult, StudentProfile


class ChatRequest(BaseModel):
    conversation: list[dict[str, str]] = Field(min_length=1)
    model: ModelConfig
    dars_text: str | None = None
    dars_pdf_base64: str | None = None


class IntakeRequest(ChatRequest):
    pass


class PlanRequest(BaseModel):
    profile: StudentProfile


app = FastAPI(title="UCLA Course Planner", version="0.2.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/intake", response_model=StudentProfile)
async def intake(request: IntakeRequest) -> StudentProfile:
    conversation = _add_document_context(request)
    profile = await asyncio.to_thread(extract_profile, conversation, request.model)
    return _apply_dars(profile, request)


@app.post("/plan", response_model=PlannerResult)
async def plan(request: PlanRequest) -> PlannerResult:
    return await asyncio.to_thread(run_planner, request.profile)


@app.post("/chat", response_model=dict[str, Any])
async def chat(request: ChatRequest) -> dict[str, Any]:
    conversation = _add_document_context(request)
    profile = await asyncio.to_thread(extract_profile, conversation, request.model)
    profile = _apply_dars(profile, request)
    result = await asyncio.to_thread(run_planner, profile)
    return {"profile": profile.model_dump(mode="json"), "result": result.model_dump(mode="json")}


def _add_document_context(request: ChatRequest) -> list[dict[str, str]]:
    conversation = list(request.conversation)
    text = request.dars_text
    if request.dars_pdf_base64:
        text = extract_text_from_pdf_base64(request.dars_pdf_base64)
    if text:
        codes = extract_course_codes(text)
        conversation.append({
            "role": "user",
            "content": "DARS document course codes extracted deterministically: " + ", ".join(codes),
        })
    return conversation


def _apply_dars(profile: StudentProfile, request: ChatRequest) -> StudentProfile:
    text = request.dars_text
    if request.dars_pdf_base64:
        text = extract_text_from_pdf_base64(request.dars_pdf_base64)
    if not text:
        return profile
    codes = extract_course_codes(text)
    return profile.model_copy(update={"dars_text": text, "dars_courses": sorted(set(profile.dars_courses + codes))})
