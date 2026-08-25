"""Graph state and serialization helpers."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Reducer used when parallel graph branches add distinct evidence keys."""
    return {**left, **right}


class PlannerState(TypedDict, total=False):
    run_id: str
    thread_id: str
    profile: dict[str, Any]
    courses: list[dict[str, Any]]
    prerequisite_courses: list[dict[str, Any]]
    enrollment_courses: list[dict[str, Any]]
    ratings_courses: list[dict[str, Any]]
    grade_courses: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    report_markdown: str
    evidence: Annotated[dict[str, dict[str, Any]], merge_dicts]
    errors: Annotated[list[dict[str, Any]], operator.add]
    events: Annotated[list[str], operator.add]


def event(message: str) -> dict[str, list[str]]:
    return {"events": [message]}


def failure(node: str, message: str, recoverable: bool = True) -> dict[str, Any]:
    return {
        "errors": [{"node": node, "message": message, "recoverable": recoverable}],
        "events": [f"{node}: {message}"],
    }
