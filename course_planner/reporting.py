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
        sections = "/".join(
            filter(
                None,
                [
                    course.get("lecture_section_id", ""),
                    course.get("discussion_section_id", ""),
                ],
            )
        )
        labels.append(
            f"{course['course_code']} ({sections})"
            if sections
            else course["course_code"]
        )
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
        lines.extend(
            [
                "## Recommended schedule",
                f"**Rank #1:** {codes}",
                f"**Composite:** {top.composite_score:.3f} · **Units:** {top.total_units} · **Enrollment risk:** {top.enrollment_risk_level} ({top.enrollment_confidence} confidence)",
                "",
                "| Rank | Courses and sections | Score | Units | Enrollment risk | Schedule quality |",
                "|---:|---|---:|---:|---:|---:|",
            ]
        )
        for candidate in candidates[:3]:
            lines.append(
                f"| {candidate.rank} | {_schedule_label(candidate)} | "
                f"{candidate.composite_score:.3f} | {candidate.total_units} | "
                f"{candidate.enrollment_risk_level} ({candidate.enrollment_confidence}) | {candidate.schedule_quality_score:.3f} |"
            )
        lines.extend(
            [
                "",
                "## Recommended meeting times",
                "",
                "| Day | Course | Section | Time | Instructor | Location |",
                "|---|---|---|---|---|---|",
            ]
        )
        for day in top.day_schedules:
            for section in day.sections:
                lines.append(
                    f"| {day.day} | {section['course_code']} | {section['section_id']} | "
                    f"{_clock(section['start_min'])}–{_clock(section['end_min'])} | "
                    f"{section.get('instructor', '') or 'TBA'} | {section.get('location', '') or 'TBA'} |"
                )
        lines.append("")
        if top.has_unverified_meeting_times:
            lines.extend(
                [
                    "> **Meeting-time warning:** At least one selected section has a TBA or unparseable time, so its conflict check is incomplete.",
                    "",
                ]
            )
        lines.extend(
            [
                "## Prerequisite eligibility",
                "",
                "| Course | Status | Official catalog rule |",
                "|---|---|---|",
            ]
        )
        for course in top.courses:
            summary = str(course.get("prerequisite_summary", "")).replace("|", "\\|")
            url = course.get("catalog_url", "")
            label = (
                f"[{course['course_code']}]({url})" if url else course["course_code"]
            )
            lines.append(
                f"| {label} | {course.get('prerequisite_status', 'unknown')} | {summary} |"
            )
        lines.extend(
            [
                "",
                "Availability is a section-specific ordinal risk score, not a calibrated probability or guarantee of enrollment.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Recommendation",
                "No valid schedule was found under the supplied hard constraints.",
                "",
            ]
        )

    lines.extend(["## Evidence and freshness", ""])
    for source, record in sorted(evidence.items()):
        lines.append(
            f"- **{source}:** {record.get('status', 'unknown')} · fetched {record.get('fetched_at', 'unknown')} · {record.get('detail', '')}"
        )
    if errors:
        lines.extend(["", "## Partial failures", ""])
        for error in errors:
            lines.append(f"- **{error['node']}:** {error['message']}")
    lines.extend(
        [
            "",
            "## Methodology",
            "Official UCLA Catalog rules are parsed and checked deterministically before constraint filtering and weighted ranking; no language model is involved in direct planning. Missing or ambiguous prerequisite evidence blocks eligibility, while missing optional ranking evidence is omitted from weighted scoring and reported.",
        ]
    )
    return "\n".join(lines)
