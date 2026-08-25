from __future__ import annotations

from course_planner.scheduling import group_sections, parse_minutes
from course_planner.scrapers.soc_scraper import (
    _parse_course_titles,
    _parse_section_rows,
    _parse_time,
)
from course_planner.utils import CourseOption, Section


def test_parses_current_ucla_template_course_titles():
    html = """
    <template>
      <div class="row-fluid class-title" id="COMSCI0031">
        <h2><button id="COMSCI0031-title">31 - Introduction to Computer Science I</button></h2>
      </div>
      <script>
        Iwe_ClassSearch_SearchResults.AddToCourseData("COMSCI0031",{"Term":"26F","SubjectAreaCode":"COM SCI","CatalogNumber":"0031    ","Path":"COMSCI0031"});
      </script>
    </template>
    """

    courses = _parse_course_titles(html, "COM SCI")

    assert len(courses) == 1
    assert courses[0]["course_code"] == "COM SCI 31"
    assert courses[0]["title"] == "Introduction to Computer Science I"


def test_parses_current_ucla_section_shape():
    html = """
    <div class="row-fluid data_row primary-row class-info" id="187093200_COMSCI0031">
      <div class="sectionColumn"><p><a>Lec 1</a></p></div>
      <div class="statusColumn"><p>Open<br>153 of 237 Enrolled<br>84 Spots Left</p></div>
      <div class="waitlistColumn"><p>1 of 40 Taken</p></div>
      <div class="dayColumn"><button>MW</button></div>
      <div class="timeColumn"><p class="mobile">MW</p><p>12pm-1:50pm</p></div>
      <div class="locationColumn"><p>Engineering VI</p></div>
      <div class="unitsColumn"><p>4.0</p></div>
      <div class="instructorColumn"><p>Smallberg, D.A.</p></div>
    </div>
    """

    sections = _parse_section_rows(html)

    assert sections == [
        {
            "section_id": "Lec 1",
            "parent_section_id": "",
            "days": "MW",
            "start_time": "12pm",
            "end_time": "1:50pm",
            "location": "Engineering VI",
            "instructor": "Smallberg, D.A.",
            "enrolled": 153,
            "capacity": 237,
            "waitlist": 1,
            "waitlist_capacity": 40,
            "format": "in-person",
            "section_type": "lecture",
            "units": 4.0,
            "_path": "187093200_COMSCI0031",
        }
    ]


def test_noon_times_and_parent_section_pairing():
    assert _parse_time("MW 12pm - 1:50pm") == ("12pm", "1:50pm")
    assert parse_minutes("12pm") == 12 * 60
    assert parse_minutes("12am") == 0

    course = CourseOption(
        course_code="COM SCI 31",
        title="Introduction to Computer Science I",
        units=4,
        sections=[
            Section("Lec 1", "MW", "12pm", "1:50pm", "", "Professor"),
            Section("Lec 2", "MW", "4pm", "5:50pm", "", "Professor"),
            Section(
                "Dis 1A",
                "F",
                "10am",
                "11:50am",
                "",
                "TA",
                parent_section_id="Lec 1",
                section_type="discussion",
            ),
            Section(
                "Dis 2A",
                "F",
                "2pm",
                "3:50pm",
                "",
                "TA",
                parent_section_id="Lec 2",
                section_type="discussion",
            ),
        ],
    )

    assert [
        [section.section_id for section in pair] for pair in group_sections(course)
    ] == [
        ["Lec 1", "Dis 1A"],
        ["Lec 2", "Dis 2A"],
    ]
