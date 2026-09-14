"""Tests for outer-agent model runtime configuration."""
import pytest

from app.agent.context import ModelContextPolicy
from app.agent.model_runtime import ModelRuntime, resolve_token_counter


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
