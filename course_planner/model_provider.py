"""Provider-neutral LangChain model factory.

The planner only requires an OpenAI-compatible chat-completions endpoint. That
means users can supply their own API key, base URL, and model without changing
the graph or tools. ASI:One remains available as an optional preset.
"""

from __future__ import annotations

from uuid import uuid4

from langchain_openai import ChatOpenAI

from course_planner.planner_models import ModelConfig


def create_chat_model(
    *,
    config: ModelConfig | None = None,
    model: str | None = None,
    session_id: str | None = None,
) -> ChatOpenAI:
    """Create a LangChain chat model from environment configuration.

    Supported providers are ``openai_compatible`` (the default), ``openai``,
    and ``asi_one``. For any OpenAI-compatible service, set:

    ``MODEL_API_KEY``, ``MODEL_BASE_URL``, and ``MODEL_NAME``.
    """
    config = config or ModelConfig.from_environment()
    provider = config.provider.lower().strip()
    if provider not in {"openai_compatible", "openai", "asi_one", "asi"}:
        raise ValueError(
            f"Unsupported MODEL_PROVIDER={provider!r}. Use openai_compatible, openai, or asi_one."
        )

    if provider in {"asi_one", "asi"}:
        base_url = config.base_url
        model_name = model or config.model
    else:
        base_url = config.base_url
        model_name = model or config.model

    api_key = config.api_key.get_secret_value()
    if not api_key:
        raise RuntimeError(
            "Set MODEL_API_KEY (and usually MODEL_BASE_URL and MODEL_NAME) before using the chat model"
        )

    kwargs: dict[str, object] = {
        "model": model_name,
        "base_url": base_url,
        "api_key": api_key,
        "temperature": config.temperature,
    }

    # ASI:One-specific planner/session controls are opt-in and never sent to
    # arbitrary providers, where unknown request fields may be rejected.
    if provider in {"asi_one", "asi"}:
        if session_id:
            kwargs["default_headers"] = {"x-session-id": session_id}

    return ChatOpenAI(**kwargs)


def new_session_id() -> str:
    return str(uuid4())
