import base64
import dataclasses
import io
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

import dacite
import pdfplumber

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Model classes (originally from models.py, consolidated here)
# ---------------------------------------------------------------------------


class YearLevel(str, Enum):
    FRESHMAN = "freshman"
    SOPHOMORE = "sophomore"
    JUNIOR = "junior"
    SENIOR = "senior"
    GRADUATE = "graduate"


class EnrollmentPass(str, Enum):
    PASS_1 = "pass_1"
    PASS_2 = "pass_2"
    OPEN = "open"


@dataclass
class StudentProfile:
    name: str
    major: str
    year: YearLevel
    gpa: float
    units_completed: float
    enrollment_pass: EnrollmentPass
    pass_open_datetime: str
    term: str = ""
    dars_courses: list[str] = field(default_factory=list)
    dars_in_progress_courses: list[str] = field(default_factory=list)
    dars_remaining_courses: list[str] = field(default_factory=list)
    required_courses: list[str] = field(default_factory=list)
    preferred_courses: list[str] = field(default_factory=list)
    hard_constraints: list[str] = field(default_factory=list)
    format_preference: str = "in-person"
    min_units: int = 12
    max_units: int = 16
    weight_enrollment_chance: float = 0.25
    weight_professor_rating: float = 0.20
    weight_avg_gpa: float = 0.20
    weight_schedule_quality: float = 0.20
    weight_workload: float = 0.15


@dataclass
class Section:
    section_id: str
    days: str
    start_time: str
    end_time: str
    location: str
    instructor: str
    parent_section_id: str = ""
    enrolled: int = 0
    capacity: int = 0
    waitlist: int = 0
    waitlist_capacity: int = 0
    format: str = "in-person"
    section_type: str = "lecture"  # "lecture", "discussion", "lab"
    availability_score: float | None = None
    availability_confidence: str = "low"
    availability_risk: str = "unknown"
    professor_rating: float | None = None
    professor_rating_raw: float | None = None
    professor_rating_adjusted: float | None = None
    professor_rating_count: int = 0
    professor_rating_confidence: str = "low"
    professor_rating_match_status: str = "unverified"
    professor_rating_source: str = ""
    professor_rating_source_url: str = ""
    avg_gpa: float | None = None
    workload_hours_per_week: float | None = None


@dataclass
class EnrollmentPrediction:
    historical_quarters_sampled: int = 0
    avg_fill_rate_by_day_1: float = 0.0
    avg_fill_rate_by_day_7: float = 0.0
    has_historically_gone_to_waitlist: bool = False
    avg_quarters_until_waitlist_clears: float | None = None
    current_fill_rate: float = 0.0
    current_waitlist_count: int = 0
    class_size: int = 0
    is_impacted_major_course: bool = False
    chance_open_at_pass: float = 1.0
    chance_open_pass_1: float = 1.0
    chance_open_pass_2: float = 0.7
    chance_open_enrollment: float = 0.45
    notes: str = ""


@dataclass
class ProfessorRatings:
    instructor_name: str
    course_code: str = ""
    matched_instructor_name: str = ""
    overall_rating: float | None = None
    adjusted_rating: float | None = None
    difficulty_rating: float | None = None
    would_take_again_pct: float | None = None
    total_reviews: int = 0
    rating_confidence: str = "low"
    match_status: str = "unverified"
    source: str = ""
    source_url: str = ""
    fetched_at: str = ""
    status: str = "unknown"
    review_summary: str = ""
    most_common_positive: str = ""
    most_common_negative: str = ""


@dataclass
class CourseRatings:
    course_code: str
    overall_course_rating: float | None = None
    adjusted_rating: float | None = None
    total_reviews: int = 0
    rating_confidence: str = "low"
    source: str = ""
    source_url: str = ""
    fetched_at: str = ""
    status: str = "unknown"
    avg_hours_per_week: float | None = None
    avg_grade_expected: str = ""


@dataclass
class GradeDistribution:
    course_code: str
    instructor_name: str
    count_a_plus: int = 0
    count_a: int = 0
    count_a_minus: int = 0
    count_b_plus: int = 0
    count_b: int = 0
    count_b_minus: int = 0
    count_c_plus: int = 0
    count_c: int = 0
    count_c_minus: int = 0
    count_d_plus: int = 0
    count_d: int = 0
    count_d_minus: int = 0
    count_f: int = 0
    total_students: int = 0
    avg_gpa: float = 0.0
    median_gpa: float = 0.0
    std_dev_gpa: float = 0.0
    pct_a_range: float = 0.0
    pct_b_range: float = 0.0
    pct_c_range: float = 0.0
    pct_d_or_f: float = 0.0
    gpa_trend: float = 0.0
    most_recent_quarter_avg_gpa: float = 0.0
    quarters_sampled: int = 0


@dataclass
class CourseOption:
    course_code: str
    title: str
    units: float
    description: str = ""
    sections: list[Section] = field(default_factory=list)
    prerequisites_met: bool = True
    prerequisite_status: str = "unknown"
    prerequisite_summary: str = "Prerequisites have not been checked."
    prerequisite_groups: list[dict] = field(default_factory=list)
    missing_prerequisite_groups: list[list[str]] = field(default_factory=list)
    corequisite_groups: list[list[str]] = field(default_factory=list)
    catalog_url: str = ""
    is_required: bool = False
    is_preferred: bool = False
    enrollment_prediction: EnrollmentPrediction | None = None
    professor_ratings: dict[str, ProfessorRatings] | None = None
    course_ratings: CourseRatings | None = None
    rating_score: float | None = None
    grade_distribution: GradeDistribution | None = None


@dataclass
class DaySchedule:
    day: str
    sections: list[dict] = field(default_factory=list)
    # Each dict: {"course_code", "section_id", "start_min", "end_min",
    #             "instructor", "location"}
    total_minutes: int = 0
    gap_minutes: int = 0
    max_consecutive_minutes: int = 0


@dataclass
class ScheduleCandidate:
    courses: list[dict] = field(default_factory=list)
    # Each dict: {"course_code", "title", "units", "lecture_section_id",
    #             "discussion_section_id"}
    day_schedules: list[DaySchedule] = field(default_factory=list)
    total_units: float = 0.0
    days_on_campus: int = 0
    avg_gap_minutes_per_day: float = 0.0
    max_consecutive_minutes_any_day: int = 0
    avg_enrollment_chance: float = 0.0
    min_enrollment_chance: float = 1.0
    enrollment_risk_level: str = "unknown"
    enrollment_confidence: str = "low"
    avg_rating_score: float | None = None
    avg_gpa: float | None = None
    min_gpa: float | None = None
    avg_workload_hours_per_week: float | None = None
    schedule_quality_score: float = 0.0
    composite_score: float = 0.0
    preference_match_score: float = 0.0
    rank: int = 0
    reason: str = ""
    has_time_conflicts: bool = False
    violates_days_off: bool = False
    violates_time_bounds: bool = False
    violates_max_gap: bool = False
    violates_max_consecutive: bool = False
    violates_format_preference: bool = False
    has_unverified_meeting_times: bool = False


@dataclass
class CourseRiskFlag:
    course_code: str
    flag_type: str  # "enrollment", "grade", "workload", "rating"
    severity: str  # "critical", "warning"
    metric_name: str = ""
    metric_value: float = 0.0
    threshold_used: float = 0.0
    explanation: str = ""


@dataclass
class PlannerReport:
    student_name: str
    generated_at: str
    enrollment_pass: str
    pass_open_datetime: str
    recommended_schedule: ScheduleCandidate | None = None
    all_ranked_schedules: list[ScheduleCandidate] = field(default_factory=list)
    risk_flags: list[CourseRiskFlag] = field(default_factory=list)
    full_markdown_report: str = ""
    overall_success_probability: float = 0.0


# ---------------------------------------------------------------------------
# Serialization / Deserialization
# ---------------------------------------------------------------------------


class _EnumEncoder(json.JSONEncoder):
    """JSON encoder that serializes Enum members as their `.value`."""

    def default(self, o):
        if isinstance(o, Enum):
            return o.value
        return super().default(o)


def serialize(obj) -> str:
    """Convert any dataclass (including nested dataclasses,
    Enums, and Optional fields) to a JSON string."""
    if isinstance(obj, list):
        return json.dumps([dataclasses.asdict(item) for item in obj], cls=_EnumEncoder)
    return json.dumps(dataclasses.asdict(obj), cls=_EnumEncoder)


def deserialize(json_str: str, cls: type[T]) -> T:
    """Reconstruct a dataclass from a JSON string.

    Uses ``dacite`` with ``cast=[Enum]`` so Enum fields are automatically
    cast from their raw values.
    """
    data = json.loads(json_str)
    return dacite.from_dict(
        data_class=cls, data=data, config=dacite.Config(cast=[Enum])
    )


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------


def extract_pdf_text(base64_str: str) -> str:
    """Decode a base64-encoded PDF and extract all text via *pdfplumber*."""
    pdf_bytes = base64.b64decode(base64_str)
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def bayesian_adjusted_rating(
    raw_rating: float | None,
    review_count: int,
    *,
    prior_mean: float = 3.5,
    prior_count: int = 10,
) -> float | None:
    """Conservatively adjust a rating using a 3.5/5 prior from 10 reviews.

    A zero-review result is missing evidence, not a 3.5 rating. This gives
    5.0 from one review an adjusted 3.6364, below 4.8 from 200 reviews
    (4.7381), and keeps tiny samples from dominating ranking.
    """
    if raw_rating is None or review_count <= 0:
        return None
    if prior_count < 0:
        raise ValueError("prior_count must be non-negative")
    if not 0 <= prior_mean <= 5:
        raise ValueError("prior_mean must be between 0 and 5")
    adjusted = (raw_rating * review_count + prior_mean * prior_count) / (
        review_count + prior_count
    )
    return round(max(0.0, min(5.0, adjusted)), 4)


def rating_confidence(review_count: int) -> str:
    """Classify rating evidence: low (1–4), medium (5–24), high (25+)."""
    if review_count >= 25:
        return "high"
    if review_count >= 5:
        return "medium"
    return "low"
