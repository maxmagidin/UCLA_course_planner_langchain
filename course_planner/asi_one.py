"""Backward-compatible import path for the old ASI:One integration."""

from course_planner.model_provider import create_chat_model, new_session_id


create_asi_model = create_chat_model
