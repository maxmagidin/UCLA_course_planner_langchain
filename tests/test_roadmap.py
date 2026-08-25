from __future__ import annotations

import course_planner.roadmap as roadmap_module
from course_planner.roadmap import suggest_roadmap

DESCRIPTIONS = {
    "COM SCI 32": "Enforced requisite: course 31. Data structures.",
    "COM SCI 33": "Enforced requisite: course 32. Computer organization.",
    "COM SCI 35L": "Requisites: courses 31, 32. Software construction.",
    "COM SCI 111": "Enforced requisites: courses 32, 33, 35L. Operating systems.",
}


def test_roadmap_places_dependencies_in_earlier_terms(monkeypatch):
    monkeypatch.setattr(
        roadmap_module,
        "fetch_catalog_course",
        lambda code, year: {
            "course_code": code,
            "description": DESCRIPTIONS[code],
            "units": 4.0,
        },
    )

    result = suggest_roadmap(
        ["COM SCI 31"],
        ["COM SCI 111", "COM SCI 35L", "COM SCI 33", "COM SCI 32"],
        [("Fall 2026", 12), ("Winter 2027", 12), ("Spring 2027", 12)],
    )

    assert result.terms[0].courses == ["COM SCI 32"]
    assert result.terms[1].courses == ["COM SCI 35L", "COM SCI 33"]
    assert result.terms[2].courses == ["COM SCI 111"]
    assert result.unplaced_courses == []


def test_roadmap_reports_external_missing_prerequisites(monkeypatch):
    monkeypatch.setattr(
        roadmap_module,
        "fetch_catalog_course",
        lambda code, year: {
            "course_code": code,
            "description": DESCRIPTIONS[code],
            "units": 4.0,
        },
    )

    result = suggest_roadmap(
        [],
        ["COM SCI 111"],
        [("Fall 2026", 16)],
    )

    assert result.unplaced_courses == ["COM SCI 111"]
    assert "COM SCI 32" in result.warnings[0]
