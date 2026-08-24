"""Deterministic schedule ranking extracted from the legacy worker."""

from __future__ import annotations

from course_planner.utils import ScheduleCandidate, StudentProfile


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def rank_schedules(candidates: list[ScheduleCandidate], profile: StudentProfile) -> list[ScheduleCandidate]:
    weights = [
        profile.weight_enrollment_chance,
        profile.weight_professor_rating,
        profile.weight_avg_gpa,
        profile.weight_schedule_quality,
        profile.weight_workload,
    ]
    total = sum(weights)
    weights = [value / total for value in weights] if total else [0.2] * 5

    for candidate in candidates:
        enroll = _clamp(candidate.avg_enrollment_chance)
        professor = _clamp((candidate.avg_bruinwalk_composite or 0.0) / 5.0)
        gpa = _clamp((candidate.avg_gpa or 0.0) / 4.0)
        schedule = _clamp(candidate.schedule_quality_score)
        workload = _clamp(1.0 - (candidate.avg_workload_hours_per_week or 0.0) / 20.0)
        candidate.composite_score = round(_clamp(sum(metric * weight for metric, weight in zip(
            [enroll, professor, gpa, schedule, workload], weights
        ))), 4)
        candidate.preference_match_score = _preference_match(candidate, profile)

    candidates.sort(key=lambda item: (item.composite_score, item.preference_match_score), reverse=True)
    for index, candidate in enumerate(candidates, start=1):
        candidate.rank = index
    return candidates


def _preference_match(candidate: ScheduleCandidate, profile: StudentProfile) -> float:
    selected = {item["course_code"].upper() for item in candidate.courses}
    required = {item.upper() for item in profile.required_courses}
    preferred = {item.upper() for item in profile.preferred_courses}
    score = 0.0
    if required.issubset(selected):
        score += 0.3
    score += min(0.4, 0.15 * len(selected & preferred))
    if profile.min_units <= candidate.total_units <= profile.max_units:
        score += 0.2
    if not candidate.has_time_conflicts:
        score += 0.1
    return round(_clamp(score), 4)
