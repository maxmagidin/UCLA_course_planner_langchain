"""Prerequisite-aware course placement across an academic-year horizon."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from course_planner.prerequisites import normalize_course_code, parse_catalog_requisites
from course_planner.scrapers.catalog_scraper import fetch_catalog_course
from course_planner.terms import parse_ucla_term


@dataclass
class RoadmapTerm:
    term: str
    max_units: float
    courses: list[str] = field(default_factory=list)
    total_units: float = 0.0


@dataclass
class RoadmapSuggestion:
    terms: list[RoadmapTerm]
    unplaced_courses: list[str]
    warnings: list[str]


def suggest_roadmap(
    completed_courses: list[str],
    requested_courses: list[str],
    terms: list[tuple[str, float]],
) -> RoadmapSuggestion:
    """Place each course in its earliest eligible term within unit limits."""
    completed = {normalize_course_code(item) for item in completed_courses}
    requested = list(
        dict.fromkeys(
            normalize_course_code(item) for item in requested_courses if item.strip()
        )
    )
    if not terms:
        return RoadmapSuggestion([], requested, ["At least one term is required."])
    catalog_year = parse_ucla_term(terms[0][0]).catalog_year
    catalog: dict[str, dict] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(requested)))) as pool:
        jobs = {
            pool.submit(fetch_catalog_course, code, catalog_year): code
            for code in requested
        }
        for future in as_completed(jobs):
            code = jobs[future]
            try:
                catalog[code] = future.result()
            except Exception as exc:  # noqa: BLE001 - preserve partial roadmap results
                failures[code] = str(exc)

    rules = {
        code: parse_catalog_requisites(code, str(record.get("description", "")))
        for code, record in catalog.items()
    }
    remaining = [code for code in requested if code in catalog]
    result_terms: list[RoadmapTerm] = []
    warnings = [
        f"{code}: official catalog lookup failed; course was not placed."
        for code in sorted(failures)
    ]

    def prerequisites_met(code: str) -> bool:
        rule = rules[code]
        return not rule.parse_warning and all(
            any(option in completed for option in group.options)
            for group in rule.groups
            if not group.recommended and group.kind == "prerequisite"
        )

    for term_label, max_units in terms:
        term = RoadmapTerm(term=parse_ucla_term(term_label).label, max_units=max_units)
        for code in list(remaining):
            rule = rules[code]
            if rule.parse_warning:
                continue
            if not prerequisites_met(code):
                continue
            corequisite_groups = [
                group
                for group in rule.groups
                if not group.recommended and group.kind == "corequisite"
            ]
            companions: list[str] = []
            corequisites_available = True
            for group in corequisite_groups:
                if any(
                    option in completed or option in term.courses
                    for option in group.options
                ):
                    continue
                companion = next(
                    (
                        option
                        for option in group.options
                        if option in remaining and prerequisites_met(option)
                    ),
                    None,
                )
                if companion:
                    companions.append(companion)
                else:
                    corequisites_available = False
            if not corequisites_available:
                continue
            placement = list(dict.fromkeys([code, *companions]))
            placement_units = sum(
                float(catalog[item].get("units", 4.0)) for item in placement
            )
            if term.total_units + placement_units > max_units:
                continue
            for item in placement:
                if item in remaining:
                    term.courses.append(item)
                    term.total_units += float(catalog[item].get("units", 4.0))
                    remaining.remove(item)
        result_terms.append(term)
        # Prerequisites must be completed in an earlier term, not concurrently.
        completed.update(term.courses)

    for code in remaining:
        rule = rules[code]
        unmet = [
            " or ".join(group.options)
            for group in rule.groups
            if not group.recommended
            and group.kind == "prerequisite"
            and not any(option in completed for option in group.options)
        ]
        if rule.parse_warning:
            reason = f"catalog rule needs manual review ({rule.parse_warning})"
        else:
            reason = (
                f"needs {'; '.join(unmet)}"
                if unmet
                else "did not fit the term unit limits"
            )
        warnings.append(f"{code}: {reason}.")
    unplaced = [
        code
        for code in requested
        if code not in {item for term in result_terms for item in term.courses}
    ]
    return RoadmapSuggestion(result_terms, unplaced, warnings)
