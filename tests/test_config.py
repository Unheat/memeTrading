"""Tests for user configuration loader (app.config)."""
from pathlib import Path
import pytest

from app.config import (
    AppConfig,
    LLMConfig,
    MediaConfig,
    ResearchConfig,
    load_config,
    SUPPORTED_CHARACTER_PAIRS,
)


def test_default_config_instantiation():
    cfg = AppConfig()
    assert cfg.llm.model == "gpt-5.3-codex"
    assert cfg.llm.base_url is None
    assert cfg.llm.temperature == pytest.approx(0.2)
    assert cfg.media.generate_media is True
    assert cfg.media.character_pair == "peter_stewie"
    assert cfg.media.reel_temperature == pytest.approx(0.4)
    assert cfg.media.fish_model == "s2"
    assert cfg.research.max_tool_calls == 35
    assert cfg.research.benchmark_ticker == "SPY"


def test_supported_character_pairs():
    assert "peter_stewie" in SUPPORTED_CHARACTER_PAIRS
    assert "rick_morty" in SUPPORTED_CHARACTER_PAIRS

    # Invalid character pair must raise clear ValueError
    with pytest.raises(ValueError, match="Unsupported character_pair"):
        MediaConfig(character_pair="batman_robin")


def test_load_config_from_yaml_file(tmp_path):
    yaml_file = tmp_path / "test_config.yaml"
    yaml_file.write_text(
        """
llm:
  model: "anthropic/claude-3.5-sonnet"
  base_url: "https://openrouter.ai/api/v1"
  temperature: 0.2

media:
  generate_media: false
  character_pair: "rick_morty"

research:
  max_tool_calls: 20
  benchmark_ticker: "QQQ"
""",
        encoding="utf-8",
    )

    cfg = load_config(yaml_file)
    assert cfg.llm.model == "anthropic/claude-3.5-sonnet"
    assert cfg.llm.base_url == "https://openrouter.ai/api/v1"
    assert cfg.llm.temperature == pytest.approx(0.2)
    assert cfg.media.generate_media is False
    assert cfg.media.character_pair == "rick_morty"
    assert cfg.research.max_tool_calls == 20
    assert cfg.research.benchmark_ticker == "QQQ"


def test_load_config_ignores_non_secret_environment_settings(tmp_path, monkeypatch):
    """Verify config.yaml is the sole source for non-secret user settings."""
    yaml_file = tmp_path / "test_config.yaml"
    yaml_file.write_text(
        "llm:\n  model: 'gpt-4o'\n  base_url: 'https://provider.example/v1'\n"
        "media:\n  character_pair: 'peter_stewie'\n  reel_temperature: 0.4\n  fish_model: 's2-free'",
        encoding="utf-8",
    )

    monkeypatch.setenv("OUTER_AGENT_MODEL", "ignored-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://ignored.example/v1")
    monkeypatch.setenv("CHARACTER_PAIR", "rick_morty")
    monkeypatch.setenv("REEL_TEMPERATURE", "1.0")
    monkeypatch.setenv("FISH_MODEL", "ignored-model")

    cfg = load_config(yaml_file)
    assert cfg.llm.model == "gpt-4o"
    assert cfg.llm.base_url == "https://provider.example/v1"
    assert cfg.media.character_pair == "peter_stewie"
    assert cfg.media.reel_temperature == pytest.approx(0.4)
    assert cfg.media.fish_model == "s2-free"


def test_load_config_models_fallback_list(tmp_path):
    """Verify loading multi-model fallback list from config.yaml."""
    yaml_file = tmp_path / "test_config_models.yaml"
    yaml_file.write_text(
        """
llm:
  temperature: 0.2
  models:
    - model: "openai/gpt-4o"
      base_url: "http://localhost:20128/v1"
      api_key_env: "NINEROUTER_API_KEY"
    - model: "openrouter/anthropic/claude-3.5-sonnet"
      base_url: "https://openrouter.ai/api/v1"
      api_key_env: "OPENROUTER_API_KEY"
    - model: "deepseek/deepseek-chat"
      base_url: "https://api.deepseek.com/v1"
      api_key_env: "DEEPSEEK_API_KEY"
""",
        encoding="utf-8",
    )

    cfg = load_config(yaml_file)
    assert len(cfg.llm.models) == 3
    assert cfg.llm.model == "openai/gpt-4o"
    assert cfg.llm.base_url == "http://localhost:20128/v1"
    assert cfg.llm.models[0].api_key_env == "NINEROUTER_API_KEY"
    assert cfg.llm.models[1].model == "openrouter/anthropic/claude-3.5-sonnet"
    assert cfg.llm.models[1].base_url == "https://openrouter.ai/api/v1"
    assert cfg.llm.models[2].model == "deepseek/deepseek-chat"


def test_model_endpoint_resolves_its_named_secret(monkeypatch):
    """Verify each fallback endpoint reads only its declared environment key."""
    from app.config import ModelEndpointConfig

    monkeypatch.setenv("OPENROUTER_API_KEY", "router-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    endpoint = ModelEndpointConfig(
        model="openrouter/anthropic/claude-sonnet-4",
        api_key_env="OPENROUTER_API_KEY",
    )

    assert endpoint.resolve_api_key() == "router-secret"
