"""User-facing configuration loader for Meme Market Forensic Research Agent.

Loads settings from config.yaml with environment variable overrides and validation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

SUPPORTED_CHARACTER_PAIRS = frozenset({"peter_stewie", "rick_morty"})
DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_ENV_PATH = Path(".env")


@dataclass(frozen=True)
class ModelEndpointConfig:
    """Configuration for one LLM endpoint and its credential environment variable."""

    model: str = "gpt-5.3-codex"
    base_url: str | None = None  # None uses official provider endpoint
    api_key_env: str | None = None  # Name only, e.g. OPENROUTER_API_KEY; secret stays in .env
    temperature: float | None = None

    def resolve_api_key(self) -> str | None:
        """Read this endpoint's credential from its configured environment variable.

        Returns:
            Secret value when configured and non-empty; otherwise None.
        """
        if not self.api_key_env:
            return None
        value = os.getenv(self.api_key_env)
        return value.strip() if value and value.strip() else None


@dataclass(frozen=True)
class LLMConfig:
    """User-configurable LLM settings supporting fallback lists across providers."""

    models: list[ModelEndpointConfig] = field(default_factory=lambda: [ModelEndpointConfig()])
    temperature: float = 0.2

    @property
    def model(self) -> str:
        """Primary model identifier."""
        return self.models[0].model if self.models else "gpt-5.3-codex"

    @property
    def base_url(self) -> str | None:
        """Primary model base URL."""
        return self.models[0].base_url if self.models else None


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

    max_tool_calls: int = 35
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


def load_config(
    config_path: Path | str | None = None,
    env_path: Path | str | None = None,
) -> AppConfig:
    """Load secrets from .env and non-secret settings from YAML.

    Args:
        config_path: Optional path to config.yaml. Defaults to 'config.yaml'.
        env_path: Optional path to .env. Defaults to sibling of config file.

    Returns:
        Validated AppConfig instance with endpoint credential references.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    resolved_env_path = Path(env_path) if env_path else path.parent / DEFAULT_ENV_PATH
    load_dotenv(resolved_env_path, override=False)
    data: dict[str, Any] = {}

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
                if isinstance(content, dict):
                    data = content
        except Exception as exc:
            raise ValueError(f"Failed to parse config file at {path}: {exc}") from exc

    # Parse non-secret LLM settings from config.yaml only.
    raw_llm = data.get("llm", {}) or {}
    temp = float(raw_llm.get("temperature", 0.2))

    raw_models_list = raw_llm.get("models")
    endpoint_configs: list[ModelEndpointConfig] = []

    if isinstance(raw_models_list, list) and raw_models_list:
        for item in raw_models_list:
            if isinstance(item, dict):
                m_name = item.get("model") or "gpt-5.3-codex"
                b_url = item.get("base_url")
                if b_url:
                    b_url = str(b_url).strip()
                    if not b_url or b_url.lower() in ("none", "null"):
                        b_url = None
                api_key_env = item.get("api_key_env")
                ep_temp = float(item["temperature"]) if "temperature" in item and item["temperature"] is not None else None
                endpoint_configs.append(
                    ModelEndpointConfig(
                        model=m_name,
                        base_url=b_url,
                        api_key_env=str(api_key_env).strip() if api_key_env else None,
                        temperature=ep_temp,
                    )
                )
    else:
        model_name = raw_llm.get("model") or "gpt-5.3-codex"
        base_url = raw_llm.get("base_url")
        if base_url:
            base_url = str(base_url).strip()
            if not base_url or base_url.lower() in ("none", "null"):
                base_url = None
        endpoint_configs.append(ModelEndpointConfig(model=model_name, base_url=base_url))

    llm_cfg = LLMConfig(models=endpoint_configs, temperature=temp)

    # Parse non-secret media settings from config.yaml only.
    raw_media = data.get("media", {}) or {}
    gen_media = raw_media.get("generate_media", True) if "generate_media" in raw_media else True
    char_pair = raw_media.get("character_pair") or "peter_stewie"
    raw_reel_temp = raw_media.get("reel_temperature", 0.4)
    raw_fish_model = raw_media.get("fish_model", "s2")
    media_cfg = MediaConfig(
        generate_media=bool(gen_media),
        character_pair=str(char_pair),
        reel_temperature=float(raw_reel_temp),
        fish_model=str(raw_fish_model),
    )

    # Parse Research config
    raw_res = data.get("research", {}) or {}
    research_cfg = ResearchConfig(
        max_tool_calls=int(raw_res.get("max_tool_calls", 35)),
        max_identical_calls=int(raw_res.get("max_identical_calls", 2)),
        benchmark_ticker=str(raw_res.get("benchmark_ticker", "SPY")),
        sec_periods=int(raw_res.get("sec_periods", 4)),
        cases_root=str(raw_res.get("cases_root", "cases")),
    )

    return AppConfig(llm=llm_cfg, media=media_cfg, research=research_cfg)
