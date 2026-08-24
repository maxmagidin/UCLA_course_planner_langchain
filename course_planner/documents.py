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
