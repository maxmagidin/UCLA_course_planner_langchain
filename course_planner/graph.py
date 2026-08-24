"""The durable UCLA planner workflow.

The graph deliberately combines deterministic nodes with one optional LLM
intake boundary. Retrieval, constraint solving, ranking, and reporting are
ordinary Python.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from course_planner.planner_models import PlannerResult, StudentProfile
from course_planner.ranking import rank_schedules
from course_planner.reporting import build_report
from course_planner.scheduling import generate_schedules
from course_planner.scrapers.bruinwalk_scraper import (
    scrape_course_ratings,
    scrape_professor_ratings,
)
from course_planner.scrapers.grade_dist_scraper import load_grade_data
from course_planner.scrapers.soc_scraper import (
    scrape_historical_enrollment,
    scrape_quarter_courses,
)
from course_planner.state import PlannerState, event, failure
from course_planner.utils import (
    CourseOption,
    EnrollmentPrediction,
    ProfessorRatings,
    Section,
    deserialize,
)
from course_planner.utils import (
    StudentProfile as LegacyProfile,
)

logger = logging.getLogger(__name__)


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _course_limit() -> int:
    try:
        return max(1, min(40, int(os.getenv("PLANNER_MAX_COURSES_PER_DEPARTMENT", "12"))))
    except ValueError:
        return 12


def _legacy_profile(data: dict[str, Any]) -> LegacyProfile:
    """Convert the graph boundary model into the existing solver model."""
    payload = dict(data)
    payload["year"] = payload.get("year", "junior")
    payload["enrollment_pass"] = payload.get("enrollment_pass", "open")
    return deserialize(json.dumps(payload), LegacyProfile)


def _course_objects(items: list[dict[str, Any]]) -> list[CourseOption]:
    return [deserialize(json.dumps(item), CourseOption) for item in items]


def _as_dicts(items: list[Any]) -> list[dict[str, Any]]:
    return [asdict(item) for item in items]


def _departments(profile: StudentProfile) -> set[str]:
    major = profile.major.upper()
    known = {
        "COMPUTER SCIENCE": "COM SCI",
        "COM SCI": "COM SCI",
        "MATHEMATICS": "MATH",
        "MATH": "MATH",
        "PHYSICS": "PHYSICS",
        "ECONOMICS": "ECON",
        "ECON": "ECON",
    }
    departments = {value for key, value in known.items() if key in major}
    if not departments:
        departments.add(profile.major.upper().strip())
    for course_code in profile.required_courses + profile.preferred_courses:
        parts = course_code.upper().rsplit(" ", 1)
        if len(parts) == 2:
            departments.add(parts[0])
    return {item for item in departments if item}


def _normalize_code(value: str) -> str:
    return " ".join(value.upper().split())


def _instructor_surname(value: str) -> str:
    return re.sub(r"[^A-Z]", "", value.upper().split(",", 1)[0])


def _prerequisites(description: str) -> list[str]:
    """Conservative prerequisite extraction; ambiguity is not treated as met."""
    return [_normalize_code(match) for match in re.findall(r"\b[A-Z]{2,6}\s+\d{1,3}[A-Z]?\b", description.upper())]


def _build_course_options(raw_courses: list[dict[str, Any]], profile: StudentProfile) -> list[CourseOption]:
    completed = {_normalize_code(item) for item in profile.dars_courses}
    required = {_normalize_code(item) for item in profile.required_courses}
    preferred = {_normalize_code(item) for item in profile.preferred_courses}
    preferred_format = profile.format_preference.lower()
    results: list[CourseOption] = []

    for raw in raw_courses:
        code = _normalize_code(str(raw.get("course_code", "")))
        if not code or code in completed:
            continue
        sections = raw.get("sections", [])
        if preferred_format != "any":
            sections = [item for item in sections if item.get("format", "in-person").lower() == preferred_format]
        if not sections:
            continue
        prereqs = _prerequisites(str(raw.get("description", "")))
        results.append(CourseOption(
            course_code=code,
            title=str(raw.get("title", "")),
            units=float(raw.get("units", 4.0)),
            description=str(raw.get("description", "")),
            sections=[
                Section(
                    section_id=str(item.get("section_id", "")),
                    days=str(item.get("days", "")),
                    start_time=str(item.get("start_time", "")),
                    end_time=str(item.get("end_time", "")),
                    location=str(item.get("location", "")),
                    instructor=str(item.get("instructor", "")),
                    parent_section_id=str(item.get("parent_section_id", "")),
                    enrolled=int(item.get("enrolled", 0) or 0),
                    capacity=int(item.get("capacity", 0) or 0),
                    waitlist=int(item.get("waitlist", 0) or 0),
                    waitlist_capacity=int(item.get("waitlist_capacity", 0) or 0),
                    format=str(item.get("format", "in-person")),
                    section_type=str(item.get("section_type", "lecture")),
                ) for item in sections
            ],
            prerequisites_met=all(item in completed for item in prereqs),
            is_required=code in required,
            is_preferred=code in preferred,
        ))
    return results


def retrieve_classes_node(state: PlannerState) -> dict[str, Any]:
    node = "retrieve_classes"
    try:
        profile = StudentProfile.model_validate(state["profile"])
        if not profile.term:
            return failure(node, "term is required; do not default to a stale quarter", False)
        raw: list[dict[str, Any]] = []
        requested = profile.required_courses + profile.preferred_courses
        for department in _departments(profile):
            raw.extend(
                scrape_quarter_courses(
                    profile.term,
                    department,
                    course_codes=requested,
                    max_courses=_course_limit(),
                )
            )
        raw = list({
            _normalize_code(str(item.get("course_code", ""))): item
            for item in raw
            if item.get("course_code")
        }.values())
        courses = _build_course_options(raw, profile)
        evidence_status = "ok" if courses else "failed"
        result: dict[str, Any] = {
            "courses": _as_dicts(courses),
            "evidence": {"schedule_of_classes": {"source": "UCLA SOC", "fetched_at": datetime.now(timezone.utc).isoformat(), "status": evidence_status, "detail": f"{len(courses)} options with usable sections"}},
            **event(f"retrieve_classes: found {len(courses)} course options"),
        }
        if not courses:
            return {
                **result,
                **failure(node, f"UCLA returned no usable {profile.term} courses for the requested departments", False),
            }

        found = {_normalize_code(course.course_code) for course in courses}
        missing_required = sorted({
            _normalize_code(code) for code in profile.required_courses
        } - found)
        if missing_required:
            return {
                **result,
                **failure(
                    node,
                    "Required courses not offered with usable sections: " + ", ".join(missing_required),
                    False,
                ),
            }
        return result
    except Exception as exc:
        logger.exception("Class retrieval failed")
        return {
            "courses": [],
            "evidence": {"schedule_of_classes": {"source": "UCLA SOC", "fetched_at": datetime.now(timezone.utc).isoformat(), "status": "failed", "detail": str(exc)}},
            **failure(node, str(exc), False),
        }


def enrollment_node(state: PlannerState) -> dict[str, Any]:
    node = "enrollment"
    try:
        profile = StudentProfile.model_validate(state["profile"])
        courses = _course_objects(state.get("courses", []))
        historical_enabled = _env_flag("PLANNER_ENABLE_HISTORICAL_ENROLLMENT")
        for course in courses:
            history = scrape_historical_enrollment(course.course_code) if historical_enabled else []
            n = len(history)
            day1 = sum((row.get("enrollment_day_1", 0) / max(row.get("capacity", 1), 1)) for row in history) / n if n else 0.0
            day7 = sum((row.get("enrollment_day_7", 0) / max(row.get("capacity", 1), 1)) for row in history) / n if n else 0.0
            current = course.sections[0] if course.sections else None
            fill = (current.enrolled / current.capacity) if current and current.capacity else 0.0
            base = (
                max(0.0, min(1.0, 1.0 - day1))
                if n
                else max(0.02, min(1.0, 1.0 - fill)) if current and current.capacity else 0.5
            )
            pass1 = base
            pass2 = max(0.0, min(1.0, base * 0.7))
            open_enrollment = max(0.0, min(1.0, base * 0.45))
            actual = {"pass_1": pass1, "pass_2": pass2, "open": open_enrollment}[profile.enrollment_pass.value]
            course.enrollment_prediction = EnrollmentPrediction(
                historical_quarters_sampled=n,
                avg_fill_rate_by_day_1=day1,
                avg_fill_rate_by_day_7=day7,
                has_historically_gone_to_waitlist=sum(bool(row.get("went_to_waitlist")) for row in history) > n / 2 if n else False,
                current_fill_rate=fill,
                current_waitlist_count=current.waitlist if current else 0,
                class_size=current.capacity if current else 0,
                chance_open_at_pass=actual,
                chance_open_pass_1=pass1,
                chance_open_pass_2=pass2,
                chance_open_enrollment=open_enrollment,
                notes=f"Based on {n} historical observations and current fill of {fill:.0%}.",
            )
        detail = (
            "historical fill-rate heuristic plus current enrollment"
            if historical_enabled
            else "current enrollment snapshot; historical lookups disabled for quick local runs"
        )
        return {"enrollment_courses": _as_dicts(courses), "evidence": {"enrollment": {"source": "UCLA SOC enrollment", "fetched_at": datetime.now(timezone.utc).isoformat(), "status": "ok", "detail": detail}}, **event("enrollment: enrichment complete")}
    except Exception as exc:
        logger.exception("Enrollment enrichment failed")
        return {"enrollment_courses": state.get("courses", []), **failure(node, str(exc))}


def ratings_node(state: PlannerState) -> dict[str, Any]:
    node = "ratings"
    try:
        courses = _course_objects(state.get("courses", []))
        if not _env_flag("PLANNER_ENABLE_BRUINWALK"):
            return {
                "ratings_courses": _as_dicts(courses),
                "evidence": {"bruinwalk": {"source": "Bruinwalk", "fetched_at": datetime.now(timezone.utc).isoformat(), "status": "partial", "detail": "disabled for quick local runs; set PLANNER_ENABLE_BRUINWALK=true to enable"}},
                **event("ratings: skipped in quick local mode"),
            }
        for course in courses:
            course.course_ratings = scrape_course_ratings(course.course_code)
            ratings: dict[str, ProfessorRatings] = {}
            for section in course.sections:
                instructor = section.instructor.strip()
                if instructor and instructor not in ratings:
                    result = scrape_professor_ratings(instructor, course.course_code)
                    if result:
                        ratings[instructor] = result
            course.professor_ratings = ratings or None
            values = [item.overall_rating for item in ratings.values() if item.overall_rating is not None]
            professor_score = sum(values) / len(values) if values else None
            course_score = (
                course.course_ratings.overall_course_rating
                if course.course_ratings and course.course_ratings.overall_course_rating is not None
                else None
            )
            if professor_score is not None and course_score is not None:
                course.bruinwalk_composite_score = round(professor_score * 0.6 + course_score * 0.4, 4)
            elif professor_score is not None:
                course.bruinwalk_composite_score = round(professor_score, 4)
            elif course_score is not None:
                course.bruinwalk_composite_score = round(course_score, 4)
            else:
                course.bruinwalk_composite_score = None
        return {"ratings_courses": _as_dicts(courses), "evidence": {"bruinwalk": {"source": "Bruinwalk", "fetched_at": datetime.now(timezone.utc).isoformat(), "status": "ok", "detail": "course and instructor ratings"}}, **event("ratings: enrichment complete")}
    except Exception as exc:
        logger.exception("Ratings enrichment failed")
        return {"ratings_courses": state.get("courses", []), **failure(node, str(exc))}


def grades_node(state: PlannerState) -> dict[str, Any]:
    node = "grades"
    try:
        courses = _course_objects(state.get("courses", []))
        if not _env_flag("PLANNER_ENABLE_GRADES", default=True):
            return {
                "grade_courses": _as_dicts(courses),
                "evidence": {"grades": {"source": "UCLA grade distributions", "fetched_at": datetime.now(timezone.utc).isoformat(), "status": "partial", "detail": "disabled by PLANNER_ENABLE_GRADES"}},
                **event("grades: disabled"),
            }
        data = load_grade_data()
        matched = 0
        for course in courses:
            records = data.get(_normalize_code(course.course_code), {})
            if records:
                instructor = course.sections[0].instructor.strip() if course.sections else ""
                surname = _instructor_surname(instructor)
                course.grade_distribution = next(
                    (
                        distribution
                        for record_instructor, distribution in records.items()
                        if surname and _instructor_surname(record_instructor) == surname
                    ),
                    None,
                )
                matched += int(course.grade_distribution is not None)
        return {"grade_courses": _as_dicts(courses), "evidence": {"grades": {"source": "UCLA grade distributions", "fetched_at": datetime.now(timezone.utc).isoformat(), "status": "ok", "detail": f"cached public sheets; matched {matched} of {len(courses)} current instructors"}}, **event("grades: enrichment complete")}
    except Exception as exc:
        logger.exception("Grade enrichment failed")
        return {"grade_courses": state.get("courses", []), **failure(node, str(exc))}


def merge_evidence_node(state: PlannerState) -> dict[str, Any]:
    try:
        merged = _course_objects(state.get("enrollment_courses", state.get("courses", [])))
        ratings = {item.course_code.upper(): item for item in _course_objects(state.get("ratings_courses", []))}
        grades = {item.course_code.upper(): item for item in _course_objects(state.get("grade_courses", []))}
        for course in merged:
            if course.course_code.upper() in ratings:
                rating = ratings[course.course_code.upper()]
                course.course_ratings = rating.course_ratings
                course.professor_ratings = rating.professor_ratings
                course.bruinwalk_composite_score = rating.bruinwalk_composite_score
            if course.course_code.upper() in grades:
                course.grade_distribution = grades[course.course_code.upper()].grade_distribution
        return {"courses": _as_dicts(merged), **event("merge_evidence: joined parallel branches")}
    except Exception as exc:  # noqa: BLE001 - graph nodes must return typed failures
        return failure("merge_evidence", str(exc))


def schedule_node(state: PlannerState) -> dict[str, Any]:
    try:
        if any(not error.get("recoverable", True) for error in state.get("errors", [])):
            return {"candidates": [], **event("schedule: skipped because retrieval had a blocking error")}
        profile = _legacy_profile(state["profile"])
        candidates = generate_schedules(_course_objects(state.get("courses", [])), profile)
        candidates = rank_schedules(candidates, profile)
        return {"candidates": _as_dicts(candidates), **event(f"schedule: generated {len(candidates)} candidates")}
    except Exception as exc:
        logger.exception("Schedule generation failed")
        return failure("schedule", str(exc), False)


def report_node(state: PlannerState) -> dict[str, Any]:
    try:
        profile = _legacy_profile(state["profile"])
        candidates = [deserialize(json.dumps(item), __import__("course_planner.utils", fromlist=["ScheduleCandidate"]).ScheduleCandidate) for item in state.get("candidates", [])]
        report = build_report(candidates, profile, state.get("evidence", {}), state.get("errors", []))
        return {"report_markdown": report, **event("report: completed")}
    except Exception as exc:  # noqa: BLE001 - graph nodes must return typed failures
        return failure("report", str(exc), False)


def build_graph(*, checkpointer=None):
    """Compile the planner graph with durable thread-level checkpoints."""
    graph = StateGraph(PlannerState)
    graph.add_node("retrieve_classes", retrieve_classes_node)
    graph.add_node("enrollment", enrollment_node)
    graph.add_node("ratings", ratings_node)
    graph.add_node("grades", grades_node)
    graph.add_node("merge_evidence", merge_evidence_node)
    graph.add_node("schedule", schedule_node)
    graph.add_node("report", report_node)
    graph.add_edge(START, "retrieve_classes")
    graph.add_edge("retrieve_classes", "enrollment")
    graph.add_edge("retrieve_classes", "ratings")
    graph.add_edge("retrieve_classes", "grades")
    graph.add_edge("enrollment", "merge_evidence")
    graph.add_edge("ratings", "merge_evidence")
    graph.add_edge("grades", "merge_evidence")
    graph.add_edge("merge_evidence", "schedule")
    graph.add_edge("schedule", "report")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def run_planner(
    profile: StudentProfile | dict[str, Any],
    *,
    thread_id: str | None = None,
    run_id: str | None = None,
    checkpointer=None,
) -> PlannerResult:
    """Run one planner thread and return a validated result."""
    parsed = profile if isinstance(profile, StudentProfile) else StudentProfile.model_validate(profile)
    run_id = run_id or str(uuid4())
    thread_id = thread_id or run_id
    state = build_graph(checkpointer=checkpointer).invoke(
        {"run_id": run_id, "thread_id": thread_id, "profile": parsed.model_dump(mode="json"), "errors": [], "events": []},
        config={"configurable": {"thread_id": thread_id, "checkpoint_ns": run_id}},
    )
    errors = [item for item in state.get("errors", []) if isinstance(item, dict)]
    return PlannerResult(
        run_id=run_id,
        status="failed" if any(not item.get("recoverable", True) for item in errors) else ("partial" if errors else "completed"),
        report_markdown=state.get("report_markdown", ""),
        candidates=state.get("candidates", []),
        evidence=state.get("evidence", {}),
        errors=errors,
    )
