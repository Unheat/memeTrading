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
    assert cfg.research.max_tool_calls == 15
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


def test_load_config_env_overrides(tmp_path, monkeypatch):
    yaml_file = tmp_path / "test_config.yaml"
    yaml_file.write_text("llm:\n  model: 'gpt-4o'\nmedia:\n  character_pair: 'peter_stewie'", encoding="utf-8")

    monkeypatch.setenv("OUTER_AGENT_MODEL", "gpt-5.3-codex-override")
    monkeypatch.setenv("CHARACTER_PAIR", "rick_morty")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")

    cfg = load_config(yaml_file)
    assert cfg.llm.model == "gpt-5.3-codex-override"
    assert cfg.llm.base_url == "https://api.deepseek.com/v1"
    assert cfg.media.character_pair == "rick_morty"
