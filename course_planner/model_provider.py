"""OpenAI and Anthropic transient BYOK model construction.

The API accepts an explicit provider configuration for one request. There is
deliberately no environment-owned credential fallback or session credential.
"""

from __future__ import annotations

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from course_planner.planner_models import ModelConfig


def create_chat_model(
    *,
    config: ModelConfig | None = None,
) -> BaseChatModel:
    """Create an OpenAI-compatible or native Anthropic chat model.

    ``config`` is mandatory so a process environment can never silently select
    a server-owned key or model. The key is not returned by planner responses.
    """
    if config is None:
        raise RuntimeError("An explicit transient model config is required")
    supplied_key = config.api_key.get_secret_value()
    if config.provider != "openai_compatible" and not supplied_key:
        raise RuntimeError("A transient model api_key is required for enhancement")
    common = {
        "model": config.model,
        "base_url": config.base_url,
        # Local OpenAI-compatible servers commonly do not authenticate, while
        # the OpenAI client still requires a non-empty constructor value.
        "api_key": supplied_key or "local-model",
        "temperature": config.temperature,
        "timeout": 45,
        "max_retries": 2,
    }
    if config.provider == "anthropic":
        return ChatAnthropic(max_tokens=2_048, **common)
    return ChatOpenAI(**common)
