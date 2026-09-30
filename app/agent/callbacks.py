"""Investigation event tracking and real-time execution callback handler.

Provides structured, serializable event streams capturing model thinking, tool
invocations, tool receipts, stage transitions, and verification gates.
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult, LLMResult

logger = logging.getLogger(__name__)


def _clean_for_json(val: Any, max_str_len: int = 1200) -> Any:
    """Recursively convert LangChain messages and non-primitives into clean JSON-serializable primitives."""
    if val is None or isinstance(val, (int, float, bool)):
        return val
    if isinstance(val, str):
        return val[:max_str_len]
    if hasattr(val, "content"):
        content = getattr(val, "content", "")
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
                return _clean_for_json(parsed, max_str_len=max_str_len)
            except Exception:
                return str(content)[:max_str_len]
        return _clean_for_json(content, max_str_len=max_str_len)
    if isinstance(val, Mapping):
        return {str(k): _clean_for_json(v, max_str_len=max_str_len) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [_clean_for_json(item, max_str_len=max_str_len) for item in val]
    return str(val)[:max_str_len]


class InvestigationCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler capturing live execution events for UI streaming."""

    def __init__(
        self,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        case_id: Optional[str] = None,
    ) -> None:
        """Initialize the callback handler with an optional event dispatch listener.

        Args:
            event_callback: Callable receiving serialized InvestigationEvent dicts.
            case_id: Optional case identifier for event correlation.
        """
        super().__init__()
        self.event_callback = event_callback
        self.case_id = case_id
        self._lock = threading.Lock()
        self._seq = 0
        self._events: List[Dict[str, Any]] = []
        self._current_stage = "initializing"

    @property
    def events(self) -> List[Dict[str, Any]]:
        """Return a snapshot of all events recorded by this handler."""
        with self._lock:
            return list(self._events)

    def set_stage(self, stage: str) -> None:
        """Update active pipeline execution stage."""
        with self._lock:
            self._current_stage = stage

    def emit(
        self,
        event_type: str,
        title: str,
        payload: Optional[Dict[str, Any]] = None,
        stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record and broadcast a structured execution event.

        Args:
            event_type: Event category ('stage', 'llm_start', 'llm_thinking',
                'llm_response', 'tool_call', 'tool_result', 'gate', 'log').
            title: Human-readable summary of the event.
            payload: Additional structured data (arguments, outputs, metrics).
            stage: Optional stage override; defaults to active stage.

        Returns:
            The recorded event dictionary.
        """
        clean_payload = _clean_for_json(payload or {}, max_str_len=1200)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._seq += 1
            seq = self._seq
            active_stage = stage or self._current_stage

            event = {
                "seq": seq,
                "case_id": self.case_id,
                "timestamp": now,
                "event_type": event_type,
                "stage": active_stage,
                "title": title,
                "payload": clean_payload,
            }
            self._events.append(event)

        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception as exc:
                logger.debug("event_callback dispatch failed: %s", exc)

        return event

    def emit_stage(self, stage: str, title: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Emit a pipeline stage transition milestone."""
        self.set_stage(stage)
        return self.emit(event_type="stage", title=title, payload=payload, stage=stage)

    def emit_log(self, message: str, level: str = "INFO") -> Dict[str, Any]:
        """Emit an informational log message event."""
        return self.emit(
            event_type="log",
            title=message,
            payload={"message": message, "level": level},
        )

    # --------------------------------------------------------------------------
    # LangChain BaseCallbackHandler Hooks
    # --------------------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Handle LLM invocation initiation."""
        model_name = (metadata or {}).get("model") or (serialized or {}).get("name") or "model"
        preview = ""
        if prompts and isinstance(prompts[0], str):
            preview = prompts[0][:250]

        self.emit(
            event_type="llm_start",
            title=f"Model Query ({model_name})",
            payload={
                "model": model_name,
                "prompt_preview": preview,
                "run_id": str(run_id),
            },
        )

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Handle chat model invocation initiation."""
        model_name = (metadata or {}).get("model") or (serialized or {}).get("name") or "chat_model"
        last_msg = ""
        msg_count = 0
        if messages and messages[0]:
            msg_count = len(messages[0])
            last_msg = str(getattr(messages[0][-1], "content", ""))[:250]

        self.emit(
            event_type="llm_start",
            title=f"Chat Model Turn ({model_name})",
            payload={
                "model": model_name,
                "message_count": msg_count,
                "last_message_preview": last_msg,
                "run_id": str(run_id),
            },
        )

    def on_llm_end(
        self,
        response: Union[LLMResult, ChatResult],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Handle LLM invocation completion, extracting thinking and tool calls."""
        generations = getattr(response, "generations", [])
        if not generations or not generations[0]:
            return

        first_gen = generations[0]
        if isinstance(first_gen, list):
            first_gen = first_gen[0] if first_gen else None
        if not first_gen:
            return

        message = getattr(first_gen, "message", None)
        text = getattr(first_gen, "text", "") or (getattr(message, "content", "") if message else "") or ""

        # Extract model thinking / reasoning if present
        extra = getattr(message, "additional_kwargs", {}) or {}
        reasoning = extra.get("reasoning_content") or ""
        if reasoning:
            self.emit(
                event_type="llm_thinking",
                title="Model Reasoning Trace",
                payload={
                    "thinking": reasoning,
                    "run_id": str(run_id),
                },
            )

        # Inspect tool calls generated in this turn
        tool_calls = getattr(message, "tool_calls", None) or []
        call_names = [c.get("name") for c in tool_calls if isinstance(c, dict) and c.get("name")]

        title = f"Model Decision: {len(tool_calls)} Tool Call(s)" if tool_calls else "Model Generation"
        self.emit(
            event_type="llm_response",
            title=title,
            payload={
                "content_preview": text[:600] if text else "",
                "tool_calls": call_names,
                "tool_calls_count": len(tool_calls),
                "run_id": str(run_id),
            },
        )

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        inputs: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Handle tool execution initiation."""
        tool_name = (serialized or {}).get("name") or "tool"
        args_payload: Any = inputs or input_str
        if isinstance(args_payload, str):
            try:
                args_payload = json.loads(args_payload)
            except Exception:
                pass

        clean_inputs = _clean_for_json(args_payload, max_str_len=500)
        target_ticker = ""
        if isinstance(clean_inputs, dict):
            target_ticker = clean_inputs.get("ticker") or clean_inputs.get("symbol") or ""

        ticker_tag = f" (${target_ticker.upper()})" if target_ticker else ""
        self.emit(
            event_type="tool_call",
            title=f"Calling {tool_name}{ticker_tag}",
            payload={
                "tool": tool_name,
                "ticker": target_ticker,
                "inputs": clean_inputs,
                "run_id": str(run_id),
            },
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Handle successful tool execution completion."""
        raw_val = output.content if hasattr(output, "content") else output
        if isinstance(raw_val, str):
            clean_text = raw_val.strip()
            try:
                parsed_json = json.loads(clean_text)
                preview = json.dumps(parsed_json, indent=2)[:600]
            except Exception:
                preview = clean_text[:600]
        elif isinstance(raw_val, Mapping):
            preview = json.dumps(dict(raw_val), indent=2, default=str)[:600]
        else:
            preview = str(raw_val)[:600]

        self.emit(
            event_type="tool_result",
            title="Tool Output Received",
            payload={
                "status": "ok",
                "output_preview": preview,
                "run_id": str(run_id),
            },
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Handle tool execution failure."""
        self.emit(
            event_type="tool_result",
            title=f"Tool Error: {type(error).__name__}",
            payload={
                "status": "error",
                "error": str(error),
                "run_id": str(run_id),
            },
        )
