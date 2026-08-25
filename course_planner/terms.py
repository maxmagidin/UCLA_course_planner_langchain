"""Shared UCLA term parsing and catalog-year helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TERM_PATTERN = re.compile(r"^(Fall|Winter|Spring|Summer)\s+(20\d{2})$", re.IGNORECASE)
_SOC_CODES = {"fall": "F", "winter": "W", "spring": "S", "summer": "1"}


@dataclass(frozen=True)
class UclaTerm:
    season: str
    year: int

    @property
    def label(self) -> str:
        return f"{self.season} {self.year}"

    @property
    def soc_code(self) -> str:
        return f"{str(self.year)[-2:]}{_SOC_CODES[self.season.lower()]}"

    @property
    def catalog_year(self) -> int:
        # UCLA catalogs are academic-year based: Winter 2027 uses 2026-27.
        return self.year if self.season == "Fall" else self.year - 1


def parse_ucla_term(value: str) -> UclaTerm:
    """Parse an explicit UCLA term; never silently coerce an unknown season."""
    match = _TERM_PATTERN.fullmatch(" ".join((value or "").split()))
    if not match:
        raise ValueError(
            "term must look like Fall 2026, Winter 2027, Spring 2027, or Summer 2027"
        )
    season = match.group(1).capitalize()
    return UclaTerm(season=season, year=int(match.group(2)))
