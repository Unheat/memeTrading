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
    temperature: float = 0.2  # 0.2 provides strategic lateral thinking & witty dialogue while keeping facts grounded


@dataclass(frozen=True)
class MediaConfig:
    """User-configurable settings for video reel and cited article generation."""

    generate_media: bool = True
    character_pair: str = "peter_stewie"  # Allowed: "peter_stewie" or "rick_morty"
    reel_temperature: float = 0.4  # Higher temperature (0.4) specifically for witty dialogue & comedic banter
    fish_model: str = "s2"  # Fish Audio TTS model: "s2" (flagship) or "s2-free" (free tier)

    def __post_init__(self) -> None:
        """Validate character pair against supported cast options."""
        clean = self.character_pair.strip().lower()
        if clean not in SUPPORTED_CHARACTER_PAIRS:
            allowed = ", ".join(sorted(f"'{p}'" for p in SUPPORTED_CHARACTER_PAIRS))
            raise ValueError(f"Unsupported character_pair: '{self.character_pair}'. Must be one of: {allowed}")
        object.__setattr__(self, "character_pair", clean)
        if not 0.0 <= self.reel_temperature <= 2.0:
            raise ValueError(f"reel_temperature must be between 0.0 and 2.0, got: {self.reel_temperature}")
        clean_model = self.fish_model.strip() if self.fish_model else "s2"
        object.__setattr__(self, "fish_model", clean_model)


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
    raw_reel_temp = os.getenv("REEL_TEMPERATURE") or raw_media.get("reel_temperature", 0.4)
    raw_fish_model = os.getenv("FISH_MODEL") or raw_media.get("fish_model", "s2")
    media_cfg = MediaConfig(
        generate_media=bool(gen_media),
        character_pair=str(char_pair),
        reel_temperature=float(raw_reel_temp),
        fish_model=str(raw_fish_model),
    )

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
