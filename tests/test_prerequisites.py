from __future__ import annotations

from course_planner.prerequisites import evaluate_requisites, parse_catalog_requisites
from course_planner.scrapers.catalog_scraper import _page_content, catalog_course_url
from course_planner.terms import parse_ucla_term


def test_parses_relative_and_cross_department_and_groups():
    rule = parse_catalog_requisites(
        "COM SCI M146",
        "Requisites: course 32 or Program in Computing 10C; "
        "Civil and Environmental Engineering 110 or Electrical and Computer "
        "Engineering 131A or Mathematics 170A or 170E or Statistics 100A; "
        "Mathematics 33A. Introduction to data science.",
    )

    assert [group.options for group in rule.groups] == [
        ["COM SCI 32", "PIC 10C"],
        ["C&EE 110", "EC ENGR 131A", "MATH 170A", "MATH 170E", "STATS 100A"],
        ["MATH 33A"],
    ]
    evaluation = evaluate_requisites(
        rule,
        {"PIC 10C", "MATH 170E", "MATH 33A"},
    )
    assert evaluation.status == "met"


def test_unmet_and_corequisite_are_explicit():
    rule = parse_catalog_requisites(
        "PHYSICS 1B",
        "Enforced requisites: course 1A, Mathematics 31B, 32A. "
        "Enforced corequisite: Mathematics 32B. Fluid mechanics.",
    )
    unmet = evaluate_requisites(rule, {"PHYSICS 1A", "MATH 31B"}, {"MATH 32B"})
    eligible = evaluate_requisites(
        rule,
        {"PHYSICS 1A", "MATH 31B", "MATH 32A"},
        {"MATH 32B"},
    )

    assert unmet.status == "unmet"
    assert unmet.missing_groups == [["MATH 32A"]]
    assert eligible.status == "corequisite"
    assert eligible.corequisite_groups == [["MATH 32B"]]


def test_catalog_next_data_parser_and_url():
    document = """<html><script id="__NEXT_DATA__" type="application/json">{
      "props":{"pageProps":{"pageErrors":[],"pageContent":{
        "code":"COM SCI 111","title":"Operating Systems Principles"
      }}}
    }</script></html>"""

    assert _page_content(document)["code"] == "COM SCI 111"
    assert catalog_course_url("COM SCI 111", 2026).endswith(
        "/course/2026/COMSCI111?year=2026"
    )


def test_terms_are_strict_and_map_to_the_academic_catalog():
    assert parse_ucla_term("Fall 2026").soc_code == "26F"
    assert parse_ucla_term("Winter 2027").catalog_year == 2026
    try:
        parse_ucla_term("Autumn 2026")
    except ValueError as exc:
        assert "Fall 2026" in str(exc)
    else:
        raise AssertionError("invalid term silently defaulted to Fall")


def test_grade_threshold_is_unknown_without_grade_evidence():
    rule = parse_catalog_requisites(
        "MATH 32B",
        "Enforced requisites: courses 31B and 32A, with grades of C– or better. Calculus.",
    )

    result = evaluate_requisites(rule, {"MATH 31B", "MATH 32A"})

    assert result.status == "unknown"
    assert "manual verification" in result.summary
