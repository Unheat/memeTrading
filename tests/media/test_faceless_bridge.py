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


def test_add_characters_graceful_when_unconfigured(tmp_path):
    bridge = FacelessBridge(faceless_root=tmp_path)
    result = bridge.add_characters(
        video_path=tmp_path / "dummy.mp4",
        audio_dir=tmp_path / "audio",
        topic_slug="test",
        output_dir=tmp_path / "output",
    )
    assert result is None


def test_add_captions_graceful_when_unconfigured(tmp_path):
    bridge = FacelessBridge(faceless_root=tmp_path)
    result = bridge.add_captions(
        video_path=tmp_path / "dummy.mp4",
        dialogue_path=tmp_path / "dialogue.json",
        audio_dir=tmp_path / "audio",
        topic_slug="test",
        output_dir=tmp_path / "output",
    )
    assert result is None


def test_compose_reel_aborts_when_unavailable(tmp_path):
    """compose_reel should return None when faceless scripts are not available."""
    bridge = FacelessBridge(faceless_root=tmp_path)
    dialogue_file = tmp_path / "dialogue.json"
    dialogue_file.write_text("[]")
    result = bridge.compose_reel(
        dialogue_path=dialogue_file,
        topic_slug="test",
        output_dir=tmp_path / "output",
    )
    assert result is None


def test_compose_reel_aborts_when_ffmpeg_missing(tmp_path):
    """compose_reel should return None when FFmpeg is not detected by doctor."""
    bridge = FacelessBridge(faceless_root=tmp_path)
    dialogue_file = tmp_path / "dialogue.json"
    dialogue_file.write_text("[]")

    with patch.object(bridge, "check_doctor", return_value={
        "available": True,
        "node_ready": True,
        "ffmpeg_ready": False,
        "fish_ready": True,
    }):
        result = bridge.compose_reel(
            dialogue_path=dialogue_file,
            topic_slug="test",
            output_dir=tmp_path / "output",
        )
    assert result is None


def test_compose_reel_aborts_when_fish_missing(tmp_path):
    """compose_reel should return None when Fish Audio is not configured."""
    bridge = FacelessBridge(faceless_root=tmp_path)
    dialogue_file = tmp_path / "dialogue.json"
    dialogue_file.write_text("[]")

    with patch.object(bridge, "check_doctor", return_value={
        "available": True,
        "node_ready": True,
        "ffmpeg_ready": True,
        "fish_ready": False,
    }):
        result = bridge.compose_reel(
            dialogue_path=dialogue_file,
            topic_slug="test",
            output_dir=tmp_path / "output",
        )
    assert result is None
