"""Read authoritative course descriptions from the official UCLA Catalog."""

from __future__ import annotations

import html
import json
import logging
import re
from functools import lru_cache
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CATALOG_BASE_URL = "https://catalog.registrar.ucla.edu"
_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


def catalog_course_url(course_code: str, catalog_year: int) -> str:
    slug = re.sub(r"[^A-Z0-9]", "", course_code.upper())
    return f"{CATALOG_BASE_URL}/course/{catalog_year}/{slug}?year={catalog_year}"


def _page_content(document: str) -> dict[str, Any]:
    match = _NEXT_DATA.search(document)
    if not match:
        raise ValueError("UCLA Catalog response did not contain course data")
    payload = json.loads(html.unescape(match.group(1)))
    page_props = payload.get("props", {}).get("pageProps", {})
    errors = page_props.get("pageErrors") or []
    content = page_props.get("pageContent") or {}
    if errors or not content.get("code"):
        raise ValueError("UCLA Catalog did not return that course")
    return content


def _plain_text(value: str) -> str:
    return " ".join(BeautifulSoup(value or "", "html.parser").get_text(" ").split())


@lru_cache(maxsize=512)
def fetch_catalog_course(course_code: str, catalog_year: int) -> dict[str, Any]:
    """Return normalized official catalog data, cached for this process."""
    normalized = " ".join(course_code.upper().split())
    url = catalog_course_url(normalized, catalog_year)
    try:
        with httpx.Client(
            headers=_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            response = client.get(url)
            response.raise_for_status()
        content = _page_content(response.text)
    except Exception as exc:
        logger.warning("UCLA Catalog lookup failed for %s: %s", normalized, exc)
        raise RuntimeError(f"catalog lookup failed for {normalized}") from exc
    return {
        "course_code": " ".join(str(content.get("code", normalized)).upper().split()),
        "title": str(content.get("title", "")).strip(),
        "description": _plain_text(str(content.get("description", ""))),
        "units": _catalog_units(str(content.get("credit_points_header", ""))),
        "catalog_year": catalog_year,
        "catalog_url": url,
    }


def _catalog_units(value: str) -> float:
    match = re.search(r"\d+(?:\.\d+)?", value or "")
    return float(match.group(0)) if match else 4.0
