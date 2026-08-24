"""Composable deterministic tools around the existing UCLA data sources."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool

from course_planner.scrapers.bruinwalk_scraper import (
    scrape_course_ratings,
    scrape_professor_ratings,
)
from course_planner.scrapers.grade_dist_scraper import load_grade_data
from course_planner.scrapers.soc_scraper import (
    scrape_historical_enrollment,
    scrape_quarter_courses,
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@tool
def search_ucla_schedule(term: str, department: str) -> str:
    """Fetch the current UCLA Schedule of Classes for one term and department."""
    return json.dumps(scrape_quarter_courses(term, department))


@tool
def search_historical_enrollment(course_code: str) -> str:
    """Fetch historical enrollment observations for a UCLA course."""
    return json.dumps(scrape_historical_enrollment(course_code))


@tool
def search_bruinwalk(course_code: str, instructor: str = "") -> str:
    """Fetch course and, when supplied, professor ratings from Bruinwalk."""
    result: dict[str, Any] = {
        "course": scrape_course_ratings(course_code),
        "professor": scrape_professor_ratings(instructor, course_code) if instructor else None,
    }
    return json.dumps(result, default=lambda value: value.__dict__)


@tool
def search_grade_distribution(course_code: str) -> str:
    """Look up cached UCLA grade-distribution records for a course."""
    data = load_grade_data().get(" ".join(course_code.upper().split()), {})
    return json.dumps(data, default=lambda value: value.__dict__)


TOOL_REGISTRY = [
    search_ucla_schedule,
    search_historical_enrollment,
    search_bruinwalk,
    search_grade_distribution,
]
