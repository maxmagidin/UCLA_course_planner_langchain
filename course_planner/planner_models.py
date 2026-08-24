"""Typed boundary models for the LangChain/LangGraph planner.

The legacy repository used dataclasses and JSON blobs inside ChatMessage
objects.  These Pydantic models are the public contract of the new runtime.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


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


class StudentProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    major: str = Field(min_length=1)
    year: YearLevel = YearLevel.JUNIOR
    gpa: float = Field(default=0.0, ge=0.0, le=4.0)
    units_completed: float = Field(default=0.0, ge=0.0)
    enrollment_pass: EnrollmentPass = EnrollmentPass.OPEN
    pass_open_datetime: str = ""
    term: str = Field(min_length=1)
    dars_text: str | None = None
    dars_courses: list[str] = Field(default_factory=list)
    required_courses: list[str] = Field(default_factory=list)
    preferred_courses: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    format_preference: Literal["in-person", "hybrid", "online", "any"] = "any"
    min_units: int = Field(default=12, ge=0)
    max_units: int = Field(default=16, ge=0)
    weight_enrollment_chance: float = Field(default=0.25, ge=0.0)
    weight_professor_rating: float = Field(default=0.20, ge=0.0)
    weight_avg_gpa: float = Field(default=0.20, ge=0.0)
    weight_schedule_quality: float = Field(default=0.20, ge=0.0)
    weight_workload: float = Field(default=0.15, ge=0.0)

    @field_validator("max_units")
    @classmethod
    def max_units_not_below_min(cls, value: int, info):
        minimum = info.data.get("min_units", 0)
        if value < minimum:
            raise ValueError("max_units must be greater than or equal to min_units")
        return value


class ModelConfig(BaseModel):
    """Transient BYOK configuration; never put this model in PlannerState."""

    model_config = ConfigDict(extra="ignore")

    provider: str = "openai_compatible"
    api_key: SecretStr = SecretStr("")
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @classmethod
    def from_environment(cls) -> ModelConfig:
        import os

        provider = os.getenv("MODEL_PROVIDER", "openai_compatible").lower().strip()
        asi = provider in {"asi_one", "asi"}
        return cls(
            provider=provider,
            api_key=os.getenv("MODEL_API_KEY")
            or (os.getenv("ASI_ONE_API_KEY") if asi else None)
            or (os.getenv("ASI1_API_KEY") if asi else None)
            or os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv(
                "MODEL_BASE_URL",
                os.getenv("ASI_ONE_BASE_URL", "https://api.asi1.ai/v1")
                if asi
                else "https://api.openai.com/v1",
            ),
            model=os.getenv(
                "MODEL_NAME",
                os.getenv("ASI_ONE_MODEL", "asi1") if asi else "gpt-4o-mini",
            ),
            temperature=float(os.getenv("MODEL_TEMPERATURE", "0")),
        )


class EvidenceRecord(BaseModel):
    source: str
    fetched_at: str
    status: Literal["ok", "partial", "failed"] = "ok"
    detail: str = ""


class RunError(BaseModel):
    node: str
    message: str
    recoverable: bool = True


class PlannerResult(BaseModel):
    run_id: str
    status: Literal["completed", "partial", "failed"]
    report_markdown: str = ""
    candidates: list[dict] = Field(default_factory=list)
    evidence: dict[str, EvidenceRecord] = Field(default_factory=dict)
    errors: list[RunError] = Field(default_factory=list)
