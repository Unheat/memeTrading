"""Tests for outer-agent model runtime configuration and universal LiteLLM fallback."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.context import ModelContextPolicy
from app.agent.model_runtime import (
    ModelRuntime,
    UniversalChatModel,
    create_default_model_runtime,
    resolve_token_counter,
)
from app.config import ModelEndpointConfig


class FakeModel:
    """Offline model marker used to verify runtime composition."""


def test_model_runtime_keeps_injected_model_and_modern_policy() -> None:
    """Verify offline models receive million-token default context policy."""
    model = FakeModel()
    runtime = ModelRuntime(model=model)

    assert runtime.model is model
    assert runtime.context_policy.context_window_tokens == 1_000_000
    assert runtime.context_policy.compact_threshold_tokens == 200_000


def test_resolve_token_counter_prefers_model_capability() -> None:
    """Verify runtime uses provider-aware message counting when available."""
    class CountingModel:
        """Expose deterministic model-aware counting for test composition."""

        def get_num_tokens_from_messages(self, messages):
            """Return count proving complete message list reached model hook."""
            return len(messages) * 11

    counter = resolve_token_counter(CountingModel())
    assert counter([]) == 0
    assert counter([object(), object()]) == 22


def test_provider_native_mode_requires_capability_adapter() -> None:
    """Verify portable preparation rejects unsupported native-only compaction."""
    from app.agent.context import prepare_context

    policy = ModelContextPolicy(compaction_mode="provider_native")
    with pytest.raises(ValueError, match="provider capability adapter"):
        prepare_context([], policy=policy)


def test_universal_chat_model_message_conversion():
    """Verify UniversalChatModel converts LangChain message types to LiteLLM payload."""
    model = UniversalChatModel(model="gpt-4o")
    messages = [
        SystemMessage(content="System instructions"),
        HumanMessage(content="User query"),
        AIMessage(content="Assistant response", tool_calls=[{"name": "lookup", "args": {"ticker": "MU"}, "id": "call-1"}]),
        ToolMessage(content="Tool result", tool_call_id="call-1"),
    ]
    converted = model._convert_messages(messages)
    assert len(converted) == 4
    assert converted[0] == {"role": "system", "content": "System instructions"}
    assert converted[1] == {"role": "user", "content": "User query"}
    assert converted[2]["role"] == "assistant"
    assert converted[2]["tool_calls"][0]["function"]["name"] == "lookup"
    assert converted[3] == {"role": "tool", "content": "Tool result", "tool_call_id": "call-1"}


def test_universal_chat_model_automatic_fallback():
    """Verify UniversalChatModel tries primary endpoint and falls back on error."""
    attempts = []

    def fake_completion(**kwargs):
        attempts.append(kwargs["model"])
        if kwargs["model"] == "primary-model":
            raise ConnectionError("Primary model offline")
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Fallback response ok",
                        tool_calls=[],
                    )
                )
            ]
        )

    model = UniversalChatModel(
        endpoints=[
            {"model": "primary-model", "base_url": "http://localhost:20128/v1"},
            {"model": "fallback-model", "base_url": "https://openrouter.ai/api/v1"},
        ]
    )

    with patch("litellm.completion", side_effect=fake_completion):
        res = model.invoke([HumanMessage(content="Hello")])
        assert res.content == "Fallback response ok"
        assert attempts == ["primary-model", "fallback-model"]


def test_universal_chat_model_skips_missing_named_credential():
    """Verify missing endpoint credentials produce one actionable local error."""
    model = UniversalChatModel(
        endpoints=[
            {
                "model": "openai/stack",
                "base_url": "http://localhost:20128/v1",
                "api_key": None,
                "api_key_env": "NINEROUTER_API_KEY",
            }
        ]
    )

    with pytest.raises(RuntimeError, match="NINEROUTER_API_KEY"):
        model.invoke([HumanMessage(content="Hello")])


def test_create_default_model_runtime_with_endpoints(monkeypatch):
    """Verify runtime resolves a distinct secret for each fallback endpoint."""
    monkeypatch.setenv("NINEROUTER_API_KEY", "nine-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deep-secret")
    endpoints = [
        ModelEndpointConfig(
            model="openai/gpt-4o",
            base_url="http://localhost:20128/v1",
            api_key_env="NINEROUTER_API_KEY",
        ),
        ModelEndpointConfig(
            model="deepseek/deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key_env="DEEPSEEK_API_KEY",
        ),
    ]
    runtime = create_default_model_runtime(endpoints=endpoints)
    assert isinstance(runtime.model, UniversalChatModel)
    assert len(runtime.model.endpoints) == 2
    assert runtime.model.endpoints[0]["model"] == "openai/gpt-4o"
    assert runtime.model.endpoints[0]["api_key"] == "nine-secret"
    assert runtime.model.endpoints[1]["model"] == "deepseek/deepseek-chat"
    assert runtime.model.endpoints[1]["api_key"] == "deep-secret"
