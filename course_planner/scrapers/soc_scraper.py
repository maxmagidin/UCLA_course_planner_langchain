"""Scraper for the UCLA Schedule of Classes (sa.ucla.edu/ro/public/soc).

The SOC front-end is a dynamic web component, but the underlying data is
served by internal JSON endpoints.  We hit those directly with httpx.
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from course_planner.terms import parse_ucla_term

logger = logging.getLogger(__name__)

BASE_URL = "https://sa.ucla.edu/ro/public/soc"
RESULTS_URL = "https://sa.ucla.edu/ro/Public/SOC/Results"
COURSE_SUMMARY_URL = f"{RESULTS_URL}/GetCourseSummary"

# Shared client headers to mimic a browser request.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Referer": BASE_URL,
    "X-Requested-With": "XMLHttpRequest",
}


def _term_code(quarter: str) -> str:
    """Convert e.g. 'Fall 2025' -> '25F'."""
    return parse_ucla_term(quarter).soc_code


def _parse_time(raw: str) -> tuple[str, str]:
    """Best-effort parse of UCLA time ranges such as ``12pm-1:50pm``."""
    raw = raw.strip()
    m = re.search(
        r"(\d{1,2}(?::\d{2})?\s*[ap]m?)\s*[-–]\s*"
        r"(\d{1,2}(?::\d{2})?\s*[ap]m?)",
        raw,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return raw, ""


def _element_text(element) -> str:
    """Read normal and template-backed text nodes from UCLA HTML fragments."""
    if element is None:
        return ""
    return " ".join(
        str(value).strip()
        for value in element.find_all(string=True)
        if str(value).strip()
    )


def _course_models(html: str) -> dict[str, dict[str, Any]]:
    """Extract the JSON models UCLA registers for expandable result rows."""
    models: dict[str, dict[str, Any]] = {}
    pattern = re.compile(r'AddToCourseData\("([^\"]+)",(\{.*?\})\)', re.DOTALL)
    for path, encoded in pattern.findall(html):
        try:
            models[path] = json.loads(encoded)
        except json.JSONDecodeError:
            logger.debug("Could not decode UCLA course model for %s", path)
    return models


def _parse_course_titles(html: str, department: str) -> list[dict[str, Any]]:
    """Parse the initial result page without issuing per-course requests."""
    soup = BeautifulSoup(html, "html.parser")
    models = _course_models(html)
    courses: list[dict[str, Any]] = []
    for row in soup.select("div.class-title[id]"):
        path = str(row.get("id", ""))
        model = models.get(path)
        button = row.select_one("[id$='-title']")
        label = (
            str(button.string).strip()
            if button and button.string
            else _element_text(button)
        )
        if not model or " - " not in label:
            continue
        catalog, title = label.split(" - ", 1)
        subject = str(model.get("SubjectAreaCode") or department).strip()
        courses.append(
            {
                "course_code": " ".join(f"{subject} {catalog}".upper().split()),
                "title": title.strip(),
                "model": model,
            }
        )
    return courses


def _section_type(section_id: str) -> str:
    lowered = section_id.lower()
    if lowered.startswith(("dis", "lab", "tut")):
        return "lab" if lowered.startswith("lab") else "discussion"
    return "lecture"


def _parse_section_rows(
    html: str, *, parent_section_id: str = ""
) -> list[dict[str, Any]]:
    """Parse section rows returned by ``GetCourseSummary``."""
    soup = BeautifulSoup(html, "html.parser")
    sections: list[dict[str, Any]] = []
    for row in soup.select(".data_row.class-info[id]"):
        section_cell = row.select_one(".sectionColumn")
        section_link = section_cell.select_one("a") if section_cell else None
        section_id = _element_text(section_link)
        if not section_id:
            match = re.search(
                r"\b(?:Lec|Dis|Lab|Sem|Tut)\s*\w+",
                _element_text(section_cell),
                re.IGNORECASE,
            )
            section_id = match.group(0) if match else ""
        if not section_id:
            continue

        day_cell = row.select_one(".dayColumn")
        day_button = day_cell.select_one("button") if day_cell else None
        days = _element_text(day_button or day_cell)

        time_text = _element_text(row.select_one(".timeColumn"))
        start_time, end_time = _parse_time(time_text)
        status_text = _element_text(row.select_one(".statusColumn"))
        waitlist_text = _element_text(row.select_one(".waitlistColumn"))
        enrolled_match = re.search(
            r"(\d+)\s+(?:of|/)\s+(\d+)\s+Enrolled", status_text, re.IGNORECASE
        )
        if not enrolled_match:
            enrolled_match = re.search(r"(\d+)\s*/\s*(\d+)", status_text)
        waitlist_match = re.search(
            r"(\d+)\s+(?:of|/)\s+(\d+)\s+Taken", waitlist_text, re.IGNORECASE
        )
        if not waitlist_match:
            waitlist_match = re.search(r"(\d+)\s*/\s*(\d+)", waitlist_text)

        location = _element_text(row.select_one(".locationColumn"))
        instructor = _element_text(row.select_one(".instructorColumn"))
        row_text = _element_text(row).lower()
        section_format = "in-person"
        if "online" in row_text or "remote" in row_text:
            section_format = "online"
        elif "hybrid" in row_text:
            section_format = "hybrid"

        units_match = re.search(
            r"\d+(?:\.\d+)?", _element_text(row.select_one(".unitsColumn"))
        )
        sections.append(
            {
                "section_id": section_id,
                "parent_section_id": parent_section_id,
                "days": days,
                "start_time": start_time,
                "end_time": end_time,
                "location": location,
                "instructor": instructor,
                "enrolled": int(enrolled_match.group(1)) if enrolled_match else 0,
                "capacity": int(enrolled_match.group(2)) if enrolled_match else 0,
                "waitlist": int(waitlist_match.group(1)) if waitlist_match else 0,
                "waitlist_capacity": int(waitlist_match.group(2))
                if waitlist_match
                else 0,
                "format": section_format,
                "section_type": _section_type(section_id),
                "units": float(units_match.group(0)) if units_match else None,
                "_path": str(row.get("id", "")),
            }
        )
    return sections


def _extract_sections_from_html(html: str) -> list[dict]:
    """Backward-compatible section-fragment parser used by legacy callers."""
    return [
        {
            key: value
            for key, value in section.items()
            if not key.startswith("_") and key != "units"
        }
        for section in _parse_section_rows(html)
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_available_departments(quarter: str = "Fall 2025") -> list[str]:
    """Return a list of all department / subject-area names offered in *quarter*.

    Scrapes the SOC main page's subject-area dropdown.
    """
    term = _term_code(quarter)
    params = {"t": term}
    try:
        with httpx.Client(
            headers=_HEADERS,
            timeout=httpx.Timeout(30, connect=8),
            follow_redirects=True,
            transport=httpx.HTTPTransport(retries=2),
        ) as client:
            resp = client.get(BASE_URL, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            depts: list[str] = []
            # Older versions rendered ordinary <option> elements.
            for opt in soup.select("option"):
                val = (opt.get("value") or "").strip()
                label = opt.get_text(strip=True)
                if (
                    val
                    and label
                    and val != "0"
                    and not re.fullmatch(r"\d{2}[FWS12]", val)
                ):
                    depts.append(label)
            if depts:
                return depts

            # The current site passes an HTML-escaped JSON array to its
            # autocomplete widget instead of rendering <option> elements.
            match = re.search(
                r"SearchPanelSetup\('(.+?)',\s*'select_filter_subject'",
                resp.text,
                re.DOTALL,
            )
            if match:
                items = json.loads(html_lib.unescape(match.group(1)))
                return [
                    str(
                        item.get("label") or item.get("text") or item.get("value", "")
                    ).strip()
                    for item in items
                    if isinstance(item, dict)
                ]
    except Exception:
        logger.exception("Failed to fetch departments")

    return []


def scrape_quarter_courses(
    quarter: str,
    department: str,
    *,
    course_codes: list[str] | None = None,
    max_courses: int | None = None,
    request_timeout_seconds: float = 30,
    request_retries: int = 2,
    log_failures: bool = True,
) -> list[dict]:
    """Scrape course listings for *department* in *quarter* from UCLA SOC.

    Returns a list of dicts, each with keys:
        course_code, title, units, instructor, sections (list[dict]),
        description

    Each section dict contains:
        section_id, days, start_time, end_time, location, instructor,
        enrolled, capacity, waitlist, waitlist_capacity, format
    """
    term = _term_code(quarter)
    # Pass ordinary spaces and let httpx encode them. Passing a literal "+"
    # causes httpx to send "%2B", which UCLA interprets as a different subject.
    subj = " ".join(department.strip().upper().split())

    params: dict[str, Any] = {
        "t": term,
        "sBy": "subject",
        "subj": subj,
        "cls_no": "",
        "btnIsInIndex": "btn_inIndex",
    }

    courses: list[dict] = []

    try:
        with httpx.Client(
            headers=_HEADERS,
            timeout=httpx.Timeout(
                request_timeout_seconds,
                connect=min(8, request_timeout_seconds),
            ),
            follow_redirects=True,
            transport=httpx.HTTPTransport(retries=request_retries),
        ) as client:
            # The initial request establishes the ASP.NET session required by
            # every expandable-course request that follows.
            resp = client.get(RESULTS_URL, params=params)
            resp.raise_for_status()
            if "/error/" in str(resp.url).lower():
                raise RuntimeError(
                    f"UCLA SOC redirected the {subj} search to an error page"
                )

            title_rows = _parse_course_titles(resp.text, subj)
            requested = {
                " ".join(code.upper().split()) for code in (course_codes or [])
            }
            title_rows.sort(
                key=lambda item: (
                    item["course_code"] not in requested,
                    item["course_code"],
                )
            )
            if max_courses is not None and max_courses >= 0:
                explicit = [
                    item for item in title_rows if item["course_code"] in requested
                ]
                others = [
                    item for item in title_rows if item["course_code"] not in requested
                ]
                title_rows = explicit + others[: max(0, max_courses - len(explicit))]

            for item in title_rows:
                try:
                    detail = _get_course_summary(
                        client, item["model"], referer=str(resp.url)
                    )
                    primary_sections = _parse_section_rows(detail)
                    detail_models = _course_models(detail)
                    sections = list(primary_sections)

                    # Lectures with discussions/labs are another expandable
                    # level. Preserve that parent relationship for the solver.
                    for primary in primary_sections:
                        child_model = detail_models.get(primary["_path"])
                        if not child_model:
                            continue
                        child_html = _get_course_summary(
                            client, child_model, referer=str(resp.url)
                        )
                        sections.extend(
                            _parse_section_rows(
                                child_html,
                                parent_section_id=str(primary["section_id"]),
                            )
                        )

                    units = next(
                        (
                            float(section["units"])
                            for section in primary_sections
                            if section.get("units") is not None
                        ),
                        4.0,
                    )
                    cleaned_sections = [
                        {
                            key: value
                            for key, value in section.items()
                            if not key.startswith("_") and key != "units"
                        }
                        for section in sections
                    ]
                    if not cleaned_sections:
                        continue
                    courses.append(
                        {
                            "course_code": item["course_code"],
                            "title": item["title"],
                            "units": units,
                            "instructor": cleaned_sections[0].get("instructor", ""),
                            "description": "",
                            "sections": cleaned_sections,
                        }
                    )
                except Exception:
                    logger.exception(
                        "SOC detail scrape failed for %s / %s",
                        quarter,
                        item["course_code"],
                    )

    except Exception:
        if log_failures:
            logger.exception("SOC scrape failed for %s / %s", quarter, department)
        else:
            logger.debug(
                "Optional SOC scrape failed for %s / %s",
                quarter,
                department,
                exc_info=True,
            )

    return courses


def _get_course_summary(
    client: httpx.Client,
    model: dict[str, Any],
    *,
    referer: str,
) -> str:
    response = client.get(
        COURSE_SUMMARY_URL,
        params={
            "model": json.dumps(model, separators=(",", ":")),
            "FilterFlags": "{}",
            "IsMultiListedTitles": "",
        },
        headers={"Referer": referer},
    )
    response.raise_for_status()
    if "/error/" in str(response.url).lower():
        raise RuntimeError(
            "UCLA SOC course detail request was redirected to an error page"
        )
    return response.text


# ---------------------------------------------------------------------------
# Historical enrollment scraping
# ---------------------------------------------------------------------------

ARCHIVE_URL = "https://registrar.ucla.edu/archives/schedule-of-classes-archive"

# Generate the last 8 quarters going backwards from the current one.
_QUARTER_SEQUENCE = ["Winter", "Spring", "Fall"]


def _recent_quarters(n: int = 8) -> list[str]:
    """Return up to *n* recent quarter strings like 'Fall 2025'."""
    import datetime as _dt

    now = _dt.datetime.now(tz=_dt.timezone.utc).date()
    year = now.year
    # Determine current quarter index
    month = now.month
    if month <= 3:
        qi = 0  # Winter
    elif month <= 6:
        qi = 1  # Spring
    else:
        qi = 2  # Fall

    quarters: list[str] = []
    y, idx = year, qi
    while len(quarters) < n:
        # Go backwards: skip current, start from previous
        idx -= 1
        if idx < 0:
            idx = len(_QUARTER_SEQUENCE) - 1
            y -= 1
        quarters.append(f"{_QUARTER_SEQUENCE[idx]} {y}")
    return quarters


def scrape_historical_enrollment(course_code: str) -> list[dict]:
    """Scrape historical enrollment data for *course_code* from the UCLA
    Schedule of Classes archive.

    Returns up to 4 past quarters of data, each dict containing:
        quarter, final_enrollment, capacity, went_to_waitlist, snapshot_type
    """
    # One recent academic-year cycle is enough to expose recurring demand
    # without multiplying an ordinary plan into an unbounded archive crawl.
    quarters = _recent_quarters(4)
    # Normalize course code for URL matching
    code_norm = " ".join(course_code.upper().split())
    dept = code_norm.rsplit(" ", 1)[0] if " " in code_norm else code_norm

    results: list[dict] = []

    for qtr in quarters:
        term = _term_code(qtr)
        try:
            # Query only the requested archived course first. The general SOC
            # parser already understands UCLA's course-detail response and is
            # more precise than searching the archive index's flattened text.
            archived = scrape_quarter_courses(
                qtr,
                dept,
                course_codes=[code_norm],
                max_courses=1,
                request_timeout_seconds=6,
                request_retries=0,
                log_failures=False,
            )
            matching = [
                course
                for course in archived
                if " ".join(course.get("course_code", "").upper().split()) == code_norm
            ]
            for course in matching:
                sections = course.get("sections", [])
                if not sections:
                    continue
                section = sections[0]
                enrolled = int(section.get("enrolled", 0))
                capacity = int(section.get("capacity", 0))
                waitlist = int(section.get("waitlist", 0))
                results.append(
                    {
                        "quarter": qtr,
                        "final_enrollment": enrolled,
                        "capacity": capacity,
                        "went_to_waitlist": waitlist > 0,
                        "snapshot_type": "final",
                    }
                )
            if matching:
                continue

            # Some older terms are no longer served by the SOC search. Fall
            # back to the Registrar archive page with the same short budget.
            with httpx.Client(
                headers=_HEADERS,
                timeout=httpx.Timeout(6, connect=6),
                follow_redirects=True,
                transport=httpx.HTTPTransport(retries=0),
            ) as client:
                resp = client.get(
                    ARCHIVE_URL,
                    params={"term": term},
                )
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                page_text = soup.get_text(" ", strip=True)
                if code_norm not in page_text.upper():
                    continue

                # Parse enrollment data from the archive page
                # Look for rows matching the course code
                enroll_match = re.search(
                    re.escape(code_norm) + r".*?(\d+)\s*/\s*(\d+)",
                    page_text,
                    re.IGNORECASE,
                )
                if enroll_match:
                    enrolled = int(enroll_match.group(1))
                    cap = int(enroll_match.group(2))
                    wl_match = re.search(
                        re.escape(code_norm) + r".*?[Ww]aitlist\D*(\d+)",
                        page_text,
                        re.IGNORECASE,
                    )
                    wl = int(wl_match.group(1)) if wl_match else 0
                    results.append(
                        {
                            "quarter": qtr,
                            "final_enrollment": enrolled,
                            "capacity": cap,
                            "went_to_waitlist": wl > 0 or enrolled >= cap,
                            "snapshot_type": "final",
                        }
                    )

        except Exception:  # noqa: BLE001 - one unavailable archive quarter is non-fatal
            logger.debug("Historical scrape failed for %s / %s", course_code, qtr)
            continue

    return results
