"""Optional model assistance for already-reviewed planning preferences."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from course_planner.constraints import (
    ConstraintParseError,
    parse_constraints,
    serialize_constraints,
)
from course_planner.model_provider import create_chat_model
from course_planner.planner_models import (
    EnhancementContext,
    EnhancementPatch,
    EnhancementProposal,
    EnhancementResponse,
    ModelConfig,
)
from course_planner.prerequisites import normalize_course_code

ENHANCEMENT_PROMPT = """You translate one student's natural-language planning request into
a partial preference patch. Never create or return a student profile. Never
change identity, major, GPA, units completed, enrollment status, DARS facts,
prerequisites, ratings, or any authoritative course facts.

Return only strict JSON matching exactly:
{"patch":{"terms":null,"format_preference":null,"hard_constraints":null,"ranking_weights":null},"explanations":[],"warnings":[]}
Use null for fields that should remain unchanged. Terms must use only the
provided term/course allow-lists. Hard constraints must use supported phrases
such as "Friday off", "No classes before 10:00", or "No classes after 17:30".
Ranking weights must be finite numbers from 0 through 1. The service merges
your patch with the current context and requires human review before applying.
"""


class PreferenceValidationError(ValueError):
    """The model proposed a value outside the deterministic context."""


class ModelEnhancementOutput(BaseModel):
    """Strict model response before deterministic context merging."""

    model_config = ConfigDict(extra="forbid")

    patch: EnhancementPatch
    explanations: list[str] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=20)


def _message_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            item if isinstance(item, str) else str(item.get("text", ""))
            for item in content
            if isinstance(item, (str, dict))
        ).strip()
    raise PreferenceValidationError("Model returned no JSON content")


def _parse_json(response: Any) -> dict[str, Any]:
    raw = _message_text(response)
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PreferenceValidationError("Model response was not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise PreferenceValidationError("Model response must be a JSON object")
    return decoded


def _normal_course(value: str) -> str:
    try:
        return normalize_course_code(value)
    except Exception as exc:
        raise PreferenceValidationError(
            f"Invalid course suggestion: {value!r}"
        ) from exc


def _merge(
    context: EnhancementContext,
    patch: EnhancementPatch,
) -> EnhancementProposal:
    payload = context.model_dump(mode="python")
    # ``allowed_courses`` is validation context, never part of the returned
    # proposal contract.
    payload.pop("allowed_courses", None)
    if patch.terms is not None:
        payload["terms"] = [item.model_dump(mode="python") for item in patch.terms]
    if patch.format_preference is not None:
        payload["format_preference"] = patch.format_preference
    if patch.hard_constraints is not None:
        payload["hard_constraints"] = patch.hard_constraints
    if patch.ranking_weights is not None:
        weights = payload["ranking_weights"]
        weights.update(patch.ranking_weights.model_dump(exclude_none=True))
        payload["ranking_weights"] = weights

    allowed_courses = {_normal_course(item) for item in context.allowed_courses}
    context_terms = {item.term for item in context.terms}
    for term in payload["terms"]:
        if term["term"] not in context_terms:
            raise PreferenceValidationError(
                f"term is outside the current context: {term['term']}"
            )
        for key in ("required_courses", "preferred_courses"):
            normalized = [_normal_course(item) for item in term[key]]
            unknown = sorted(set(normalized) - allowed_courses)
            if unknown:
                raise PreferenceValidationError(
                    f"{key} contains courses outside the allow-list: {', '.join(unknown)}"
                )
            term[key] = list(dict.fromkeys(normalized))
    try:
        parsed_constraints = parse_constraints(payload["hard_constraints"])
    except ConstraintParseError as exc:
        raise PreferenceValidationError(str(exc)) from exc
    payload["hard_constraints"] = serialize_constraints(parsed_constraints)
    try:
        return EnhancementProposal.model_validate(payload)
    except Exception as exc:
        raise PreferenceValidationError(
            "Merged enhancement proposal is invalid"
        ) from exc


def enhance_planning(
    description: str,
    context: EnhancementContext,
    model_config: ModelConfig,
) -> EnhancementResponse:
    """Generate and merge a complete, typed proposal without mutating context."""
    model = create_chat_model(config=model_config)
    payload = {"description": description, "context": context.model_dump(mode="json")}
    response = model.invoke(
        [
            SystemMessage(content=ENHANCEMENT_PROMPT),
            HumanMessage(content=json.dumps(payload, ensure_ascii=True)),
        ]
    )
    try:
        output = ModelEnhancementOutput.model_validate(_parse_json(response))
        proposal = _merge(context, output.patch)
    except PreferenceValidationError:
        raise
    except Exception as exc:
        raise PreferenceValidationError(
            "Model JSON did not match the enhancement schema"
        ) from exc
    return EnhancementResponse(
        proposal=proposal,
        explanations=output.explanations,
        warnings=output.warnings,
        requires_review=True,
    )
