"""Side-effect-free deterministic schedule generation.

This module deliberately has no ``uagents`` imports, so it is safe to invoke
from FastAPI worker threads, tests, the CLI, and LangGraph nodes.
"""

from __future__ import annotations

import itertools
import re

from course_planner.utils import (
    CourseOption,
    DaySchedule,
    ScheduleCandidate,
    Section,
    StudentProfile,
)

MAX_CANDIDATES = 20
_DAY_CHARS = {
    "M": "Monday",
    "T": "Tuesday",
    "W": "Wednesday",
    "R": "Thursday",
    "F": "Friday",
    "S": "Saturday",
    "U": "Sunday",
}


def parse_minutes(value: str) -> int | None:
    """Parse UCLA 12/24-hour values such as ``12pm`` and ``14:30``."""
    match = re.fullmatch(
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
        value.strip().lower().replace(".", ""),
    )
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    suffix = match.group(3)
    if hour > 23 or minute > 59 or (suffix and not 1 <= hour <= 12):
        return None
    if suffix == "pm" and hour != 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    return hour * 60 + minute


def _section_time_blocks(section: Section) -> list[tuple[str, int, int]]:
    start = parse_minutes(section.start_time)
    end = parse_minutes(section.end_time)
    if start is None or end is None:
        return []
    return [
        (day, start, end)
        for character in section.days.upper()
        if (day := _DAY_CHARS.get(character))
    ]


def _blocks_conflict(
    left: list[tuple[str, int, int]],
    right: list[tuple[str, int, int]],
) -> bool:
    return any(
        left_day == right_day and left_start < right_end and right_start < left_end
        for left_day, left_start, left_end in left
        for right_day, right_start, right_end in right
    )


def _parse_constraints(profile: StudentProfile) -> dict:
    days_off: set[str] = set()
    no_before: int | None = None
    no_after: int | None = None
    max_gap: int | None = None
    max_consecutive: int | None = None

    for constraint in profile.hard_constraints or []:
        lowered = constraint.lower().strip()
        for day_name in (
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
        ):
            if day_name in lowered and any(word in lowered for word in ("off", "no", "free")):
                days_off.add(day_name.capitalize())

        match = re.search(
            r"(?:before|earlier than)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
            lowered,
        )
        if match and (minutes := parse_minutes(match.group(1))) is not None:
            no_before = minutes

        match = re.search(
            r"(?:after|later than)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
            lowered,
        )
        if match and (minutes := parse_minutes(match.group(1))) is not None:
            no_after = minutes

        match = re.search(r"(\d+)\s*(?:min|minute).*gap", lowered)
        if match:
            max_gap = int(match.group(1))

        match = re.search(
            r"(\d+)\s*(?:min|minute).*(?:consecutive|back.to.back|straight)",
            lowered,
        )
        if match:
            max_consecutive = int(match.group(1))

    return {
        "days_off": days_off,
        "no_before": no_before,
        "no_after": no_after,
        "max_gap": max_gap,
        "max_consecutive": max_consecutive,
    }


def group_sections(course: CourseOption) -> list[list[Section]]:
    """Return valid lecture plus linked discussion/lab choices."""
    lectures = [
        section
        for section in course.sections
        if section.section_type.lower() not in {"discussion", "dis", "lab", "tut"}
    ]
    discussions = [section for section in course.sections if section not in lectures]
    if not lectures:
        return [[section] for section in course.sections]
    if not discussions:
        return [[lecture] for lecture in lectures]

    options: list[list[Section]] = []
    for lecture in lectures:
        linked = [
            discussion
            for discussion in discussions
            if discussion.parent_section_id == lecture.section_id
        ]
        candidates = linked or [
            discussion for discussion in discussions if not discussion.parent_section_id
        ]
        for discussion in candidates:
            if not _blocks_conflict(
                _section_time_blocks(lecture),
                _section_time_blocks(discussion),
            ):
                options.append([lecture, discussion])
    return options or [[lecture] for lecture in lectures]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _course_combinations(
    courses: list[CourseOption],
    profile: StudentProfile,
) -> list[list[tuple[CourseOption, list[list[Section]]]]]:
    eligible = [course for course in courses if course.prerequisites_met]
    required = [(course, group_sections(course)) for course in eligible if course.is_required]
    optional = [(course, group_sections(course)) for course in eligible if not course.is_required]
    required = [(course, options) for course, options in required if options]
    optional = [(course, options) for course, options in optional if options]
    required_units = sum(course.units for course, _ in required)

    combinations: list[list[tuple[CourseOption, list[list[Section]]]]] = []
    for count in range(min(len(optional), 6) + 1):
        for subset in itertools.combinations(optional, count):
            units = required_units + sum(course.units for course, _ in subset)
            if profile.min_units <= units <= profile.max_units:
                combinations.append(required + list(subset))
            if len(combinations) >= 500:
                return combinations
    return combinations


def _valid_section_pick(
    section_pick: tuple[tuple[CourseOption, list[Section]], ...],
    constraints: dict,
    preferred_formats: set[str],
) -> tuple[list[dict], list[tuple[str, int, int]]] | None:
    all_blocks: list[tuple[str, int, int]] = []
    course_infos: list[dict] = []
    for course, sections in section_pick:
        lecture_id = ""
        discussion_id = ""
        for section in sections:
            if preferred_formats and section.format.lower() not in preferred_formats:
                return None
            blocks = _section_time_blocks(section)
            if _blocks_conflict(blocks, all_blocks):
                return None
            for day, start, end in blocks:
                if day in constraints["days_off"]:
                    return None
                if constraints["no_before"] is not None and start < constraints["no_before"]:
                    return None
                if constraints["no_after"] is not None and end > constraints["no_after"]:
                    return None
            all_blocks.extend(blocks)
            if section.section_type.lower() in {"discussion", "dis", "lab", "tut"}:
                discussion_id = section.section_id
            else:
                lecture_id = section.section_id
        course_infos.append({
            "course_code": course.course_code,
            "title": course.title,
            "units": course.units,
            "lecture_section_id": lecture_id,
            "discussion_section_id": discussion_id,
        })
    return course_infos, all_blocks


def _day_schedules(
    section_pick: tuple[tuple[CourseOption, list[Section]], ...],
    constraints: dict,
) -> tuple[list[DaySchedule], float, int] | None:
    blocks_by_day: dict[str, list[tuple[int, int, str, str, str, str]]] = {}
    for course, sections in section_pick:
        for section in sections:
            for day, start, end in _section_time_blocks(section):
                blocks_by_day.setdefault(day, []).append((
                    start,
                    end,
                    course.course_code,
                    section.section_id,
                    section.instructor,
                    section.location,
                ))

    schedules: list[DaySchedule] = []
    total_gap = 0
    max_consecutive = 0
    for day, blocks in sorted(blocks_by_day.items()):
        blocks.sort()
        gaps = [blocks[index][0] - blocks[index - 1][1] for index in range(1, len(blocks))]
        if constraints["max_gap"] is not None and any(
            gap > constraints["max_gap"] for gap in gaps
        ):
            return None

        longest = 0
        if blocks:
            streak_start, streak_end = blocks[0][0], blocks[0][1]
            for block in blocks[1:]:
                if block[0] <= streak_end:
                    streak_end = max(streak_end, block[1])
                else:
                    longest = max(longest, streak_end - streak_start)
                    streak_start, streak_end = block[0], block[1]
            longest = max(longest, streak_end - streak_start)
        if constraints["max_consecutive"] is not None and longest > constraints["max_consecutive"]:
            return None

        positive_gap = sum(gap for gap in gaps if gap > 0)
        total_gap += positive_gap
        max_consecutive = max(max_consecutive, longest)
        schedules.append(DaySchedule(
            day=day,
            sections=[{
                "course_code": course_code,
                "section_id": section_id,
                "start_min": start,
                "end_min": end,
                "instructor": instructor,
                "location": location,
            } for start, end, course_code, section_id, instructor, location in blocks],
            total_minutes=sum(end - start for start, end, *_ in blocks),
            gap_minutes=positive_gap,
            max_consecutive_minutes=longest,
        ))

    average_gap = total_gap / len(schedules) if schedules else 0.0
    return schedules, average_gap, max_consecutive


def generate_schedules(
    courses: list[CourseOption],
    profile: StudentProfile,
) -> list[ScheduleCandidate]:
    """Build, hard-filter, score, and return up to 20 schedule candidates."""
    constraints = _parse_constraints(profile)
    preferred = profile.format_preference.lower().strip()
    preferred_formats = {preferred} if preferred and preferred != "any" else set()
    candidates: list[ScheduleCandidate] = []

    for combination in _course_combinations(courses, profile):
        per_course = [
            [(course, section_group) for section_group in section_groups]
            for course, section_groups in combination
        ]
        if not per_course:
            continue
        product_size = 1
        for choices in per_course:
            product_size *= len(choices)
        if product_size > 2000:
            per_course = [choices[:4] for choices in per_course]

        for section_pick in itertools.product(*per_course):
            valid = _valid_section_pick(section_pick, constraints, preferred_formats)
            if valid is None:
                continue
            course_infos, _ = valid
            schedule_data = _day_schedules(section_pick, constraints)
            if schedule_data is None:
                continue
            day_schedules, average_gap, max_consecutive = schedule_data

            enrollment: list[float] = []
            ratings: list[float] = []
            grades: list[float] = []
            workloads: list[float] = []
            for course, _ in section_pick:
                if course.enrollment_prediction:
                    enrollment.append(course.enrollment_prediction.chance_open_at_pass)
                if course.bruinwalk_composite_score is not None:
                    ratings.append(course.bruinwalk_composite_score)
                if course.grade_distribution and course.grade_distribution.avg_gpa > 0:
                    grades.append(course.grade_distribution.avg_gpa)
                if course.course_ratings and course.course_ratings.avg_hours_per_week is not None:
                    workloads.append(course.course_ratings.avg_hours_per_week)

            days_on_campus = len(day_schedules)
            quality = (
                _clamp(1 - average_gap / 180) * 0.4
                + _clamp(1 - days_on_campus / 5) * 0.3
                + _clamp(1 - max_consecutive / 300) * 0.3
            )
            candidates.append(ScheduleCandidate(
                courses=course_infos,
                day_schedules=day_schedules,
                total_units=sum(course["units"] for course in course_infos),
                days_on_campus=days_on_campus,
                avg_gap_minutes_per_day=round(average_gap, 1),
                max_consecutive_minutes_any_day=max_consecutive,
                avg_enrollment_chance=round(sum(enrollment) / len(enrollment), 4) if enrollment else 0.0,
                min_enrollment_chance=round(min(enrollment), 4) if enrollment else 1.0,
                avg_bruinwalk_composite=round(sum(ratings) / len(ratings), 4) if ratings else None,
                avg_gpa=round(sum(grades) / len(grades), 3) if grades else None,
                min_gpa=round(min(grades), 3) if grades else None,
                avg_workload_hours_per_week=round(sum(workloads) / len(workloads), 1) if workloads else None,
                schedule_quality_score=round(quality, 4),
            ))
            if len(candidates) >= MAX_CANDIDATES * 10:
                break
        if len(candidates) >= MAX_CANDIDATES * 10:
            break

    candidates.sort(key=lambda candidate: candidate.schedule_quality_score, reverse=True)
    return candidates[:MAX_CANDIDATES]


# Compatibility aliases for the legacy worker's private helper names.
_generate_schedules = generate_schedules
_group_sections = group_sections
_parse_minutes = parse_minutes
