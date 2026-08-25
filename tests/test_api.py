from __future__ import annotations

from fastapi.testclient import TestClient

import course_planner.api as api_module
import course_planner.graph as graph_module
from course_planner.api import app
from course_planner.planner_models import PlannerResult, StudentProfile
from course_planner.roadmap import RoadmapSuggestion, RoadmapTerm

client = TestClient(app)


def test_health_and_frontend_are_ready():
    health = client.get("/api/health")
    frontend = client.get("/app/")

    assert health.json() == {"status": "ok"}
    assert frontend.status_code in {200, 503}
    if frontend.status_code == 200:
        assert '<div id="root"></div>' in frontend.text
        assert "UCLA Course Planner" in frontend.text
    else:
        assert "Frontend build needed" in frontend.text


def test_dars_parse_returns_reviewable_courses_and_profile_hints():
    response = client.post(
        "/dars/parse",
        json={
            "dars_text": """
Student Name: Alex Student
Major: Computer Science
Class Level: Junior
Cumulative GPA: 3.60
Units Completed: 96
COURSES COMPLETED
COM SCI 31
MATH 31A
""",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "text"
    assert body["course_codes"] == ["COM SCI 31", "MATH 31A"]
    assert body["completed_courses"] == ["COM SCI 31", "MATH 31A"]
    assert body["in_progress_courses"] == []
    assert body["remaining_courses"] == []
    assert body["profile_hints"] == {
        "name": "Alex Student",
        "major": "Computer Science",
        "year": "junior",
        "gpa": 3.6,
        "units_completed": 96.0,
    }


def test_dars_parse_requires_a_readable_document():
    response = client.post("/dars/parse", json={})

    assert response.status_code == 400
    assert "DARS" in response.json()["detail"]


def test_byok_intake_key_is_transient_and_not_returned(monkeypatch):
    captured = {}

    def fake_extract(conversation, model):
        captured["key"] = model.api_key.get_secret_value()
        captured["conversation"] = conversation
        return StudentProfile(
            name="Alex Student", major="Computer Science", term="Fall 2026"
        )

    monkeypatch.setattr(api_module, "extract_profile", fake_extract)
    response = client.post(
        "/intake",
        json={
            "conversation": [{"role": "user", "content": "I am a junior CS major."}],
            "model": {
                "provider": "openai",
                "api_key": "request-only-key",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
            },
        },
    )

    assert response.status_code == 200
    assert captured["key"] == "request-only-key"
    assert captured["conversation"][0]["content"] == "I am a junior CS major."
    assert "request-only-key" not in response.text


def test_invalid_pdf_is_a_client_error_before_planning():
    response = client.post(
        "/plan",
        json={
            "profile": {
                "name": "Test Student",
                "major": "Computer Science",
                "term": "Fall 2026",
            },
            "dars_pdf_base64": "not-base64!",
        },
    )

    assert response.status_code == 400
    assert "not valid base64" in response.json()["detail"]


def test_plan_endpoint_runs_graph_in_worker_thread(monkeypatch):
    raw = [
        {
            "course_code": f"COM SCI {number}",
            "title": f"Course {number}",
            "units": 4,
            "description": "",
            "sections": [
                {
                    "section_id": "Lec 1",
                    "days": day,
                    "start_time": "10am",
                    "end_time": "10:50am",
                    "location": "Boelter Hall",
                    "instructor": "Professor",
                    "capacity": 100,
                    "enrolled": 20,
                    "format": "in-person",
                    "section_type": "lecture",
                }
            ],
        }
        for number, day in zip((101, 102, 103), ("M", "T", "W"))
    ]
    monkeypatch.setattr(
        graph_module,
        "scrape_quarter_courses",
        lambda term, department, **kwargs: raw,
    )
    monkeypatch.setattr(
        graph_module,
        "fetch_catalog_course",
        lambda code, year: {
            "course_code": code,
            "title": code,
            "description": "Lecture, four hours. Letter grading.",
            "catalog_year": year,
            "catalog_url": "https://catalog.registrar.ucla.edu/course/test",
        },
    )
    monkeypatch.setenv("PLANNER_ENABLE_GRADES", "false")

    response = client.post(
        "/plan",
        json={
            "profile": {
                "name": "Test Student",
                "major": "Computer Science",
                "term": "Fall 2026",
                "required_courses": ["COM SCI 101", "COM SCI 102", "COM SCI 103"],
                "min_units": 12,
                "max_units": 12,
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["candidates"]


def test_horizon_plan_carries_the_top_schedule_into_the_next_term(monkeypatch):
    received_profiles = []

    def fake_run_planner(profile, **kwargs):
        received_profiles.append(profile)
        courses = [
            {
                "course_code": code,
                "title": code,
                "units": 4,
                "lecture_section_id": "Lec 1",
                "discussion_section_id": "",
            }
            for code in profile.required_courses
        ]
        return PlannerResult(
            run_id=kwargs["run_id"],
            status="completed",
            candidates=[{"courses": courses, "total_units": len(courses) * 4}],
        )

    monkeypatch.setattr(api_module, "run_planner", fake_run_planner)
    response = client.post(
        "/api/plan/horizon",
        json={
            "profile": {
                "name": "Test Student",
                "major": "Computer Science",
                "term": "Fall 2026",
                "units_completed": 96,
                "dars_courses": ["MATH 31A"],
            },
            "terms": [
                {
                    "term": "Fall 2026",
                    "required_courses": ["COM SCI 101"],
                    "min_units": 4,
                    "max_units": 4,
                },
                {
                    "term": "Winter 2027",
                    "required_courses": ["COM SCI 102"],
                    "min_units": 4,
                    "max_units": 4,
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["terms"][0]["planned_courses"] == ["COM SCI 101"]
    assert body["terms"][1]["planned_courses"] == ["COM SCI 102"]
    assert body["completed_courses"] == ["MATH 31A", "COM SCI 101", "COM SCI 102"]
    assert received_profiles[1].dars_courses == ["MATH 31A", "COM SCI 101"]
    assert received_profiles[1].units_completed == 100


def test_horizon_plan_rejects_a_course_assigned_to_multiple_terms():
    response = client.post(
        "/api/plan/horizon",
        json={
            "profile": {
                "name": "Test Student",
                "major": "Computer Science",
                "term": "Fall 2026",
            },
            "terms": [
                {"term": "Fall 2026", "required_courses": ["COM SCI 101"]},
                {"term": "Winter 2027", "preferred_courses": ["COM SCI 101"]},
            ],
        },
    )

    assert response.status_code == 422
    assert "Assign each course to one term only" in response.text


def test_roadmap_endpoint_returns_reviewable_placements(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "suggest_roadmap",
        lambda completed, requested, terms: RoadmapSuggestion(
            terms=[
                RoadmapTerm(
                    term="Fall 2026",
                    max_units=12,
                    courses=["COM SCI 32"],
                    total_units=4,
                )
            ],
            unplaced_courses=["COM SCI 111"],
            warnings=["COM SCI 111 needs COM SCI 33."],
        ),
    )
    response = client.post(
        "/api/roadmap/suggest",
        json={
            "profile": {
                "name": "Test Student",
                "major": "Computer Science",
                "term": "Fall 2026",
                "dars_courses": ["COM SCI 31"],
            },
            "courses": ["COM SCI 32", "COM SCI 111"],
            "terms": [{"term": "Fall 2026", "max_units": 12}],
        },
    )

    assert response.status_code == 200
    assert response.json()["terms"][0]["courses"] == ["COM SCI 32"]
    assert response.json()["unplaced_courses"] == ["COM SCI 111"]
