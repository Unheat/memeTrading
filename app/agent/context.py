"""Adaptive, pair-safe context preparation for agent model calls."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

DEFAULT_CONTEXT_WINDOW_TOKENS = 1_000_000
DEFAULT_RESERVED_OUTPUT_TOKENS = 32_000
DEFAULT_SAFETY_MARGIN_TOKENS = 32_000
DEFAULT_COMPACT_THRESHOLD_TOKENS = 200_000
DEFAULT_TOOL_RESULT_MAX_TOKENS = 8_000
DEFAULT_LATEST_UNITS_TO_PRESERVE = 3
DEFAULT_COMPACTION_MODE = "application"
SUPPORTED_COMPACTION_MODES = frozenset({"application", "provider_native", "hybrid"})
ESTIMATED_CHARACTERS_PER_TOKEN = 4
TOOL_DIGEST_LENGTH = 16

TokenCounter = Callable[[Sequence[BaseMessage]], int]


@dataclass(frozen=True)
class ModelContextPolicy:
    """Define immutable local context limits and retention behavior.

    Args:
        context_window_tokens: Provider-declared total context capacity.
        reserved_output_tokens: Capacity reserved for model output and tool calls.
        safety_margin_tokens: Additional capacity withheld from input.
        compact_threshold_tokens: Input size that activates pruning and compaction.
        tool_result_max_tokens: Minimum old tool-body size eligible for replacement.
        latest_units_to_preserve: Number of newest conversational units never dropped.
        compaction_mode: Application, provider-native, or hybrid context handling.

    Returns:
        Immutable policy consumed by :func:`prepare_context`.
    """

    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS
    safety_margin_tokens: int = DEFAULT_SAFETY_MARGIN_TOKENS
    compact_threshold_tokens: int = DEFAULT_COMPACT_THRESHOLD_TOKENS
    tool_result_max_tokens: int = DEFAULT_TOOL_RESULT_MAX_TOKENS
    latest_units_to_preserve: int = DEFAULT_LATEST_UNITS_TO_PRESERVE
    compaction_mode: str = DEFAULT_COMPACTION_MODE

    @property
    def max_input_tokens(self) -> int:
        """Return context capacity available to model input.

        Args:
            self: Validated policy instance.

        Returns:
            Context window after output reserve and safety margin.
        """
        return self.context_window_tokens - self.reserved_output_tokens - self.safety_margin_tokens

    def __post_init__(self) -> None:
        """Validate policy values after construction.

        Args:
            self: Constructed policy instance.

        Returns:
            None. Raises ``ValueError`` for inconsistent limits.
        """
        if self.context_window_tokens <= 0:
            raise ValueError("context_window_tokens must be positive")
        if self.reserved_output_tokens < 0 or self.safety_margin_tokens < 0:
            raise ValueError("reserved_output_tokens and safety_margin_tokens cannot be negative")
        if self.max_input_tokens <= 0:
            raise ValueError("output reserve and safety margin must leave positive input capacity")
        if not 0 < self.compact_threshold_tokens <= self.max_input_tokens:
            raise ValueError("compact_threshold_tokens must fit within input capacity")
        if self.tool_result_max_tokens <= 0:
            raise ValueError("tool_result_max_tokens must be positive")
        if self.latest_units_to_preserve < 0:
            raise ValueError("latest_units_to_preserve cannot be negative")
        if self.compaction_mode not in SUPPORTED_COMPACTION_MODES:
            raise ValueError(f"unsupported compaction_mode: {self.compaction_mode}")


@dataclass(frozen=True)
class PreparedContext:
    """Describe immutable output and token accounting from context preparation.

    Args:
        messages: Pair-safe messages selected for the next model call.
        original_tokens: Estimated size before preparation.
        prepared_tokens: Estimated size after preparation.
        compacted: Whether any tool body or conversational unit changed.

    Returns:
        Immutable context preparation result.
    """

    messages: tuple[BaseMessage, ...]
    original_tokens: int
    prepared_tokens: int
    compacted: bool


def conservative_token_counter(messages: Sequence[BaseMessage]) -> int:
    """Estimate tokens from message content plus tool-call names, IDs, and arguments.

    Args:
        messages: Messages whose model-visible payloads should be counted.

    Returns:
        Conservative character-based token estimate, rounded upward.
    """
    characters = 0
    for message in messages:
        characters += len(_stable_text(message.content))
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls:
                characters += len(str(tool_call.get("id", "")))
                characters += len(str(tool_call.get("name", "")))
                characters += len(_stable_text(tool_call.get("args", {})))
        if isinstance(message, ToolMessage):
            characters += len(message.tool_call_id)
            characters += len(message.name or "")
    return math.ceil(characters / ESTIMATED_CHARACTERS_PER_TOKEN) if characters else 0


def _stable_text(value: Any) -> str:
    """Serialize arbitrary message payloads deterministically for counting and hashing.

    Args:
        value: Message content or tool arguments to serialize.

    Returns:
        Stable compact text representation.
    """
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _validate_tool_pairs(messages: Sequence[BaseMessage]) -> None:
    """Validate that each AI tool call has one matching following tool result.

    Args:
        messages: Ordered conversation to validate.

    Returns:
        None. Raises ``ValueError`` when IDs are missing, duplicated, orphaned, or unmatched.
    """
    pending: set[str] = set()
    seen: set[str] = set()
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            if pending:
                raise ValueError("AI tool calls must be resolved before another AI tool-call message")
            call_ids = [str(call.get("id", "")) for call in message.tool_calls]
            if any(not call_id for call_id in call_ids):
                raise ValueError("AI tool calls require non-empty IDs")
            if len(call_ids) != len(set(call_ids)) or seen.intersection(call_ids):
                raise ValueError("AI tool call IDs must be unique")
            pending.update(call_ids)
            seen.update(call_ids)
        elif isinstance(message, ToolMessage):
            call_id = message.tool_call_id
            if call_id not in pending:
                raise ValueError(f"orphaned or duplicate ToolMessage tool_call_id: {call_id}")
            pending.remove(call_id)
        elif pending:
            raise ValueError("all ToolMessages must immediately follow their AI tool-call message")
    if pending:
        raise ValueError(f"unmatched AI tool call IDs: {sorted(pending)}")


def _conversation_units(messages: Sequence[BaseMessage]) -> list[list[BaseMessage]]:
    """Group history into oldest-to-newest units without splitting tool-call pairs.

    Args:
        messages: Validated ordered conversation.

    Returns:
        Units beginning at each human message; any leading messages form one unit.
    """
    units: list[list[BaseMessage]] = []
    for message in messages:
        if isinstance(message, HumanMessage) or not units:
            units.append([message])
        else:
            units[-1].append(message)
    return units


def _pruned_tool_message(message: ToolMessage) -> ToolMessage:
    """Replace a tool body with deterministic metadata while retaining pair identity.

    Args:
        message: Oversized tool result to replace.

    Returns:
        ToolMessage retaining status, name, ID, original size, and content digest.
    """
    body = _stable_text(message.content)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:TOOL_DIGEST_LENGTH]
    metadata = {
        "digest": digest,
        "id": message.tool_call_id,
        "name": message.name,
        "size": len(body.encode("utf-8")),
        "status": getattr(message, "status", None),
    }
    return ToolMessage(
        content=json.dumps(metadata, sort_keys=True, separators=(",", ":")),
        tool_call_id=message.tool_call_id,
        name=message.name,
        status=getattr(message, "status", "success"),
    )


def prepare_context(
    messages: Sequence[BaseMessage],
    policy: ModelContextPolicy | None = None,
    token_counter: TokenCounter = conservative_token_counter,
) -> PreparedContext:
    """Prepare bounded history while preserving complete AI/tool-call pairs.

    Args:
        messages: Ordered model conversation history.
        policy: Optional immutable limits; defaults to ``ModelContextPolicy``.
        token_counter: Injectable whole-history token estimator.

    Returns:
        Immutable prepared context with before/after accounting.
    """
    active_policy = policy or ModelContextPolicy()
    original = tuple(messages)
    _validate_tool_pairs(original)
    if active_policy.compaction_mode == "provider_native":
        raise ValueError("provider_native compaction requires a provider capability adapter")

    original_tokens = token_counter(original)
    if original_tokens < active_policy.compact_threshold_tokens:
        return PreparedContext(original, original_tokens, original_tokens, False)

    system_prefix = [message for message in original if isinstance(message, SystemMessage)]
    history = [message for message in original if not isinstance(message, SystemMessage)]
    units = _conversation_units(history)
    protected_start = max(0, len(units) - active_policy.latest_units_to_preserve)
    changed = False
    for index, unit in enumerate(units[:protected_start]):
        for message_index, message in enumerate(unit):
            if (
                isinstance(message, ToolMessage)
                and token_counter([message]) >= active_policy.tool_result_max_tokens
            ):
                unit[message_index] = _pruned_tool_message(message)
                changed = True

    prepared = [*system_prefix, *(message for unit in units for message in unit)]
    while token_counter(prepared) > active_policy.max_input_tokens and len(units) > active_policy.latest_units_to_preserve:
        units.pop(0)
        prepared = [*system_prefix, *(message for unit in units for message in unit)]
        changed = True

    _validate_tool_pairs(prepared)
    prepared_tokens = token_counter(prepared)
    if prepared_tokens > active_policy.max_input_tokens:
        raise ValueError("latest complete context units exceed model input capacity")
    return PreparedContext(tuple(prepared), original_tokens, prepared_tokens, changed)


def trim_conversation_history(
    messages: Sequence[BaseMessage],
    max_tokens: int = DEFAULT_COMPACT_THRESHOLD_TOKENS,
) -> list[BaseMessage]:
    """Return pair-safe bounded history through the legacy list-based API.

    Args:
        messages: Ordered model conversation history.
        max_tokens: Preparation threshold and hard target for compatibility.

    Returns:
        Prepared messages as a mutable list.
    """
    policy = ModelContextPolicy(
        context_window_tokens=max_tokens + DEFAULT_RESERVED_OUTPUT_TOKENS + DEFAULT_SAFETY_MARGIN_TOKENS,
        compact_threshold_tokens=max_tokens,
    )
    return list(prepare_context(messages, policy=policy).messages)
