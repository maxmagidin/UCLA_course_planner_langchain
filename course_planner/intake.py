"""Structured conversational intake powered by ASI:One."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from course_planner.asi_one import create_asi_model
from course_planner.planner_models import StudentProfile


INTAKE_PROMPT = """You are the intake assistant for a UCLA course planner.
Extract a complete student profile from the conversation. Ask for missing
required fields in plain language before returning a profile. Required fields:
name, major, year, GPA, units completed, enrollment pass, pass-open time, term,
and preferred unit range. Preserve hard constraints exactly. Never invent a
course, date, GPA, or term. Use the structured schema supplied by the caller.
"""


def extract_profile(conversation: list[dict[str, str]]) -> StudentProfile:
    """Extract a validated profile from a conversation transcript."""
    model = create_asi_model().with_structured_output(StudentProfile)
    messages = [SystemMessage(content=INTAKE_PROMPT)] + [
        HumanMessage(content=f"{item['role']}: {item['content']}") for item in conversation
    ]
    return model.invoke(messages)
