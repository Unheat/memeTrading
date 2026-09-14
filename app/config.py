"""User-facing configuration loader for Meme Market Forensic Research Agent.

Loads settings from config.yaml with environment variable overrides and validation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_CHARACTER_PAIRS = frozenset({"peter_stewie", "rick_morty"})
DEFAULT_CONFIG_PATH = Path("config.yaml")


@dataclass(frozen=True)
class LLMConfig:
    """User-configurable LLM settings for the research agent."""

    model: str = "gpt-5.3-codex"
    base_url: str | None = None  # None uses official OpenAI; set for OpenRouter, DeepSeek, etc.
    temperature: float = 0.0


@dataclass(frozen=True)
class MediaConfig:
    """User-configurable settings for video reel and cited article generation."""

    generate_media: bool = True
    character_pair: str = "peter_stewie"  # Allowed: "peter_stewie" or "rick_morty"

    def __post_init__(self) -> None:
        """Validate character pair against supported cast options."""
        clean = self.character_pair.strip().lower()
        if clean not in SUPPORTED_CHARACTER_PAIRS:
            allowed = ", ".join(sorted(f"'{p}'" for p in SUPPORTED_CHARACTER_PAIRS))
            raise ValueError(f"Unsupported character_pair: '{self.character_pair}'. Must be one of: {allowed}")
        object.__setattr__(self, "character_pair", clean)


@dataclass(frozen=True)
class ResearchConfig:
    """User-configurable execution limits and research defaults."""

    max_tool_calls: int = 15
    max_identical_calls: int = 2
    benchmark_ticker: str = "SPY"
    sec_periods: int = 4
    cases_root: str = "cases"


@dataclass(frozen=True)
class AppConfig:
    """Consolidated application configuration."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    media: MediaConfig = field(default_factory=MediaConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)


def load_config(config_path: Path | str | None = None) -> AppConfig:
    """Load configuration from a YAML file with environment variable overrides.

    Args:
        config_path: Optional path to config.yaml. Defaults to 'config.yaml'.

    Returns:
        Validated AppConfig instance.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    data: dict[str, Any] = {}

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
                if isinstance(content, dict):
                    data = content
        except Exception as exc:
            raise ValueError(f"Failed to parse config file at {path}: {exc}") from exc

    # Parse LLM config with env overrides
    raw_llm = data.get("llm", {}) or {}
    model_name = os.getenv("OUTER_AGENT_MODEL") or raw_llm.get("model") or "gpt-5.3-codex"
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or raw_llm.get("base_url")
    if base_url:
        base_url = str(base_url).strip()
        if not base_url or base_url.lower() in ("none", "null"):
            base_url = None
    temp = float(raw_llm.get("temperature", 0.0))

    llm_cfg = LLMConfig(model=model_name, base_url=base_url, temperature=temp)

    # Parse Media config with env overrides
    raw_media = data.get("media", {}) or {}
    gen_media = raw_media.get("generate_media", True) if "generate_media" in raw_media else True
    char_pair = os.getenv("CHARACTER_PAIR") or raw_media.get("character_pair") or "peter_stewie"
    media_cfg = MediaConfig(generate_media=bool(gen_media), character_pair=str(char_pair))

    # Parse Research config
    raw_res = data.get("research", {}) or {}
    research_cfg = ResearchConfig(
        max_tool_calls=int(raw_res.get("max_tool_calls", 15)),
        max_identical_calls=int(raw_res.get("max_identical_calls", 2)),
        benchmark_ticker=str(raw_res.get("benchmark_ticker", "SPY")),
        sec_periods=int(raw_res.get("sec_periods", 4)),
        cases_root=str(raw_res.get("cases_root", "cases")),
    )

    return AppConfig(llm=llm_cfg, media=media_cfg, research=research_cfg)
