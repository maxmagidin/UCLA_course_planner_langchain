"""Typed boundary models for the LangChain/LangGraph planner.

The legacy repository used dataclasses and JSON blobs inside ChatMessage
objects.  These Pydantic models are the public contract of the new runtime.
"""

from __future__ import annotations

import ipaddress
import os
from enum import Enum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from course_planner.terms import parse_ucla_term


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
    dars_in_progress_courses: list[str] = Field(default_factory=list)
    dars_remaining_courses: list[str] = Field(default_factory=list)
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

    @field_validator("term")
    @classmethod
    def valid_ucla_term(cls, value: str) -> str:
        return parse_ucla_term(value).label


class ModelConfig(BaseModel):
    """Transient BYOK configuration; never put this model in PlannerState."""

    model_config = ConfigDict(extra="ignore")

    provider: str = Field(default="openai_compatible", max_length=80)
    api_key: SecretStr = SecretStr("")
    base_url: str = Field(default="https://api.openai.com/v1", max_length=2_000)
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=300)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @field_validator("base_url")
    @classmethod
    def safe_model_base_url(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "model base_url must be an ordinary provider URL without credentials, query, or fragment"
            )
        allow_insecure = os.getenv("ALLOW_INSECURE_MODEL_BASE_URLS", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if parsed.scheme != "https" and not (
            allow_insecure and parsed.scheme == "http"
        ):
            raise ValueError("model base_url must use HTTPS")
        allow_private = os.getenv("ALLOW_PRIVATE_MODEL_BASE_URLS", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        hostname = parsed.hostname.lower().rstrip(".")
        if not allow_private and hostname in {"localhost", "localhost.localdomain"}:
            raise ValueError("private model base URLs are disabled")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if (
            address
            and not allow_private
            and (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_reserved
                or address.is_unspecified
            )
        ):
            raise ValueError("private model base URLs are disabled")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls) -> ModelConfig:
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
