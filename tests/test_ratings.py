from pathlib import Path
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup

from course_planner.instructor_identity import (
    match_instructor,
    normalize_instructor_name,
)
from course_planner.scrapers.bruinwalk_scraper import _parse_professor_from_html
from course_planner.utils import bayesian_adjusted_rating, rating_confidence

FIXTURES = Path(__file__).parent / "fixtures"


def test_bayesian_adjustment_excludes_empty_samples_and_shrinks_tiny_samples():
    assert bayesian_adjusted_rating(5.0, 0) is None
    assert bayesian_adjusted_rating(5.0, 1) < bayesian_adjusted_rating(4.8, 200)
    assert rating_confidence(1) == "low"
    assert rating_confidence(5) == "medium"
    assert rating_confidence(25) == "high"


def test_professor_fixture_is_factual_and_provenanced():
    soup = BeautifulSoup(
        (FIXTURES / "bruinwalk_professor.html").read_text(), "html.parser"
    )
    rating = _parse_professor_from_html(
        soup,
        "Smallberg, David",
        "COM SCI 31",
        source_url="https://bruinwalk.com/professors/david-a-smallberg/com-sci-31/",
        fetched_at="2026-08-28T00:00:00+00:00",
    )
    assert rating is not None
    assert rating.instructor_name == "Smallberg, David"
    assert rating.matched_instructor_name == "David A Smallberg"
    assert rating.course_code == "COM SCI 31"
    assert rating.overall_rating == 4.1
    assert rating.total_reviews == 222
    assert rating.adjusted_rating == bayesian_adjusted_rating(4.1, 222)
    assert rating.rating_confidence == "high"
    assert rating.match_status == "middle"
    assert rating.source == "Bruinwalk"
    assert rating.source_url.endswith("david-a-smallberg/com-sci-31/")


def test_professor_parser_rejects_wrong_course_or_zero_reviews():
    soup = BeautifulSoup(
        (FIXTURES / "bruinwalk_professor.html").read_text(), "html.parser"
    )
    assert _parse_professor_from_html(soup, "Smallberg, David", "COM SCI 32") is None
    zero = BeautifulSoup(
        (FIXTURES / "bruinwalk_professor.html")
        .read_text()
        .replace("Based on 222 Users", "Based on 0 Users"),
        "html.parser",
    )
    assert _parse_professor_from_html(zero, "Smallberg, David", "COM SCI 31") is None


def test_course_page_does_not_treat_first_professor_card_as_course_rating():
    from course_planner.scrapers.bruinwalk_scraper import _parse_course_from_html

    html = '<a href="/classes/com-sci-31/">COM SCI 31</a><div class="overall-score">3.7</div>'
    assert (
        _parse_course_from_html(BeautifulSoup(html, "html.parser"), "COM SCI 31")
        is None
    )


def test_professor_scrape_uses_selected_identity_and_course_path():
    from course_planner.scrapers import bruinwalk_scraper

    search = Mock(
        status_code=200,
        text='<a href="/professors/david-a-smallberg/">David A Smallberg</a>',
    )
    page = Mock(
        status_code=200,
        text=(FIXTURES / "bruinwalk_professor.html").read_text(),
        url="https://bruinwalk.com/professors/david-a-smallberg/com-sci-31/",
    )
    fake_client = Mock()
    fake_client.__enter__ = lambda self: self
    fake_client.__exit__ = lambda self, *args: None
    fake_client.get.side_effect = [search, page]
    with patch.object(bruinwalk_scraper.httpx, "Client", return_value=fake_client):
        rating = bruinwalk_scraper.scrape_professor_ratings(
            "Smallberg, David", "COM SCI 31"
        )
    assert rating is not None
    assert rating.matched_instructor_name == "David A Smallberg"
    assert rating.course_code == "COM SCI 31"
    assert fake_client.get.call_args_list[1].args[0].endswith("/com-sci-31/")


def test_identity_handles_comma_initials_and_punctuation():
    identity = normalize_instructor_name("Doe, J.M.")
    assert identity.surname == "doe"
    assert identity.given_initials == "jm"
    match = match_instructor("Doe, J.M.", ["Jane Marie Doe"])
    assert match.is_match
    assert match.status == "initial"


def test_identity_rejects_ambiguous_surname_only_match():
    match = match_instructor("Doe", ["Jane Doe", "John Doe"])
    assert match.status == "ambiguous"
    assert not match.is_match
