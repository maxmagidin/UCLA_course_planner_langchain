"""ASI:One model configuration for LangChain.

ASI:One is OpenAI-compatible.  No custom model adapter is needed; only the
base URL and model name change.  Planner mode is intentionally opt-in because
this application already has its own deterministic LangGraph orchestration.
"""

from __future__ import annotations

import os
from uuid import uuid4

from langchain_openai import ChatOpenAI


def create_asi_model(*, model: str | None = None, session_id: str | None = None) -> ChatOpenAI:
    """Return an ASI:One-backed LangChain chat model."""
    api_key = os.getenv("ASI_ONE_API_KEY") or os.getenv("ASI1_API_KEY")
    if not api_key:
        raise RuntimeError("Set ASI_ONE_API_KEY before using the ASI:One model")

    kwargs: dict[str, object] = {
        "model": model or os.getenv("ASI_ONE_MODEL", "asi1"),
        "base_url": os.getenv("ASI_ONE_BASE_URL", "https://api.asi1.ai/v1"),
        "api_key": api_key,
        "temperature": float(os.getenv("ASI_ONE_TEMPERATURE", "0")),
    }
    if os.getenv("ASI_ONE_ENABLE_THINKING", "false").lower() == "true":
        kwargs["extra_body"] = {
            "enable_thinking": True,
            "thinking_budget": int(os.getenv("ASI_ONE_THINKING_BUDGET", "1024")),
        }
    if session_id:
        kwargs["default_headers"] = {"x-session-id": session_id}
    return ChatOpenAI(**kwargs)


def new_session_id() -> str:
    return str(uuid4())
