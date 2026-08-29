"""Factual Bruinwalk retrieval.

This module only fetches and parses source data. It intentionally has no model
client, platform key, environment setting, or review-summary side effect.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from course_planner.instructor_identity import match_instructor
from course_planner.utils import (
    CourseRatings,
    ProfessorRatings,
    bayesian_adjusted_rating,
    rating_confidence,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://bruinwalk.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html, application/json, */*",
}


def _fetched_at() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _slug(name: str) -> str:
    """Convert 'John Smith' -> 'john-smith' for URL paths."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _course_slug(code: str) -> str:
    """Convert 'COM SCI 31' -> 'com-sci-31' for URL paths."""
    return re.sub(r"[^a-z0-9]+", "-", code.strip().lower()).strip("-")


def _extract_float(text: str) -> float | None:
    m = re.search(r"(\d+\.?\d*)", text)
    return float(m.group(1)) if m else None


def _parse_professor_from_html(
    soup: BeautifulSoup,
    instructor_name: str,
    course_code: str,
    *,
    source_url: str = "",
    fetched_at: str = "",
) -> ProfessorRatings | None:
    """Extract a verified professor/course rating from current Bruinwalk DOM."""
    name_node = soup.select_one(".prof-name")
    source_name = name_node.get_text(" ", strip=True) if name_node else ""
    identity_match = match_instructor(instructor_name, [source_name])
    if not source_name or not identity_match.is_match:
        return None

    wanted_slug = _course_slug(course_code)
    course_link = next(
        (
            anchor
            for anchor in soup.select("a[href]")
            if f"/classes/{wanted_slug}/" in urlparse(anchor["href"]).path
        ),
        None,
    )
    if course_link is None:
        return None

    score_node = soup.select_one(".text-wrapper .overall-score, .overall-score")
    overall_text = soup.select_one(".text-wrapper .overall-text, .overall-text")
    overall = (
        _extract_float(score_node.get_text(" ", strip=True)) if score_node else None
    )
    summary_text = overall_text.get_text(" ", strip=True) if overall_text else ""
    count_match = re.search(
        r"based\s+on\s+(\d+)\s+(?:users?|ratings?|reviews?)",
        summary_text,
        re.IGNORECASE,
    )
    total = int(count_match.group(1)) if count_match else 0
    if overall is None or total <= 0:
        return None

    adjusted = bayesian_adjusted_rating(overall, total)
    if adjusted is None:
        return None
    return ProfessorRatings(
        instructor_name=instructor_name,
        course_code=course_code,
        matched_instructor_name=source_name,
        overall_rating=overall,
        adjusted_rating=adjusted,
        total_reviews=total,
        rating_confidence=rating_confidence(total),
        match_status=identity_match.status,
        source="Bruinwalk",
        source_url=source_url,
        fetched_at=fetched_at,
        status="ok",
    )


def _parse_course_from_html(
    soup: BeautifulSoup,
    course_code: str,
    *,
    source_url: str = "",
    fetched_at: str = "",
) -> CourseRatings | None:
    """Extract an explicit course-level aggregate, if Bruinwalk provides one.

    Current class pages list independent professor cards and do not publish a
    course aggregate. We therefore refuse to infer one from the first card.
    """
    course_link = soup.select_one(f'a[href*="/classes/{_course_slug(course_code)}/"]')
    score_node = soup.select_one(".course-overall-score, [data-course-overall-rating]")
    summary_node = soup.select_one(".course-overall-text, [data-course-rating-summary]")
    if course_link is None or score_node is None or summary_node is None:
        return None
    overall = _extract_float(score_node.get_text(" ", strip=True))
    summary = summary_node.get_text(" ", strip=True)
    count_match = re.search(
        r"(?:based\s+on|from)\s+(\d+)\s+(?:users?|ratings?|reviews?)",
        summary,
        re.IGNORECASE,
    )
    total = int(count_match.group(1)) if count_match else 0
    adjusted = bayesian_adjusted_rating(overall, total)
    if overall is None or adjusted is None:
        return None

    return CourseRatings(
        course_code=course_code,
        overall_course_rating=overall,
        adjusted_rating=adjusted,
        total_reviews=total,
        rating_confidence=rating_confidence(total),
        source="Bruinwalk",
        source_url=source_url,
        fetched_at=fetched_at,
        status="ok",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class _RequestBudget:
    """Bound network work for one scrape while reusing one HTTP client."""

    def __init__(self, client: httpx.Client, maximum: int = 8):
        self.client = client
        self.remaining = maximum

    def get(self, url: str, **kwargs) -> httpx.Response | None:
        if self.remaining <= 0:
            return None
        self.remaining -= 1
        try:
            return self.client.get(url, **kwargs)
        except httpx.HTTPError:
            logger.debug("Bruinwalk request failed: %s", url)
            return None


def _professor_candidates(search_soup: BeautifulSoup, course_code: str) -> list[str]:
    """Return unique professor/course paths from search results.

    Search result ordering is not treated as identity evidence; every
    candidate is fetched and checked against the named professor in the DOM.
    """
    course_slug = _course_slug(course_code)
    paths: list[str] = []
    for anchor in search_soup.select('a[href*="/professors/"]'):
        path = urlparse(anchor["href"]).path.rstrip("/") + "/"
        if "/professors/" not in path:
            continue
        if f"/{course_slug}/" not in path:
            path = path.rstrip("/") + f"/{course_slug}/"
        if path not in paths:
            paths.append(path)
    return paths


def _is_requested_course_url(url: str, course_code: str) -> bool:
    return f"/classes/{_course_slug(course_code)}/" in urlparse(url).path or (
        "/professors/" in urlparse(url).path
        and urlparse(url).path.rstrip("/").endswith(f"/{_course_slug(course_code)}")
    )


def scrape_professor_ratings(
    instructor_name: str, course_code: str
) -> ProfessorRatings | None:
    """Fetch a verified professor rating for the requested course.

    Bruinwalk has both aggregate professor pages and professor/course pages.
    Only the latter are accepted here, and only when the page's displayed
    professor identity and course link both match the request.
    """
    if not instructor_name.strip() or not course_code.strip():
        return None

    fetched_at = _fetched_at()
    direct = (
        f"{BASE_URL}/professors/{_slug(instructor_name)}/{_course_slug(course_code)}/"
    )

    try:
        with httpx.Client(
            headers=_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            budget = _RequestBudget(client)
            search = budget.get(
                f"{BASE_URL}/search/",
                params={"q": instructor_name, "type": "professor"},
            )
            candidates = [direct]
            if search is not None and search.status_code == 200:
                candidates = (
                    _professor_candidates(
                        BeautifulSoup(search.text, "html.parser"), course_code
                    )
                    or candidates
                )

            valid: list[ProfessorRatings] = []
            for path in candidates:
                response = budget.get(urljoin(BASE_URL, path))
                if response is None or response.status_code != 200:
                    continue
                if not _is_requested_course_url(str(response.url), course_code):
                    continue
                parsed = _parse_professor_from_html(
                    BeautifulSoup(response.text, "html.parser"),
                    instructor_name,
                    course_code,
                    source_url=str(response.url),
                    fetched_at=fetched_at,
                )
                if parsed:
                    valid.append(parsed)

            identities = {item.matched_instructor_name for item in valid}
            if len(identities) == 1 and valid:
                return valid[0]

    except Exception:
        logger.exception("Professor scrape failed for %s", instructor_name)

    return None


def scrape_course_ratings(course_code: str) -> CourseRatings | None:
    """Return an explicit Bruinwalk course aggregate, when one exists.

    The current class page contains professor-specific cards, not a
    course-level aggregate. In that layout this intentionally returns
    ``None`` instead of treating the first professor's rating as a course
    rating.
    """
    if not course_code.strip():
        return None

    slug = _course_slug(course_code)
    url = f"{BASE_URL}/classes/{slug}/"
    fetched_at = _fetched_at()

    try:
        with httpx.Client(
            headers=_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            budget = _RequestBudget(client)
            response = budget.get(url)
            if response is None or response.status_code != 200:
                search = budget.get(
                    f"{BASE_URL}/search/",
                    params={"q": course_code, "type": "course"},
                )
                if search is None or search.status_code != 200:
                    return None
                links = [
                    urljoin(BASE_URL, anchor["href"])
                    for anchor in BeautifulSoup(search.text, "html.parser").select(
                        f'a[href*="/classes/{slug}/"]'
                    )
                ]
                response = None
                for candidate in links:
                    if budget.remaining <= 0:
                        break
                    candidate_response = budget.get(candidate)
                    if candidate_response is not None:
                        response = candidate_response
                        break
            if response is None or response.status_code != 200:
                return None
            if not _is_requested_course_url(str(response.url), course_code):
                return None
            return _parse_course_from_html(
                BeautifulSoup(response.text, "html.parser"),
                course_code,
                source_url=str(response.url),
                fetched_at=fetched_at,
            )

    except Exception:
        logger.exception("Course scrape failed for %s", course_code)

    return None
