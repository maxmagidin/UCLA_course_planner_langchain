"""Small, deterministic document-ingestion helpers for user-provided records."""

from __future__ import annotations

import base64
import binascii
import io
import re

import pdfplumber

_COURSE_CODE = re.compile(
    r"\b([A-Z][A-Z&]{1,7}(?:\s+[A-Z][A-Z&]{1,7})?)\s+((?:C?M)?\d{1,3}[A-Z]{0,2})\b",
    re.IGNORECASE,
)
_MAX_PDF_BYTES = 15 * 1024 * 1024
_MAX_PDF_PAGES = 80


def _line_value(text: str, labels: str) -> str | None:
    match = re.search(
        rf"(?im)^\s*(?:{labels})\s*[:\-]\s*([^\r\n]{{1,120}}?)\s*$",
        text,
    )
    return match.group(1).strip() if match else None


def extract_text_from_pdf_base64(encoded_pdf: str) -> str:
    """Extract text from a base64-encoded PDF without sending it to an LLM."""
    if len(encoded_pdf) > _MAX_PDF_BYTES * 2:
        raise ValueError("DARS PDF exceeds the 15 MB upload limit")
    try:
        pdf_bytes = base64.b64decode(encoded_pdf, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("DARS PDF is not valid base64") from exc
    if len(pdf_bytes) > _MAX_PDF_BYTES:
        raise ValueError("DARS PDF exceeds the 15 MB upload limit")
    pieces: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if len(pdf.pages) > _MAX_PDF_PAGES:
            raise ValueError(
                f"DARS PDF exceeds the {_MAX_PDF_PAGES}-page processing limit"
            )
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pieces.append(text)
    return "\n".join(pieces)


def extract_course_codes(text: str) -> list[str]:
    """Extract normalized course codes such as ``COM SCI 31`` from DARS text."""
    text = re.sub(
        r"\b(?:and|or|the)\s+(?=[A-Z]{2,6}\s+\d)",
        "",
        text or "",
        flags=re.IGNORECASE,
    )
    found = {
        " ".join(f"{department} {number}".upper().split())
        for department, number in _COURSE_CODE.findall(text)
    }
    return sorted(found)


def classify_dars_courses(text: str) -> dict[str, list[str]]:
    """Classify DARS codes conservatively using nearby audit headings.

    Unknown layouts remain reviewable as ``unclassified`` and are not
    automatically counted as completed coursework.
    """
    buckets: dict[str, set[str]] = {
        "completed": set(),
        "in_progress": set(),
        "remaining": set(),
        "unclassified": set(),
    }
    state = "unclassified"
    markers = (
        (
            "in_progress",
            re.compile(
                r"\b(?:in[ -]?progress|currently enrolled|work in progress)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "remaining",
            re.compile(
                r"\b(?:still needed|remaining|not complete|unsatisfied|requirement not satisfied|select .{0,30} from|choose .{0,30} from)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "completed",
            re.compile(
                r"\b(?:courses? completed|completed courses?|course history|work completed|requirements? satisfied|courses? taken)\b",
                re.IGNORECASE,
            ),
        ),
    )
    for line in (text or "").splitlines():
        stripped = " ".join(line.split())
        if not stripped:
            continue
        line_state = state
        for candidate, pattern in markers:
            if pattern.search(stripped):
                state = candidate
                line_state = candidate
                break
        codes = extract_course_codes(stripped)
        if not codes:
            continue
        if re.search(r"\b(?:IP|IN PROGRESS)\b", stripped, re.IGNORECASE):
            line_state = "in_progress"
        elif re.search(
            r"\b(?:NEEDED|REMAINING|NOT COMPLETE)\b", stripped, re.IGNORECASE
        ):
            line_state = "remaining"
        elif re.search(r"\b(?:A[+\-]?|B[+\-]?|C[+\-]?|D[+\-]?|F|P|NP|CR)\b", stripped):
            line_state = "completed"
        buckets[line_state].update(codes)

    # A course shown in history wins over a repeated appearance in a rule list.
    buckets["remaining"] -= buckets["completed"] | buckets["in_progress"]
    buckets["unclassified"] -= (
        buckets["completed"] | buckets["in_progress"] | buckets["remaining"]
    )
    return {key: sorted(value) for key, value in buckets.items()}


def extract_dars_hints(text: str) -> dict[str, str | float]:
    """Extract only strongly labelled profile fields from a DARS report.

    DARS layouts change, so these values are hints for a user-review step, not
    a complete student profile. Course codes are handled separately by
    :func:`extract_course_codes`.
    """
    hints: dict[str, str | float] = {}

    name = _line_value(text, r"student\s+name|name")
    if name and not re.search(r"\d", name):
        hints["name"] = name

    major = _line_value(text, r"declared\s+major|major|academic\s+program|program")
    if major:
        hints["major"] = major

    year = _line_value(text, r"class\s+level|academic\s+level|year")
    if year:
        normalized_year = year.lower().strip()
        for level in ("freshman", "sophomore", "junior", "senior", "graduate"):
            if level in normalized_year:
                hints["year"] = level
                break

    gpa_match = re.search(
        r"(?im)^\s*(?:(?:cumulative|overall|ucla)\s+)?gpa\s*[:\-]?\s*(\d(?:\.\d{1,3})?)\b",
        text,
    )
    if gpa_match:
        gpa = float(gpa_match.group(1))
        if 0 <= gpa <= 4:
            hints["gpa"] = gpa

    units_match = re.search(
        r"(?im)^\s*(?:units?\s+(?:completed|earned)|completed\s+units?|"
        r"total\s+units?)\s*[:\-]?\s*(\d+(?:\.\d+)?)\b",
        text,
    )
    if units_match:
        units = float(units_match.group(1))
        if 0 <= units <= 500:
            hints["units_completed"] = units

    return hints
