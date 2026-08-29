from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

import course_planner.api as api_module
import course_planner.graph as graph_module
import course_planner.intake as intake_module
import course_planner.jobs as jobs_module
from course_planner.api import app
from course_planner.planner_models import (
    EnhancementProposal,
    EnhancementResponse,
    EnhancementTerm,
    PlannerResult,
    RankingWeights,
)
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
        "/api/dars/parse",
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
    assert body["course_buckets"]["completed"] == ["COM SCI 31", "MATH 31A"]
    assert body["profile_draft"]["dars_courses"] == ["COM SCI 31", "MATH 31A"]
    assert body["provenance"]["gpa"] == "dars"
    assert "term" in body["missing_fields"]


def test_dars_parse_requires_a_readable_document():
    response = client.post("/api/dars/parse", json={})

    assert response.status_code == 400
    assert "DARS" in response.json()["detail"]


def _enhancement_context():
    return {
        "terms": [
            {
                "term": "Fall 2026",
                "required_courses": [],
                "preferred_courses": [],
                "min_units": 12,
                "max_units": 16,
            }
        ],
        "allowed_courses": ["COM SCI 101"],
        "format_preference": "any",
        "hard_constraints": [],
        "ranking_weights": {
            "weight_enrollment_chance": 0.25,
            "weight_professor_rating": 0.2,
            "weight_avg_gpa": 0.2,
            "weight_schedule_quality": 0.2,
            "weight_workload": 0.15,
        },
    }


def test_byok_enhancement_key_is_transient_and_returns_complete_proposal(monkeypatch):
    captured = {}

    def fake_enhance(description, context, model):
        captured["key"] = model.api_key.get_secret_value()
        captured["provider"] = model.provider
        captured["description"] = description
        return EnhancementResponse(
            proposal=EnhancementProposal(
                terms=[
                    EnhancementTerm(term="Fall 2026", preferred_courses=["COM SCI 101"])
                ],
                format_preference="any",
                hard_constraints=[],
                ranking_weights=RankingWeights(),
            ),
            explanations=["Matches your stated interest."],
        )

    monkeypatch.setattr(api_module, "enhance_planning", fake_enhance)
    response = client.post(
        "/api/planning/enhance",
        json={
            "description": "Prefer COM SCI 101.",
            "context": _enhancement_context(),
            "model": {
                "provider": "anthropic",
                "api_key": "request-only-key",
            },
        },
    )

    assert response.status_code == 200
    assert captured["key"] == "request-only-key"
    assert captured["provider"] == "anthropic"
    assert captured["description"] == "Prefer COM SCI 101."
    assert "profile" not in response.json()
    assert response.json()["requires_review"] is True
    assert response.json()["proposal"]["terms"][0]["preferred_courses"] == [
        "COM SCI 101"
    ]
    assert "request-only-key" not in response.text


def test_custom_local_enhancement_accepts_an_empty_api_key(monkeypatch):
    captured = {}

    def fake_enhance(description, context, model):
        captured["provider"] = model.provider
        captured["key"] = model.api_key.get_secret_value()
        captured["base_url"] = model.base_url
        return EnhancementResponse(
            proposal=EnhancementProposal(
                terms=context.terms,
                format_preference=context.format_preference,
                hard_constraints=context.hard_constraints,
                ranking_weights=context.ranking_weights,
            )
        )

    monkeypatch.setattr(api_module, "enhance_planning", fake_enhance)
    response = client.post(
        "/api/planning/enhance",
        json={
            "description": "Prefer afternoons.",
            "context": _enhancement_context(),
            "model": {
                "provider": "openai_compatible",
                "base_url": "http://127.0.0.1:11434/v1",
                "model": "local-test-model",
            },
        },
    )

    assert response.status_code == 200
    assert captured == {
        "provider": "openai_compatible",
        "key": "",
        "base_url": "http://127.0.0.1:11434/v1",
    }


def test_enhancement_accepts_exact_browser_payload_and_merges_context(monkeypatch):
    class FakeModel:
        def invoke(self, messages):
            return AIMessage(
                content='{"patch":{"terms":[{"term":"Fall 2026","required_courses":["COM SCI 101"],"preferred_courses":[],"min_units":12,"max_units":16}],"format_preference":"in-person","hard_constraints":["Friday off","No classes before 10am"],"ranking_weights":{"weight_professor_rating":0.8}},"explanations":["You asked for later classes."],"warnings":[]}'
            )

    monkeypatch.setattr(
        intake_module, "create_chat_model", lambda *, config: FakeModel()
    )
    payload = {
        "description": "Keep Friday free and prioritize professor quality.",
        "context": _enhancement_context(),
        "model": {"api_key": "request-only-key"},
    }
    response = client.post("/api/planning/enhance", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["requires_review"] is True
    assert body["proposal"]["terms"][0]["required_courses"] == ["COM SCI 101"]
    assert body["proposal"]["hard_constraints"] == [
        "Friday off",
        "No classes before 10:00",
    ]
    assert body["proposal"]["ranking_weights"]["weight_enrollment_chance"] == 0.25
    assert body["proposal"]["ranking_weights"]["weight_professor_rating"] == 0.8


def test_enhancement_request_rejects_unknown_fields():
    payload = {
        "description": "Prefer afternoons.",
        "context": _enhancement_context(),
        "model": {"api_key": "request-only-key"},
        "profile": {"name": "Must not be accepted"},
    }
    assert client.post("/api/planning/enhance", json=payload).status_code == 422


def test_enhancement_unknown_course_is_rejected(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "enhance_planning",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            api_module.PreferenceValidationError("course outside the allow-list")
        ),
    )
    response = client.post(
        "/api/planning/enhance",
        json={
            "description": "Take COM SCI 999.",
            "context": _enhancement_context(),
            "model": {"api_key": "request-only-key"},
        },
    )
    assert response.status_code == 422
    assert "allow-list" in response.text


def test_raw_dars_is_not_accepted_by_planning():
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

    assert response.status_code == 422


def test_legacy_profile_intake_routes_are_removed():
    assert client.post("/api/intake", json={}).status_code == 404
    assert client.post("/api/chat", json={}).status_code == 404


def test_raw_dars_is_not_accepted_inside_profile():
    response = client.post(
        "/api/plan",
        json={
            "profile": {
                "name": "Test Student",
                "major": "Computer Science",
                "term": "Fall 2026",
                "dars_text": "private audit text",
            }
        },
    )
    assert response.status_code == 422


def test_model_config_never_reads_process_environment(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "environment-secret")
    from course_planner.model_provider import create_chat_model

    with pytest.raises(RuntimeError):
        create_chat_model()


def test_model_base_url_rejects_private_dns_resolution(monkeypatch):
    import course_planner.planner_models as models

    monkeypatch.setattr(
        models.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("10.0.0.4", 443))],
    )
    with pytest.raises(ValueError, match="private addresses"):
        models.ModelConfig(
            api_key="request-only-key", base_url="https://model.example/v1"
        )


def test_public_deployment_requires_model_host_allowlist(monkeypatch):
    import course_planner.planner_models as models

    monkeypatch.setenv("PLANNER_PUBLIC_DEPLOYMENT", "true")
    monkeypatch.delenv("MODEL_HOST_ALLOWLIST", raising=False)
    with pytest.raises(ValueError, match="MODEL_HOST_ALLOWLIST"):
        models.ModelConfig(api_key="request-only-key")


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
    monkeypatch.setenv("PLANNER_ENABLE_HISTORICAL_ENROLLMENT", "false")
    monkeypatch.setenv("PLANNER_ENABLE_BRUINWALK", "false")

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


def test_background_horizon_job_progress_and_result(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANNER_DATABASE_PATH", str(tmp_path / "api-jobs.sqlite3"))
    jobs_module.reset_job_manager_for_tests()

    def fake_job(payload, progress, cancel):
        progress(55, "Testing one term.")
        return {
            "run_id": "background-test",
            "status": "completed",
            "terms": [],
            "completed_courses": payload["profile"].get("dars_courses", []),
        }

    monkeypatch.setattr(api_module, "_run_horizon_job", fake_job)
    try:
        created = client.post(
            "/api/plan/horizon/jobs",
            json={
                "profile": {
                    "name": "Test Student",
                    "major": "Computer Science",
                    "term": "Fall 2026",
                    "dars_courses": ["COM SCI 31"],
                },
                "terms": [
                    {
                        "term": "Fall 2026",
                        "required_courses": ["COM SCI 32"],
                        "min_units": 4,
                        "max_units": 4,
                    }
                ],
            },
        )
        assert created.status_code == 202
        job_id = created.json()["id"]

        for _ in range(100):
            status = client.get(f"/api/jobs/{job_id}")
            assert status.status_code == 200
            if status.json()["status"] == "completed":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("background API job did not finish")

        assert status.json()["progress"] == 100
        assert status.json()["result"]["run_id"] == "background-test"
        assert client.get("/api/ready").json()["status"] == "ready"
    finally:
        jobs_module.reset_job_manager_for_tests()
