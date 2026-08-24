from __future__ import annotations

import course_planner.graph as graph_module
from course_planner.graph import run_planner
from course_planner.planner_models import StudentProfile


def _profile() -> StudentProfile:
    return StudentProfile(
        name="Test Student",
        major="Computer Science",
        year="junior",
        gpa=3.6,
        units_completed=96,
        enrollment_pass="pass_1",
        pass_open_datetime="2026-08-28 09:00",
        term="Fall 2026",
        required_courses=["COM SCI 101", "COM SCI 102", "COM SCI 103"],
        min_units=12,
        max_units=16,
    )


def test_profile_rejects_invalid_unit_range():
    try:
        StudentProfile(name="A", major="B", min_units=16, max_units=12)
    except ValueError as exc:
        assert "max_units" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("invalid unit range was accepted")


def test_graph_joins_parallel_enrichment(monkeypatch):
    raw = []
    for index, (start, end) in enumerate((("9:00am", "9:50am"), ("10:00am", "10:50am"), ("11:00am", "11:50am")), 1):
        raw.append({
            "course_code": f"COM SCI {100 + index}",
            "title": f"Course {index}",
            "units": 4,
            "description": "",
            "sections": [{
                "section_id": f"{index}A", "days": "MWF", "start_time": start,
                "end_time": end, "location": "", "instructor": f"Professor {index}",
                "capacity": 100, "enrolled": 20, "format": "in-person",
                "section_type": "lecture",
            }],
        })
    monkeypatch.setattr(graph_module, "scrape_quarter_courses", lambda term, department: raw)
    monkeypatch.setattr(graph_module, "scrape_historical_enrollment", lambda course_code: [])
    monkeypatch.setattr(graph_module, "scrape_course_ratings", lambda course_code: None)
    monkeypatch.setattr(graph_module, "scrape_professor_ratings", lambda instructor, course_code: None)
    monkeypatch.setattr(graph_module, "load_grade_data", lambda: {})

    result = run_planner(_profile(), thread_id="test-join")

    assert result.status == "completed"
    assert result.errors == []
    assert result.candidates
    assert "schedule_of_classes" in result.evidence
    assert "enrollment" in result.evidence
    assert "bruinwalk" in result.evidence
    assert "grades" in result.evidence
