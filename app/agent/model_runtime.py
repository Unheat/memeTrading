"""Outer-agent model construction and context capability configuration.

This module is locally written; it contains no copied or adapted donor code.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
import litellm

from app.agent.context import ModelContextPolicy, TokenCounter, conservative_token_counter
from app.config import ModelEndpointConfig, load_config

logger = logging.getLogger(__name__)

DEFAULT_OUTER_MODEL = "gpt-5.3-codex"
OUTER_MODEL_ENV = "OUTER_AGENT_MODEL"


class UniversalChatModel(BaseChatModel):
    """Universal multi-provider Chat Model supporting automatic endpoint fallbacks via LiteLLM."""

    model: str = DEFAULT_OUTER_MODEL
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = 0.2
    endpoints: List[dict] = []

    @property
    def _llm_type(self) -> str:
        return "universal-litellm-chat"

    def bind_tools(
        self,
        tools: Sequence[Union[Dict[str, Any], type, BaseTool]],
        **kwargs: Any,
    ) -> Any:
        """Bind LangChain tools converted to universal function-calling schema."""
        formatted_tools = [convert_to_openai_tool(t) for t in tools]
        return self.bind(tools=formatted_tools, **kwargs)

    def with_structured_output(
        self,
        schema: Any,
        **kwargs: Any,
    ) -> Any:
        """Return a runnable that invokes the model and parses structured output into schema."""
        from langchain_core.runnables import RunnableLambda

        def _invoke_structured(messages: Any) -> Any:
            schema_json = schema.model_json_schema() if hasattr(schema, "model_json_schema") else (schema.schema() if hasattr(schema, "schema") else {})
            instruction = f"\nYou MUST respond strictly in valid JSON conforming to this JSON schema:\n{json.dumps(schema_json, indent=2)}\nDo not include any commentary, prose, or markdown outside the single JSON object."

            if isinstance(messages, list):
                msgs = list(messages)
                last = msgs[-1]
                if isinstance(last, HumanMessage):
                    msgs[-1] = HumanMessage(content=str(last.content) + instruction)
                elif isinstance(last, SystemMessage):
                    msgs[-1] = SystemMessage(content=str(last.content) + instruction)
                else:
                    msgs.append(HumanMessage(content=instruction))
            else:
                msgs = [HumanMessage(content=str(messages) + instruction)]

            bound = self.bind(response_format={"type": "json_object"})
            res = bound.invoke(msgs)
            raw = getattr(res, "content", "")
            if isinstance(raw, str):
                cleaned = raw.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                elif cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                raw = cleaned.strip()
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
            if hasattr(schema, "model_validate"):
                return schema.model_validate(data)
            if hasattr(schema, "parse_obj"):
                return schema.parse_obj(data)
            return data

        return RunnableLambda(_invoke_structured)

    def _convert_messages(self, messages: List[BaseMessage]) -> List[dict]:
        """Convert LangChain message objects to LiteLLM message payloads."""
        converted = []
        for m in messages:
            if isinstance(m, SystemMessage):
                converted.append({"role": "system", "content": str(m.content)})
            elif isinstance(m, HumanMessage):
                converted.append({"role": "user", "content": str(m.content)})
            elif isinstance(m, ToolMessage):
                converted.append({
                    "role": "tool",
                    "content": str(m.content),
                    "tool_call_id": m.tool_call_id,
                })
            elif isinstance(m, AIMessage):
                msg_dict: dict[str, Any] = {"role": "assistant", "content": str(m.content or "")}
                if m.tool_calls:
                    msg_dict["tool_calls"] = [
                        {
                            "id": tc.get("id"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name"),
                                "arguments": json.dumps(tc.get("args")) if isinstance(tc.get("args"), dict) else str(tc.get("args")),
                            },
                        }
                        for tc in m.tool_calls
                    ]
                converted.append(msg_dict)
            else:
                converted.append({"role": "user", "content": str(m.content)})
        return converted

    def get_num_tokens_from_messages(self, messages: List[BaseMessage]) -> int:
        """Calculate model-aware token count via LiteLLM with conservative fallback."""
        converted = self._convert_messages(messages)
        try:
            return int(litellm.token_counter(model=self.model, messages=converted))
        except Exception:
            return conservative_token_counter(messages)

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate chat completion trying endpoints in fallback priority order."""
        litellm_messages = self._convert_messages(messages)
        tools = kwargs.get("tools")
        response_format = kwargs.get("response_format")
        temp = kwargs.get("temperature", self.temperature)

        target_endpoints = self.endpoints if self.endpoints else [{
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "temperature": temp,
        }]

        last_error = None
        for idx, ep in enumerate(target_endpoints):
            m_name = ep.get("model") or self.model
            b_url = ep.get("base_url") or self.base_url
            a_key = ep.get("api_key") or self.api_key
            key_env = ep.get("api_key_env")
            t_val = ep.get("temperature") if ep.get("temperature") is not None else temp

            if key_env and not a_key:
                last_error = ValueError(
                    f"Missing credential {key_env!r} for model {m_name!r}. "
                    "Add it to .env or remove this endpoint from config.yaml."
                )
                logger.warning("Skipping LLM endpoint #%d: %s", idx + 1, last_error)
                continue

            call_kwargs: dict[str, Any] = {
                "model": m_name,
                "messages": litellm_messages,
                "temperature": t_val,
            }
            if b_url:
                call_kwargs["api_base"] = b_url
            if a_key:
                call_kwargs["api_key"] = a_key
            if tools:
                call_kwargs["tools"] = tools
            if response_format:
                call_kwargs["response_format"] = response_format

            try:
                res = litellm.completion(**call_kwargs)
                choice = res.choices[0]
                content = choice.message.content or ""
                tool_calls_list = []
                if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                    for tc in choice.message.tool_calls:
                        func = getattr(tc, "function", None)
                        fn_name = getattr(func, "name", "") if func else ""
                        fn_args_raw = getattr(func, "arguments", "{}") if func else "{}"
                        try:
                            fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else dict(fn_args_raw)
                        except Exception:
                            fn_args = {"raw": fn_args_raw}
                        tool_calls_list.append({
                            "name": fn_name,
                            "args": fn_args,
                            "id": getattr(tc, "id", ""),
                            "type": "tool_call",
                        })
                ai_msg = AIMessage(content=content, tool_calls=tool_calls_list)
                return ChatResult(generations=[ChatGeneration(message=ai_msg)])
            except Exception as exc:
                logger.warning("LLM endpoint #%d (%s @ %s) failed: %s; trying next fallback...", idx + 1, m_name, b_url or "default", exc)
                last_error = exc
                continue

        raise RuntimeError(f"All configured model endpoints failed. Last error: {last_error}")


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
    temperature: float = 0.2,
    endpoints: Sequence[ModelEndpointConfig] | None = None,
) -> ModelRuntime:
    """Create default UniversalChatModel runtime with multi-provider fallback.

    Args:
        model: Optional model name override.
        base_url: Optional OpenAI-compatible base URL.
        api_key: Optional explicit API key.
        temperature: Model sampling temperature (default 0.2).
        endpoints: Optional sequence of ModelEndpointConfig for fallbacks.

    Returns:
        Runtime using configured model and provider-neutral context preparation.
    """
    if endpoints:
        ep_dicts = [
            {
                "model": ep.model,
                "base_url": ep.base_url,
                "api_key": ep.resolve_api_key() or api_key,
                "api_key_env": ep.api_key_env,
                "temperature": ep.temperature if ep.temperature is not None else temperature,
            }
            for ep in endpoints
        ]
        primary_model = ep_dicts[0]["model"]
        primary_base = ep_dicts[0]["base_url"]
    else:
        primary_model = model or DEFAULT_OUTER_MODEL
        primary_base = base_url
        ep_dicts = [{
            "model": primary_model,
            "base_url": primary_base,
            "api_key": api_key,
            "temperature": temperature,
        }]

    chat_model = UniversalChatModel(
        model=primary_model,
        base_url=primary_base,
        api_key=api_key,
        temperature=temperature,
        endpoints=ep_dicts,
    )
    return ModelRuntime(model=chat_model, token_counter=resolve_token_counter(chat_model))
