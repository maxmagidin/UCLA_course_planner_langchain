from __future__ import annotations

from pathlib import Path

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

import course_planner.graph as graph_module
from course_planner.documents import classify_dars_courses, extract_course_codes
from course_planner.graph import run_planner
from course_planner.model_provider import create_chat_model
from course_planner.planner_models import ModelConfig, StudentProfile
from course_planner.ranking import rank_schedules
from course_planner.scheduling import generate_schedules, group_sections
from course_planner.utils import CourseOption, ScheduleCandidate, Section


@pytest.fixture(autouse=True)
def catalog_without_requisites(monkeypatch):
    # Unit tests opt into enrichments explicitly so they never make live
    # network calls merely because production defaults enable every source.
    monkeypatch.setenv("PLANNER_ENABLE_GRADES", "false")
    monkeypatch.setenv("PLANNER_ENABLE_HISTORICAL_ENROLLMENT", "false")
    monkeypatch.setenv("PLANNER_ENABLE_BRUINWALK", "false")
    monkeypatch.setattr(
        graph_module,
        "fetch_catalog_course",
        lambda code, year: {
            "course_code": code,
            "title": code,
            "description": "Lecture, four hours. Letter grading.",
            "catalog_year": year,
            "catalog_url": f"https://catalog.registrar.ucla.edu/course/{year}/TEST",
        },
    )


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


def test_model_provider_uses_generic_openai_compatible_settings(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("MODEL_NAME", "provider-model")

    with pytest.raises(RuntimeError, match="explicit transient"):
        create_chat_model()


def test_model_provider_accepts_transient_openai_byok_config():
    model = create_chat_model(
        config=ModelConfig(
            provider="openai",
            api_key="request-only-key",
            base_url="https://provider.example/v1",
            model="request-model",
        )
    )
    assert model.model_name == "request-model"


def test_model_provider_accepts_native_anthropic_byok_config():
    config = ModelConfig(provider="anthropic", api_key="request-only-key")
    model = create_chat_model(config=config)

    assert isinstance(model, ChatAnthropic)
    assert model.model == "claude-haiku-4-5-20251001"
    assert config.base_url == "https://api.anthropic.com"


def test_model_provider_accepts_keyless_local_openai_compatible_config():
    config = ModelConfig(
        provider="openai_compatible",
        base_url="http://127.0.0.1:11434/v1",
        model="local-test-model",
    )
    model = create_chat_model(config=config)

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "local-test-model"
    assert str(model.openai_api_base) == "http://127.0.0.1:11434/v1"


def test_model_provider_bounds_timeout_and_retries(monkeypatch):
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT_SECONDS", "999")
    monkeypatch.setenv("MODEL_MAX_RETRIES", "999")
    model = create_chat_model(
        config=ModelConfig(
            api_key="request-only-key",
            base_url="https://provider.example/v1",
            model="request-model",
        )
    )

    assert model.request_timeout == 45
    assert model.max_retries == 2

    anthropic = create_chat_model(
        config=ModelConfig(provider="anthropic", api_key="request-only-key")
    )
    assert anthropic.default_request_timeout == 45
    assert anthropic.max_retries == 2


def test_byok_rejects_private_or_insecure_base_urls():
    for base_url in ("http://provider.example/v1", "https://127.0.0.1/v1"):
        with pytest.raises(ValueError):
            ModelConfig(api_key="test", base_url=base_url, model="test")


def test_local_model_rejects_lan_addresses_and_public_deployment(monkeypatch):
    with pytest.raises(ValueError, match="loopback endpoint"):
        ModelConfig(
            provider="openai_compatible",
            base_url="http://192.168.1.20:11434/v1",
            model="test",
        )

    monkeypatch.setenv("PLANNER_PUBLIC_DEPLOYMENT", "true")
    monkeypatch.setenv("MODEL_HOST_ALLOWLIST", "127.0.0.1")
    with pytest.raises(ValueError, match="HTTPS"):
        ModelConfig(
            provider="openai_compatible",
            base_url="http://127.0.0.1:11434/v1",
            model="test",
        )


def test_dars_course_code_extraction():
    assert extract_course_codes(
        "COURSES COMPLETED: COM SCI 31, MATH 31A and ENGL 3"
    ) == ["COM SCI 31", "ENGL 3", "MATH 31A"]


def test_dars_classification_does_not_count_remaining_courses_as_completed():
    classified = classify_dars_courses("""
COURSES COMPLETED
COM SCI 31 A
COM SCI 32 B+
IN PROGRESS
COM SCI 35L IP
STILL NEEDED
COM SCI 111
Unlabelled: MATH 61
""")

    assert classified["completed"] == ["COM SCI 31", "COM SCI 32"]
    assert classified["in_progress"] == ["COM SCI 35L"]
    assert classified["remaining"] == ["COM SCI 111", "MATH 61"]


@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    [
        (
            "dars_engineering.txt",
            {
                "completed": ["COM SCI 31", "COM SCI 32", "MATH 31A"],
                "in_progress": ["COM SCI 35L"],
                "remaining": ["COM SCI 111", "COM SCI 118"],
                "unclassified": [],
            },
        ),
        (
            "dars_letters_science.txt",
            {
                "completed": ["MATH 31A", "MATH 31B", "MATH 32A"],
                "in_progress": ["MATH 32B"],
                "remaining": ["MATH 170A", "MATH 170E", "PHYSICS 1A"],
                "unclassified": [],
            },
        ),
    ],
)
def test_synthetic_dars_layout_fixtures(fixture_name, expected):
    text = (Path(__file__).parent / "fixtures" / fixture_name).read_text()
    assert classify_dars_courses(text) == expected


def test_graph_joins_parallel_enrichment(monkeypatch):
    monkeypatch.setenv("PLANNER_ENABLE_GRADES", "true")
    monkeypatch.setenv("PLANNER_ENABLE_HISTORICAL_ENROLLMENT", "true")
    monkeypatch.setenv("PLANNER_ENABLE_BRUINWALK", "true")
    raw = []
    for index, (start, end) in enumerate(
        (("9:00am", "9:50am"), ("10:00am", "10:50am"), ("11:00am", "11:50am")), 1
    ):
        raw.append(
            {
                "course_code": f"COM SCI {100 + index}",
                "title": f"Course {index}",
                "units": 4,
                "description": "",
                "sections": [
                    {
                        "section_id": f"{index}A",
                        "days": "MWF",
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                        "instructor": f"Professor {index}",
                        "capacity": 100,
                        "enrolled": 20,
                        "format": "in-person",
                        "section_type": "lecture",
                    }
                ],
            }
        )
    monkeypatch.setattr(
        graph_module,
        "scrape_quarter_courses",
        lambda term, department, **kwargs: raw,
    )
    monkeypatch.setattr(
        graph_module, "scrape_historical_enrollment", lambda course_code: []
    )
    monkeypatch.setattr(graph_module, "scrape_course_ratings", lambda course_code: None)
    monkeypatch.setattr(
        graph_module, "scrape_professor_ratings", lambda instructor, course_code: None
    )
    monkeypatch.setattr(graph_module, "load_grade_data", dict)

    result = run_planner(_profile(), thread_id="test-join")

    assert result.status == "completed"
    assert result.errors == []
    assert result.candidates
    assert "schedule_of_classes" in result.evidence
    assert "enrollment" in result.evidence
    assert "bruinwalk" in result.evidence
    assert "grades" in result.evidence


def test_rating_enrichment_skips_generic_instructor_labels(monkeypatch):
    requested = []
    monkeypatch.setattr(graph_module, "scrape_course_ratings", lambda code: None)
    monkeypatch.setattr(
        graph_module,
        "scrape_professor_ratings",
        lambda instructor, code: requested.append((instructor, code)),
    )
    course = CourseOption(
        course_code="COM SCI 111",
        title="Operating Systems Principles",
        units=4,
        sections=[
            Section("Lec 1", "MW", "10am", "11:50am", "", "Professor Name"),
            Section("Lab 1A", "F", "10am", "11:50am", "", "TA"),
            Section("Lab 1B", "F", "12pm", "1:50pm", "", "The Staff"),
        ],
    )

    enriched, count = graph_module._enrich_course_ratings(course)

    assert enriched.course_code == "COM SCI 111"
    assert count == 0
    assert requested == [("Professor Name", "COM SCI 111")]


def test_raw_dars_text_is_removed_before_checkpointing(monkeypatch):
    captured = {}

    class FakeGraph:
        def invoke(self, state, config):
            captured["state"] = state
            captured["config"] = config
            return state

    monkeypatch.setattr(
        graph_module, "build_graph", lambda *, checkpointer: FakeGraph()
    )
    profile = _profile().model_copy(update={"dars_courses": ["COM SCI 31"]})

    run_planner(profile, checkpointer=object())

    assert "dars_text" not in captured["state"]["profile"]
    assert captured["state"]["profile"]["dars_courses"] == ["COM SCI 31"]


def test_graph_checkpoints_stay_in_memory_by_default(monkeypatch):
    captured = {}

    class FakeGraph:
        def invoke(self, state, config):
            return state

    def fake_build_graph(*, checkpointer):
        captured["checkpointer"] = checkpointer
        return FakeGraph()

    monkeypatch.delenv("PLANNER_PERSIST_GRAPH_CHECKPOINTS", raising=False)
    monkeypatch.setattr(graph_module, "build_graph", fake_build_graph)

    run_planner(_profile())

    assert isinstance(captured["checkpointer"], InMemorySaver)


def test_missing_required_courses_fail_instead_of_silently_planning(monkeypatch):
    raw = [
        {
            "course_code": "COM SCI 101",
            "title": "Available course",
            "units": 4,
            "description": "",
            "sections": [
                {
                    "section_id": "Lec 1",
                    "days": "MWF",
                    "start_time": "9am",
                    "end_time": "9:50am",
                    "location": "",
                    "instructor": "Professor",
                    "capacity": 100,
                    "enrolled": 20,
                    "format": "in-person",
                    "section_type": "lecture",
                }
            ],
        }
    ]
    monkeypatch.setattr(
        graph_module,
        "scrape_quarter_courses",
        lambda term, department, **kwargs: raw,
    )
    monkeypatch.setenv("PLANNER_ENABLE_GRADES", "false")

    result = run_planner(_profile(), thread_id="test-missing-required")

    assert result.status == "failed"
    assert result.candidates == []
    assert "COM SCI 102" in result.errors[0].message


def test_impossible_constraints_fail_instead_of_reporting_completed(monkeypatch):
    raw = [
        {
            "course_code": code,
            "title": code,
            "units": 4,
            "description": "",
            "sections": [
                {
                    "section_id": "Lec 1",
                    "days": "MWF",
                    "start_time": "9am",
                    "end_time": "9:50am",
                    "location": "",
                    "instructor": "Professor",
                    "capacity": 100,
                    "enrolled": 20,
                    "format": "in-person",
                    "section_type": "lecture",
                }
            ],
        }
        for code in ("COM SCI 101", "COM SCI 102", "COM SCI 103")
    ]
    monkeypatch.setattr(
        graph_module,
        "scrape_quarter_courses",
        lambda term, department, **kwargs: raw,
    )
    monkeypatch.setenv("PLANNER_ENABLE_GRADES", "false")
    profile = _profile().model_copy(
        update={"hard_constraints": ["No classes before 10am"]}
    )

    result = run_planner(profile, thread_id="test-no-valid-schedule")

    assert result.status == "failed"
    assert result.candidates == []
    assert result.errors[0].node == "schedule"
    assert "No valid schedule" in result.errors[0].message


def test_unsupported_hard_constraint_fails_loudly():
    profile = graph_module._legacy_profile(
        _profile()
        .model_copy(
            update={"hard_constraints": ["Only classes near the sculpture garden"]}
        )
        .model_dump(mode="json")
    )

    with pytest.raises(ValueError, match="Unsupported hard constraint"):
        generate_schedules([], profile)


def test_required_discussion_is_not_silently_dropped_when_no_pair_is_valid():
    lecture = Section(
        section_id="Lec 1",
        days="M",
        start_time="9am",
        end_time="10am",
        location="",
        instructor="",
        section_type="lecture",
    )
    conflicting_discussion = Section(
        section_id="Dis 1A",
        parent_section_id="Lec 1",
        days="M",
        start_time="9:30am",
        end_time="10:30am",
        location="",
        instructor="",
        section_type="discussion",
    )
    course = CourseOption(
        course_code="COM SCI 101",
        title="Test",
        units=4,
        sections=[lecture, conflicting_discussion],
    )

    assert group_sections(course) == []


def test_ranking_renormalizes_around_missing_optional_evidence():
    profile = graph_module._legacy_profile(_profile().model_dump(mode="json"))
    candidate = ScheduleCandidate(
        avg_enrollment_chance=0.5,
        schedule_quality_score=0.5,
        avg_rating_score=None,
        avg_gpa=None,
        avg_workload_hours_per_week=None,
    )

    ranked = rank_schedules([candidate], profile)

    assert ranked[0].composite_score == 0.5


def test_ranking_prefers_requested_schedule_over_unrelated_elective():
    profile = graph_module._legacy_profile(_profile().model_dump(mode="json"))
    requested = [{"course_code": code} for code in profile.required_courses]
    required_only = ScheduleCandidate(
        courses=requested,
        total_units=12,
        avg_enrollment_chance=0.4,
        schedule_quality_score=0.4,
    )
    with_unrelated_elective = ScheduleCandidate(
        courses=requested + [{"course_code": "COM SCI 1"}],
        total_units=13,
        avg_enrollment_chance=0.9,
        schedule_quality_score=0.9,
    )

    ranked = rank_schedules([with_unrelated_elective, required_only], profile)

    assert ranked[0] is required_only
