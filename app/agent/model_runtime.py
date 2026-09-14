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


def create_default_model_runtime() -> ModelRuntime:
    """Create default OpenAI LangChain runtime from environment configuration.

    Args:
        None.

    Returns:
        Runtime using configured model and provider-neutral context preparation.
    """
    from langchain_openai import ChatOpenAI

    model_name = os.getenv(OUTER_MODEL_ENV, DEFAULT_OUTER_MODEL)
    model = ChatOpenAI(model=model_name, temperature=0)
    return ModelRuntime(model=model, token_counter=resolve_token_counter(model))
