"""Evidence-first report generation."""

from __future__ import annotations

from datetime import datetime, timezone

from course_planner.utils import ScheduleCandidate, StudentProfile


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
            "| Rank | Courses | Score | Units | Enrollment chance | Schedule quality |",
            "|---:|---|---:|---:|---:|---:|",
        ])
        for candidate in candidates[:3]:
            lines.append(
                f"| {candidate.rank} | {', '.join(item['course_code'] for item in candidate.courses)} | "
                f"{candidate.composite_score:.3f} | {candidate.total_units} | "
                f"{candidate.min_enrollment_chance:.0%} | {candidate.schedule_quality_score:.3f} |"
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
    lines.extend(["", "## Methodology", "Deterministic constraint filtering and weighted ranking are applied before language-model explanation. Missing evidence lowers confidence and is reported instead of being silently treated as a positive signal."])
    return "\n".join(lines)
