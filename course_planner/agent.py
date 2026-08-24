"""CLI entrypoint for the LangGraph planner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from course_planner.graph import run_planner
from course_planner.planner_models import StudentProfile


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the UCLA course planner graph")
    parser.add_argument("profile", type=Path, help="JSON file containing a StudentProfile")
    args = parser.parse_args()
    profile = StudentProfile.model_validate(json.loads(args.profile.read_text()))
    result = run_planner(profile)
    print(result.report_markdown)
    if result.errors:
        print("\nErrors:")
        for error in result.errors:
            print(f"- {error.node}: {error.message}")


if __name__ == "__main__":
    main()
