"""Deterministic schedule ranking extracted from the legacy worker."""

from __future__ import annotations

from course_planner.utils import ScheduleCandidate, StudentProfile


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def rank_schedules(
    candidates: list[ScheduleCandidate], profile: StudentProfile
) -> list[ScheduleCandidate]:
    for candidate in candidates:
        metrics: list[tuple[float, float]] = [
            (_clamp(candidate.avg_enrollment_chance), profile.weight_enrollment_chance),
            (_clamp(candidate.schedule_quality_score), profile.weight_schedule_quality),
        ]
        if candidate.avg_rating_score is not None:
            metrics.append(
                (
                    _clamp(candidate.avg_rating_score / 5.0),
                    profile.weight_professor_rating,
                )
            )
        if candidate.avg_gpa is not None:
            metrics.append((_clamp(candidate.avg_gpa / 4.0), profile.weight_avg_gpa))
        if candidate.avg_workload_hours_per_week is not None:
            metrics.append(
                (
                    _clamp(1.0 - candidate.avg_workload_hours_per_week / 20.0),
                    profile.weight_workload,
                )
            )

        # Missing evidence is omitted, not treated as a zero or (for workload)
        # accidentally rewarded as a perfect score.
        total_weight = sum(weight for _, weight in metrics)
        score = (
            sum(metric * weight for metric, weight in metrics) / total_weight
            if total_weight
            else 0.0
        )
        candidate.composite_score = round(_clamp(score), 4)
        candidate.preference_match_score = _preference_match(candidate, profile)

    candidates.sort(
        key=lambda item: (item.preference_match_score, item.composite_score),
        reverse=True,
    )
    for index, candidate in enumerate(candidates, start=1):
        candidate.rank = index
    return candidates


def _preference_match(candidate: ScheduleCandidate, profile: StudentProfile) -> float:
    selected = {item["course_code"].upper() for item in candidate.courses}
    required = {item.upper() for item in profile.required_courses}
    preferred = {item.upper() for item in profile.preferred_courses}
    unrequested = selected - required - preferred
    score = 0.0
    if required.issubset(selected):
        score += 0.3
    score += min(0.4, 0.15 * len(selected & preferred))
    if profile.min_units <= candidate.total_units <= profile.max_units:
        score += 0.2
    if not candidate.has_time_conflicts:
        score += 0.1
    # Once the requested courses satisfy the unit range, do not let unrelated
    # electives outrank them solely because one happens to have richer data.
    score -= min(0.3, 0.05 * len(unrequested))
    return round(_clamp(score), 4)
