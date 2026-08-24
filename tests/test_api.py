from __future__ import annotations

from fastapi.testclient import TestClient

import course_planner.graph as graph_module
from course_planner.api import app

client = TestClient(app)


def test_health_and_frontend_are_ready():
    health = client.get("/health")
    frontend = client.get("/app/")

    assert health.json() == {"status": "ok"}
    assert frontend.status_code == 200
    assert "Run direct plan" in frontend.text


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
