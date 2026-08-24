"""Small, deterministic document-ingestion helpers for user-provided records."""

from __future__ import annotations

import base64
import binascii
import io
import re

import pdfplumber

_COURSE_CODE = re.compile(
    r"\b([A-Z]{2,6}(?:\s+[A-Z]{2,6})?)\s+(\d{1,3}[A-Z]?)\b",
    re.IGNORECASE,
)
_MAX_PDF_BYTES = 15 * 1024 * 1024


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
