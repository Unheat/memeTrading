"""Tests for the faceless subprocess bridge."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from app.media.faceless_bridge import FacelessBridge


def test_faceless_bridge_initialization(tmp_path):
    bridge = FacelessBridge(faceless_root=tmp_path)
    assert bridge.faceless_root == tmp_path
    assert bridge.scripts_dir == tmp_path / "skills" / "faceless" / "scripts"


def test_faceless_bridge_doctor_execution():
    bridge = FacelessBridge()
    # If faceless directory exists in repo root
    if (bridge.scripts_dir / "doctor.mjs").exists():
        doctor_res = bridge.check_doctor()
        assert isinstance(doctor_res, dict)
        assert "node_ready" in doctor_res


def test_faceless_bridge_graceful_when_unconfigured(tmp_path):
    bridge = FacelessBridge(faceless_root=tmp_path)
    dialogue_file = tmp_path / "dialogue.json"
    dialogue_file.write_text("[]")

    # When scripts don't exist in tmp_path, methods return None gracefully without crashing
    out_dir = tmp_path / "output"
    audio_path = bridge.generate_audio(dialogue_file, topic_slug="mu-ram", output_dir=out_dir)
    assert audio_path is None

    video_path = bridge.generate_video(tmp_path / "dummy.mp3", topic_slug="mu-ram", output_dir=out_dir)
    assert video_path is None
