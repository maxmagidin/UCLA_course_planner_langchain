"""Typed boundary models for the LangChain/LangGraph planner.

The legacy repository used dataclasses and JSON blobs inside ChatMessage
objects.  These Pydantic models are the public contract of the new runtime.
"""

from __future__ import annotations

import ipaddress
import math
import os
import socket
from enum import Enum
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from course_planner.terms import parse_ucla_term

CourseCode = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
]
HardConstraint = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]


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
    # A profile is reviewed, durable planning input.  In particular, raw DARS
    # documents do not belong here: they are accepted only by /api/dars/parse.
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    major: str = Field(min_length=1, max_length=200)
    year: YearLevel = YearLevel.JUNIOR
    gpa: float = Field(default=0.0, ge=0.0, le=4.0)
    units_completed: float = Field(default=0.0, ge=0.0)
    enrollment_pass: EnrollmentPass = EnrollmentPass.OPEN
    pass_open_datetime: str = Field(default="", max_length=100)
    term: str = Field(min_length=1, max_length=80)
    dars_courses: list[CourseCode] = Field(default_factory=list, max_length=300)
    dars_in_progress_courses: list[CourseCode] = Field(
        default_factory=list, max_length=100
    )
    dars_remaining_courses: list[CourseCode] = Field(
        default_factory=list, max_length=300
    )
    required_courses: list[CourseCode] = Field(default_factory=list, max_length=60)
    preferred_courses: list[CourseCode] = Field(default_factory=list, max_length=60)
    hard_constraints: list[HardConstraint] = Field(default_factory=list, max_length=20)
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

    @model_validator(mode="after")
    def at_least_one_ranking_weight(self) -> StudentProfile:
        total = (
            self.weight_enrollment_chance
            + self.weight_professor_rating
            + self.weight_avg_gpa
            + self.weight_schedule_quality
            + self.weight_workload
        )
        if total <= 0:
            raise ValueError("at least one ranking weight must be greater than zero")
        return self


class ModelConfig(BaseModel):
    """Transient BYOK configuration; never put this model in PlannerState."""

    # ``base_url`` has a security validator below. Pydantic otherwise skips
    # field validators when callers rely on a default value, which would let a
    # public deployment bypass the required host allowlist simply by omitting
    # ``base_url`` from the request.
    model_config = ConfigDict(extra="forbid", validate_default=True)

    provider: Literal["openai", "anthropic", "openai_compatible"] = "openai"
    api_key: SecretStr = Field(default=SecretStr(""), max_length=10_000)
    base_url: str = Field(default="", max_length=2_000)
    model: str = Field(default="", max_length=300)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @model_validator(mode="after")
    def provider_defaults_and_safe_base_url(self) -> ModelConfig:
        defaults = {
            "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
            "anthropic": (
                "https://api.anthropic.com",
                "claude-haiku-4-5-20251001",
            ),
            "openai_compatible": (
                "http://host.docker.internal:11434/v1",
                "llama3.2",
            ),
        }
        default_url, default_model = defaults[self.provider]
        self.base_url = self.base_url.strip().rstrip("/") or default_url
        self.model = self.model.strip() or default_model

        parsed = urlsplit(self.base_url)
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
        hostname = parsed.hostname.lower().rstrip(".")
        allowlist = {
            item.strip().lower().rstrip(".")
            for item in os.getenv("MODEL_HOST_ALLOWLIST", "").split(",")
            if item.strip()
        }
        public_deployment = os.getenv("PLANNER_PUBLIC_DEPLOYMENT", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        literal_address: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
        try:
            literal_address = ipaddress.ip_address(hostname)
        except ValueError:
            pass
        local_endpoint = hostname in {
            "localhost",
            "localhost.localdomain",
            "host.docker.internal",
        } or bool(literal_address and literal_address.is_loopback)
        local_model_allowed = (
            self.provider == "openai_compatible"
            and not public_deployment
            and local_endpoint
        )
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("model base_url must use HTTP or HTTPS")
        if parsed.scheme != "https" and not local_model_allowed:
            raise ValueError(
                "model base_url must use HTTPS unless a local custom model uses a loopback endpoint"
            )
        if public_deployment and hostname not in allowlist:
            raise ValueError("public deployments require MODEL_HOST_ALLOWLIST for BYOK")
        if allowlist and hostname not in allowlist:
            raise ValueError("model base URL host is not in MODEL_HOST_ALLOWLIST")
        if local_endpoint and not local_model_allowed:
            raise ValueError("private model base URLs are disabled")
        try:
            infos = socket.getaddrinfo(
                hostname, parsed.port or 443, type=socket.SOCK_STREAM
            )
        except socket.gaierror:
            infos = []
        for info in infos:
            address_text = info[4][0].split("%", 1)[0]
            try:
                address = ipaddress.ip_address(address_text)
            except ValueError:
                continue
            if not local_model_allowed and (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_reserved
                or address.is_unspecified
            ):
                raise ValueError(
                    "model base URLs resolving to private addresses are disabled"
                )
        return self


class RankingWeights(BaseModel):
    """The complete, finite ranking-weight contract shared by UI and model."""

    model_config = ConfigDict(extra="forbid")

    weight_enrollment_chance: float = Field(default=0.25, ge=0.0, le=1.0)
    weight_professor_rating: float = Field(default=0.20, ge=0.0, le=1.0)
    weight_avg_gpa: float = Field(default=0.20, ge=0.0, le=1.0)
    weight_schedule_quality: float = Field(default=0.20, ge=0.0, le=1.0)
    weight_workload: float = Field(default=0.15, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def finite_and_nonzero(self) -> RankingWeights:
        values = self.model_dump().values()
        if not all(math.isfinite(value) for value in values) or sum(values) <= 0:
            raise ValueError("ranking weights must be finite and have a nonzero total")
        return self


class EnhancementTerm(BaseModel):
    """One typed term in the natural-language enhancement contract."""

    model_config = ConfigDict(extra="forbid")

    term: str = Field(min_length=1, max_length=80)
    required_courses: list[CourseCode] = Field(default_factory=list, max_length=30)
    preferred_courses: list[CourseCode] = Field(default_factory=list, max_length=30)
    min_units: int = Field(default=12, ge=0, le=30)
    max_units: int = Field(default=16, ge=0, le=30)

    @model_validator(mode="after")
    def valid_units(self) -> EnhancementTerm:
        if self.max_units < self.min_units:
            raise ValueError("max_units must be greater than or equal to min_units")
        self.term = parse_ucla_term(self.term).label
        return self


class EnhancementContext(BaseModel):
    """Current reviewed planning context sent to the optional model."""

    model_config = ConfigDict(extra="forbid")

    terms: list[EnhancementTerm] = Field(min_length=1, max_length=4)
    allowed_courses: list[CourseCode] = Field(default_factory=list, max_length=300)
    format_preference: Literal["in-person", "hybrid", "online", "any"] = "any"
    hard_constraints: list[HardConstraint] = Field(default_factory=list, max_length=20)
    ranking_weights: RankingWeights = Field(default_factory=RankingWeights)


class RankingWeightsPatch(BaseModel):
    """Partial finite ranking weights emitted by the model."""

    model_config = ConfigDict(extra="forbid")

    weight_enrollment_chance: float | None = Field(default=None, ge=0.0, le=1.0)
    weight_professor_rating: float | None = Field(default=None, ge=0.0, le=1.0)
    weight_avg_gpa: float | None = Field(default=None, ge=0.0, le=1.0)
    weight_schedule_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    weight_workload: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def finite(self) -> RankingWeightsPatch:
        if not all(
            math.isfinite(value)
            for value in self.model_dump().values()
            if value is not None
        ):
            raise ValueError("ranking weights must be finite")
        return self


class EnhancementPatch(BaseModel):
    """Partial model output; merged with the reviewed context before return."""

    model_config = ConfigDict(extra="forbid")

    terms: list[EnhancementTerm] | None = Field(default=None, max_length=4)
    format_preference: Literal["in-person", "hybrid", "online", "any"] | None = None
    hard_constraints: list[HardConstraint] | None = Field(default=None, max_length=20)
    ranking_weights: RankingWeightsPatch | None = None


class EnhancementProposal(BaseModel):
    """Complete merged proposal returned to the browser for review."""

    model_config = ConfigDict(extra="forbid")

    terms: list[EnhancementTerm] = Field(min_length=1, max_length=4)
    format_preference: Literal["in-person", "hybrid", "online", "any"]
    hard_constraints: list[HardConstraint] = Field(default_factory=list, max_length=20)
    ranking_weights: RankingWeights


class EnhancementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal: EnhancementProposal
    explanations: list[str] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    requires_review: Literal[True] = True


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
