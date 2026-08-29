"""Deterministic instructor-name normalization and matching.

UCLA and third-party sources commonly disagree on display format (for
example ``Last, F.M.`` versus ``First Middle Last``). Matching is deliberately
conservative: a surname-only match is accepted only when it identifies one
candidate, and ambiguous matches are rejected rather than assigned silently.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "md", "phd"}


def _clean(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9 ]", " ", value.lower())


@dataclass(frozen=True)
class InstructorIdentity:
    original: str
    normalized: str
    surname: str
    given_names: tuple[str, ...]
    given_initials: str


def normalize_instructor_name(value: str) -> InstructorIdentity:
    """Normalize common ``Last, First`` and ``First Last`` name forms."""
    original = " ".join((value or "").split())
    cleaned = _clean(original)
    if not cleaned:
        return InstructorIdentity(original, "", "", (), "")
    pieces = cleaned.split()
    pieces = [piece for piece in pieces if piece not in _SUFFIXES]
    if "," in (value or ""):
        # Punctuation is removed above, so split the original on comma before
        # cleaning to preserve the explicit surname-first signal.
        surname_part, given_part = (value or "").split(",", 1)
        surname_tokens = _clean(surname_part).split()
        given_tokens = _clean(given_part).split()
        surname = surname_tokens[-1] if surname_tokens else ""
        given = tuple(token for token in given_tokens if token not in _SUFFIXES)
    else:
        surname = pieces[-1] if pieces else ""
        given = tuple(pieces[:-1])
    initials = "".join(token[0] for token in given if token)
    normalized = " ".join((*given, surname)).strip()
    return InstructorIdentity(original, normalized, surname, given, initials)


@dataclass(frozen=True)
class InstructorMatch:
    query: InstructorIdentity
    matched: InstructorIdentity | None
    status: str

    @property
    def is_match(self) -> bool:
        return self.matched is not None and self.status not in {
            "ambiguous",
            "unmatched",
        }


def _given_compatible(query: InstructorIdentity, candidate: InstructorIdentity) -> bool:
    if not query.given_names or not candidate.given_names:
        return True
    # Initials are sufficient when one source abbreviates given names.
    if all(len(token) == 1 for token in query.given_names):
        return all(
            index < len(candidate.given_names)
            and candidate.given_names[index].startswith(token)
            for index, token in enumerate(query.given_names)
        )
    if all(len(token) == 1 for token in candidate.given_names):
        return all(
            index < len(query.given_names)
            and query.given_names[index].startswith(token)
            for index, token in enumerate(candidate.given_names)
        )
    # Sources frequently omit middle names ("David Smallberg" versus
    # "David A Smallberg"). Treat a shorter, matching given-name prefix as
    # compatible while still requiring every supplied name to agree.
    shorter, longer = sorted((query.given_names, candidate.given_names), key=len)
    if len(shorter) < len(longer):
        return all(
            longer[index].startswith(token) for index, token in enumerate(shorter)
        )
    return query.given_names == candidate.given_names


def match_instructor(
    query: str, candidates: list[str] | tuple[str, ...]
) -> InstructorMatch:
    """Match *query* against source names, rejecting ambiguous surnames."""
    query_identity = normalize_instructor_name(query)
    identities = [normalize_instructor_name(item) for item in candidates if item]
    if not query_identity.surname:
        return InstructorMatch(query_identity, None, "unmatched")
    surname_matches = [
        item for item in identities if item.surname == query_identity.surname
    ]
    if not surname_matches:
        return InstructorMatch(query_identity, None, "unmatched")
    compatible = [
        item for item in surname_matches if _given_compatible(query_identity, item)
    ]
    if len(compatible) == 1:
        exact = compatible[0].normalized == query_identity.normalized
        has_given = bool(query_identity.given_names and compatible[0].given_names)
        status = (
            "exact"
            if exact
            else "initial"
            if has_given
            and any(len(token) == 1 for token in query_identity.given_names)
            else "middle"
            if has_given
            else "surname"
        )
        return InstructorMatch(query_identity, compatible[0], status)
    # A surname-only query must never pick arbitrarily among same-surname
    # instructors. Given-name disagreement is also treated as unmatched.
    return InstructorMatch(
        query_identity, None, "ambiguous" if len(surname_matches) > 1 else "unmatched"
    )
