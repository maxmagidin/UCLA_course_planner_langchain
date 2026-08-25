"""Deterministic UCLA prerequisite parsing and evaluation.

The catalog writes requisites as prose. This module supports the common UCLA
forms while preserving uncertainty explicitly. It never asks a language model
to decide whether a student is eligible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SUBJECT_ALIASES = (
    (r"Civil and Environmental Engineering", "C&EE"),
    (r"Electrical and Computer Engineering", "EC ENGR"),
    (r"Electrical Engineering", "EC ENGR"),
    (r"Computer Science", "COM SCI"),
    (r"Program in Computing", "PIC"),
    (r"Mathematics", "MATH"),
    (r"Statistics", "STATS"),
    (r"Physics", "PHYSICS"),
    (r"Chemistry and Biochemistry", "CHEM"),
    (r"Chemistry", "CHEM"),
    (r"Engineering", "ENGR"),
)
_SUBJECT_CODES = (
    "COM SCI",
    "EC ENGR",
    "C&EE",
    "MATH",
    "STATS",
    "PHYSICS",
    "CHEM",
    "ENGR",
    "PIC",
)
_COURSE_TOKEN = re.compile(
    rf"(?:(?P<subject>{'|'.join(re.escape(code) for code in _SUBJECT_CODES)})\s+)?"
    r"(?P<number>CM?\d{1,3}[A-Z]{0,2}|M\d{1,3}[A-Z]{0,2}|\d{1,3}[A-Z]{0,2})\b",
    re.IGNORECASE,
)
_REQUISITE = re.compile(
    r"(?P<enforced>enforced\s+)?(?P<recommended>recommended\s+)?"
    r"(?P<kind>requisites?|corequisites?)\s*:\s*(?P<body>.*?)(?=\.\s|$)",
    re.IGNORECASE,
)


def normalize_course_code(value: str) -> str:
    return " ".join(value.upper().split())


@dataclass
class RequisiteGroup:
    options: list[str]
    kind: str = "prerequisite"
    enforced: bool = False
    recommended: bool = False

    def as_dict(self) -> dict:
        return {
            "options": self.options,
            "kind": self.kind,
            "enforced": self.enforced,
            "recommended": self.recommended,
        }


@dataclass
class RequisiteRule:
    course_code: str
    summary: str = ""
    groups: list[RequisiteGroup] = field(default_factory=list)
    parse_warning: str = ""


@dataclass
class RequisiteEvaluation:
    status: str
    summary: str
    missing_groups: list[list[str]] = field(default_factory=list)
    corequisite_groups: list[list[str]] = field(default_factory=list)


def _canonicalize_subjects(value: str) -> str:
    result = value
    for pattern, replacement in _SUBJECT_ALIASES:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def _course_references(value: str, default_subject: str) -> list[str]:
    text = _canonicalize_subjects(value)
    current_subject = default_subject
    references: list[str] = []
    for match in _COURSE_TOKEN.finditer(text):
        subject = match.group("subject")
        if subject:
            current_subject = normalize_course_code(subject)
        number = match.group("number").upper()
        code = normalize_course_code(f"{current_subject} {number}")
        if code not in references:
            references.append(code)
    return references


def parse_catalog_requisites(course_code: str, description: str) -> RequisiteRule:
    """Parse common UCLA catalog requisite prose into AND-of-OR groups."""
    normalized_course = normalize_course_code(course_code)
    default_subject = normalized_course.rsplit(" ", 1)[0]
    matches = list(_REQUISITE.finditer(description or ""))
    if not matches:
        return RequisiteRule(
            course_code=normalized_course, summary="No catalog requisites listed."
        )

    groups: list[RequisiteGroup] = []
    summaries: list[str] = []
    warnings: list[str] = []
    for match in matches:
        body = match.group("body").strip()
        enforced = bool(match.group("enforced"))
        recommended = bool(match.group("recommended"))
        kind = (
            "corequisite"
            if "corequisite" in match.group("kind").lower()
            else "prerequisite"
        )
        label = " ".join(
            filter(
                None,
                [
                    "Enforced" if enforced else "Recommended" if recommended else "",
                    kind,
                ],
            )
        ).capitalize()
        summaries.append(f"{label}: {body}")

        for part in (item.strip(" ,") for item in body.split(";")):
            if not part:
                continue
            references = _course_references(part, default_subject)
            if not references:
                warnings.append(f"Could not interpret: {part}")
                continue
            if not recommended and re.search(
                r"\b(?:grades?|minimum grade|consent|permission|placement|examination)\b",
                part,
                re.IGNORECASE,
            ):
                warnings.append(f"Needs manual verification: {part}")
                continue
            # A UCLA semicolon separates required groups. Inside one part,
            # `or` denotes alternatives; comma/and lists are separate ANDs.
            if re.search(r"\bor\b", part, re.IGNORECASE):
                groups.append(RequisiteGroup(references, kind, enforced, recommended))
            else:
                groups.extend(
                    RequisiteGroup([reference], kind, enforced, recommended)
                    for reference in references
                )

    return RequisiteRule(
        course_code=normalized_course,
        summary="; ".join(summaries),
        groups=groups,
        parse_warning="; ".join(warnings),
    )


def evaluate_requisites(
    rule: RequisiteRule,
    completed_courses: set[str],
    available_same_term: set[str] | None = None,
) -> RequisiteEvaluation:
    """Evaluate enforced prerequisites and identify same-term corequisites."""
    completed = {normalize_course_code(item) for item in completed_courses}
    available = {normalize_course_code(item) for item in (available_same_term or set())}
    if rule.parse_warning:
        detail = rule.summary or "Catalog requisite needs manual verification."
        return RequisiteEvaluation("unknown", f"{detail} ({rule.parse_warning})")

    blocking = [group for group in rule.groups if not group.recommended]
    if not blocking:
        return RequisiteEvaluation(
            "none", rule.summary or "No enforced catalog requisites listed."
        )

    missing: list[list[str]] = []
    corequisites: list[list[str]] = []
    for group in blocking:
        met = any(option in completed for option in group.options)
        if group.kind == "corequisite" and not met:
            corequisites.append(group.options)
            met = any(option in available for option in group.options)
        if not met:
            missing.append(group.options)

    if missing:
        return RequisiteEvaluation("unmet", rule.summary, missing, corequisites)
    if corequisites:
        return RequisiteEvaluation("corequisite", rule.summary, [], corequisites)
    return RequisiteEvaluation("met", rule.summary)
