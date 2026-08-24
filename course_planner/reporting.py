"""Evidence-first report generation."""

from __future__ import annotations

from datetime import datetime, timezone

from course_planner.utils import ScheduleCandidate, StudentProfile


def _clock(minutes: int) -> str:
    hours, minute = divmod(minutes, 60)
    suffix = "am" if hours < 12 else "pm"
    display_hour = hours % 12 or 12
    return f"{display_hour}:{minute:02d}{suffix}"


def _schedule_label(candidate: ScheduleCandidate) -> str:
    labels: list[str] = []
    for course in candidate.courses:
        sections = "/".join(filter(None, [
            course.get("lecture_section_id", ""),
            course.get("discussion_section_id", ""),
        ]))
        labels.append(f"{course['course_code']} ({sections})" if sections else course["course_code"])
    return ", ".join(labels)


def build_report(
    candidates: list[ScheduleCandidate],
    profile: StudentProfile,
    evidence: dict[str, dict],
    errors: list[dict],
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# UCLA Course Planner Report",
        f"**Student:** {profile.name}",
        f"**Major:** {profile.major}",
        f"**Term:** {profile.term if hasattr(profile, 'term') else 'configured term'}",
        f"**Generated:** {now}",
        "",
    ]
    if candidates:
        top = candidates[0]
        codes = ", ".join(item["course_code"] for item in top.courses)
        lines.extend([
            "## Recommended schedule",
            f"**Rank #1:** {codes}",
            f"**Composite:** {top.composite_score:.3f} · **Units:** {top.total_units} · **Enrollment chance:** {top.min_enrollment_chance:.0%}",
            "",
            "| Rank | Courses and sections | Score | Units | Enrollment chance | Schedule quality |",
            "|---:|---|---:|---:|---:|---:|",
        ])
        for candidate in candidates[:3]:
            lines.append(
                f"| {candidate.rank} | {_schedule_label(candidate)} | "
                f"{candidate.composite_score:.3f} | {candidate.total_units} | "
                f"{candidate.min_enrollment_chance:.0%} | {candidate.schedule_quality_score:.3f} |"
            )
        lines.extend([
            "",
            "## Recommended meeting times",
            "",
            "| Day | Course | Section | Time | Instructor | Location |",
            "|---|---|---|---|---|---|",
        ])
        for day in top.day_schedules:
            for section in day.sections:
                lines.append(
                    f"| {day.day} | {section['course_code']} | {section['section_id']} | "
                    f"{_clock(section['start_min'])}–{_clock(section['end_min'])} | "
                    f"{section.get('instructor', '') or 'TBA'} | {section.get('location', '') or 'TBA'} |"
                )
        lines.append("")
    else:
        lines.extend(["## Recommendation", "No valid schedule was found under the supplied hard constraints.", ""])

    lines.extend(["## Evidence and freshness", ""])
    for source, record in sorted(evidence.items()):
        lines.append(f"- **{source}:** {record.get('status', 'unknown')} · fetched {record.get('fetched_at', 'unknown')} · {record.get('detail', '')}")
    if errors:
        lines.extend(["", "## Partial failures", ""])
        for error in errors:
            lines.append(f"- **{error['node']}:** {error['message']}")
    lines.extend(["", "## Methodology", "Deterministic constraint filtering and weighted ranking are used for this direct-planning report; no language model is involved. Missing evidence is omitted from weighted scoring and reported instead of being silently treated as a positive signal."])
    return "\n".join(lines)
