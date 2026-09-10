"""Context window management and message trimming."""
from __future__ import annotations

from typing import Sequence
from langchain_core.messages import BaseMessage, trim_messages


def _simple_token_counter(messages: Sequence[BaseMessage]) -> int:
    """Fast character-based token estimator (~4 chars per token)."""
    total_chars = sum(len(str(m.content)) for m in messages)
    return max(1, total_chars // 4)


def trim_conversation_history(
    messages: Sequence[BaseMessage],
    max_tokens: int = 4000,
) -> list[BaseMessage]:
    """Trim ephemeral raw message list using sliding window.

    Leaves recent messages intact while discarding older tool/AI turns.
    Permanent evidence is preserved separately in the dynamic system prompt.
    """
    if not messages:
        return []

    return trim_messages(
        list(messages),
        max_tokens=max_tokens,
        strategy="last",
        token_counter=_simple_token_counter,
        include_system=False,
        start_on="human",
    )
