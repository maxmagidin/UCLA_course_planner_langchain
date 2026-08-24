from __future__ import annotations

from fastapi.testclient import TestClient

import course_planner.api as api_module
import course_planner.graph as graph_module
from course_planner.api import app
from course_planner.planner_models import StudentProfile

client = TestClient(app)


def test_health_and_frontend_are_ready():
    health = client.get("/health")
    frontend = client.get("/app/")
    javascript = client.get("/app/app.js")

    assert health.json() == {"status": "ok"}
    assert frontend.status_code == 200
    assert "Start with your DARS" in frontend.text
    assert "Optional: autofill with your own model" in frontend.text
    assert "Run planner" in frontend.text
    assert javascript.status_code == 200
    assert 'request("/dars/parse"' in javascript.text


def test_dars_parse_returns_reviewable_courses_and_profile_hints():
    response = client.post("/dars/parse", json={
        "dars_text": """
Student Name: Alex Student
Major: Computer Science
Class Level: Junior
Cumulative GPA: 3.60
Units Completed: 96
COM SCI 31
MATH 31A
""",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "text"
    assert body["course_codes"] == ["COM SCI 31", "MATH 31A"]
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
        return StudentProfile(name="Alex Student", major="Computer Science", term="Fall 2026")

    monkeypatch.setattr(api_module, "extract_profile", fake_extract)
    response = client.post("/intake", json={
        "conversation": [{"role": "user", "content": "I am a junior CS major."}],
        "model": {
            "provider": "openai",
            "api_key": "request-only-key",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        },
    })

    assert response.status_code == 200
    assert captured["key"] == "request-only-key"
    assert captured["conversation"][0]["content"] == "I am a junior CS major."
    assert "request-only-key" not in response.text


def test_invalid_pdf_is_a_client_error_before_planning():
    response = client.post("/plan", json={
        "profile": {
            "name": "Test Student",
            "major": "Computer Science",
            "term": "Fall 2026",
        },
        "dars_pdf_base64": "not-base64!",
    })

    assert response.status_code == 400
    assert "not valid base64" in response.json()["detail"]


def test_plan_endpoint_runs_graph_in_worker_thread(monkeypatch):
    raw = [{
        "course_code": f"COM SCI {number}",
        "title": f"Course {number}",
        "units": 4,
        "description": "",
        "sections": [{
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
        }],
    } for number, day in zip((101, 102, 103), ("M", "T", "W"))]
    monkeypatch.setattr(
        graph_module,
        "scrape_quarter_courses",
        lambda term, department, **kwargs: raw,
    )
    monkeypatch.setenv("PLANNER_ENABLE_GRADES", "false")

    response = client.post("/plan", json={
        "profile": {
            "name": "Test Student",
            "major": "Computer Science",
            "term": "Fall 2026",
            "required_courses": ["COM SCI 101", "COM SCI 102", "COM SCI 103"],
            "min_units": 12,
            "max_units": 12,
        }
    })

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["candidates"]
