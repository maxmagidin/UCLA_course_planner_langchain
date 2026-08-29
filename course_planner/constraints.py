"""Canonical parsing and serialization for user schedule constraints."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConstraintParseError(ValueError):
    """A free-form constraint is outside the supported schedule vocabulary."""


class ConstraintSet(BaseModel):
    """Normalized constraints consumed by the scheduler."""

    model_config = ConfigDict(extra="forbid")

    days_off: list[str] = Field(default_factory=list, max_length=7)
    no_before: int | None = Field(default=None, ge=0, le=1439)
    no_after: int | None = Field(default=None, ge=0, le=1439)
    max_gap: int | None = Field(default=None, ge=0, le=1440)
    max_consecutive: int | None = Field(default=None, ge=0, le=1440)

    @model_validator(mode="after")
    def valid_time_range(self) -> ConstraintSet:
        if (
            self.no_before is not None
            and self.no_after is not None
            and self.no_after < self.no_before
        ):
            raise ValueError(
                "latest allowed start cannot be before earliest allowed start"
            )
        return self


_DAY_NAMES = {
    "m": "Monday",
    "mo": "Monday",
    "mon": "Monday",
    "monday": "Monday",
    "t": "Tuesday",
    "tu": "Tuesday",
    "tue": "Tuesday",
    "tuesday": "Tuesday",
    "w": "Wednesday",
    "we": "Wednesday",
    "wed": "Wednesday",
    "wednesday": "Wednesday",
    "r": "Thursday",
    "th": "Thursday",
    "thu": "Thursday",
    "thursday": "Thursday",
    "f": "Friday",
    "fr": "Friday",
    "fri": "Friday",
    "friday": "Friday",
    "s": "Saturday",
    "sa": "Saturday",
    "sat": "Saturday",
    "saturday": "Saturday",
    "u": "Sunday",
    "su": "Sunday",
    "sun": "Sunday",
    "sunday": "Sunday",
}
_DAY = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun|mo|tu|we|th|sa|su|m|t|w|r|f|s|u)"
_CLOCK = r"\d{1,2}(?::\d{2})?\s*(?:am|pm)?"


def _minutes(value: str) -> int | None:
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", value.strip().lower())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    suffix = match.group(3)
    if minute > 59 or (suffix and not 1 <= hour <= 12) or (not suffix and hour > 23):
        return None
    if suffix == "pm" and hour != 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    return hour * 60 + minute


def _clock(value: int) -> str:
    hour, minute = divmod(value, 60)
    return f"{hour:02d}:{minute:02d}"


def parse_constraints(values: list[str] | None) -> ConstraintSet:
    """Parse supported UI phrases, rejecting silently ignored constraints."""
    result = ConstraintSet()
    days: set[str] = set()
    for raw in values or []:
        text = " ".join(raw.strip().split())
        lowered = text.lower()
        recognized = False
        if (match := re.fullmatch(rf"({_DAY})(?:\s+off|\s+free)", lowered)) or (
            match := re.fullmatch(rf"no classes? on\s+({_DAY})", lowered)
        ):
            days.add(_DAY_NAMES[match.group(1)])
            recognized = True
        elif match := re.fullmatch(
            rf"days?\s+off:\s*({_DAY}(?:\s*,\s*{_DAY})*)", lowered
        ):
            for day in re.split(r"\s*,\s*", match.group(1)):
                days.add(_DAY_NAMES[day])
            recognized = True
        else:
            for direction, attr in (
                ("before", "no_before"),
                ("earlier than", "no_before"),
                ("after", "no_after"),
                ("later than", "no_after"),
            ):
                match = re.fullmatch(
                    rf"(?:no classes?\s+)?{direction}\s+({_CLOCK})", lowered
                )
                if match and (minutes := _minutes(match.group(1))) is not None:
                    setattr(result, attr, minutes)
                    recognized = True
                    break
        if not recognized:
            match = re.fullmatch(
                rf"(?:earliest class|latest class)\s+({_CLOCK})", lowered
            )
            if match and (minutes := _minutes(match.group(1))) is not None:
                setattr(
                    result,
                    "no_before" if lowered.startswith("earliest") else "no_after",
                    minutes,
                )
                recognized = True
        if not recognized:
            match = re.fullmatch(r"(\d+)\s*(?:min|minute)s?\s+gap", lowered)
            if match:
                result.max_gap = int(match.group(1))
                recognized = True
        if not recognized:
            match = re.fullmatch(
                r"(\d+)\s*(?:min|minute)s?\s+(?:consecutive|back[- ]to[- ]back|straight)",
                lowered,
            )
            if match:
                result.max_consecutive = int(match.group(1))
                recognized = True
        if not recognized:
            raise ConstraintParseError(f"Unsupported hard constraint: {raw}")
    result.days_off = sorted(days)
    return result


def serialize_constraints(constraints: ConstraintSet) -> list[str]:
    """Emit stable strings accepted by :func:`parse_constraints`."""
    values = [f"{day} off" for day in constraints.days_off]
    if constraints.no_before is not None:
        values.append(f"No classes before {_clock(constraints.no_before)}")
    if constraints.no_after is not None:
        values.append(f"No classes after {_clock(constraints.no_after)}")
    if constraints.max_gap is not None:
        values.append(f"{constraints.max_gap} minute gap")
    if constraints.max_consecutive is not None:
        values.append(f"{constraints.max_consecutive} minute consecutive")
    return values
