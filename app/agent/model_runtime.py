"""Outer-agent model construction and context capability configuration.

This module is locally written; it contains no copied or adapted donor code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.agent.context import ModelContextPolicy, TokenCounter, conservative_token_counter

DEFAULT_OUTER_MODEL = "gpt-5.3-codex"
OUTER_MODEL_ENV = "OUTER_AGENT_MODEL"


@dataclass(frozen=True)
class ModelRuntime:
    """Bundle model invocation with its validated context policy.

    Args:
        model: LangChain-compatible chat model.
        context_policy: Provider/model context limits used before invocation.
        token_counter: Counter for complete outgoing message requests.

    Returns:
        Immutable runtime configuration for graph composition.
    """

    model: Any
    context_policy: ModelContextPolicy = ModelContextPolicy()
    token_counter: TokenCounter = conservative_token_counter


def resolve_token_counter(model: Any) -> TokenCounter:
    """Select model-aware message counting when the model exposes it.

    Args:
        model: Chat model that may provide ``get_num_tokens_from_messages``.

    Returns:
        Model-aware counter or explicit conservative portable fallback.
    """
    model_counter = getattr(model, "get_num_tokens_from_messages", None)
    if callable(model_counter):
        return lambda messages: int(model_counter(list(messages)))
    return conservative_token_counter


def create_default_model_runtime(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0,
) -> ModelRuntime:
    """Create default OpenAI-compatible LangChain runtime.

    Args:
        model: Optional model name override. Defaults to OUTER_MODEL_ENV or DEFAULT_OUTER_MODEL.
        base_url: Optional OpenAI-compatible base URL (e.g. OpenRouter, DeepSeek, vLLM).
        api_key: Optional explicit API key.
        temperature: Model sampling temperature (default 0.0).

    Returns:
        Runtime using configured model and provider-neutral context preparation.
    """
    from langchain_openai import ChatOpenAI

    model_name = model or os.getenv(OUTER_MODEL_ENV, DEFAULT_OUTER_MODEL)
    effective_base_url = base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")
    if effective_base_url:
        effective_base_url = str(effective_base_url).strip()
        if not effective_base_url or effective_base_url.lower() in ("none", "null"):
            effective_base_url = None

    kwargs: dict[str, Any] = {
        "model": model_name,
        "temperature": temperature,
    }
    if effective_base_url:
        kwargs["base_url"] = effective_base_url
    if api_key:
        kwargs["api_key"] = api_key

    chat_model = ChatOpenAI(**kwargs)
    return ModelRuntime(model=chat_model, token_counter=resolve_token_counter(chat_model))
