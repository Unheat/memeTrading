"""Subprocess bridge to the local faceless video generator.

Executes local Node.js scripts in faceless/ without modifying or porting its codebase.
Treats faceless as a local black-box application.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FacelessBridge:
    """Subprocess runner for Creatorberry/faceless reel generation."""

    def __init__(self, faceless_root: Path | str | None = None) -> None:
        self.faceless_root = Path(faceless_root) if faceless_root else Path("faceless")
        self.scripts_dir = self.faceless_root / "skills" / "faceless" / "scripts"

    def is_available(self) -> bool:
        """Return True if Node.js is on PATH and faceless scripts exist."""
        node_bin = shutil.which("node")
        return bool(node_bin and (self.scripts_dir / "doctor.mjs").exists())

    def check_doctor(self) -> dict[str, Any]:
        """Run doctor.mjs to verify environment readiness (node, ffmpeg, fish audio, templates)."""
        if not self.is_available():
            return {"available": False, "node_ready": False, "error": "Node or scripts missing"}

        doctor_script = self.scripts_dir / "doctor.mjs"
        try:
            res = subprocess.run(
                ["node", str(doctor_script.resolve())],
                capture_output=True,
                text=True,
                cwd=str(self.faceless_root.resolve()),
                timeout=15,
            )
            output = res.stdout + res.stderr
            return {
                "available": True,
                "node_ready": "✓ Node.js" in output,
                "ffmpeg_ready": "✓ FFmpeg" in output,
                "fish_ready": "✓ Fish Audio" in output,
                "templates_ready": "✓ Minecraft templates" in output,
                "raw_output": output,
            }
        except Exception as exc:
            logger.warning("Faceless doctor check failed: %s", exc)
            return {"available": False, "error": str(exc)}

    def generate_audio(
        self,
        dialogue_path: Path,
        topic_slug: str,
        output_dir: Path,
        fish_model: str | None = None,
    ) -> Path | None:
        """Invoke generate-audio.mjs to produce full-dialogue.mp3 via Fish Audio."""
        if not self.is_available():
            logger.warning("Faceless scripts not available; skipping audio generation.")
            return None

        script = self.scripts_dir / "generate-audio.mjs"
        if not script.exists():
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "node",
            str(script.resolve()),
            "--script",
            str(dialogue_path.resolve()),
            "--topic",
            topic_slug,
            "--output",
            str(output_dir.resolve()),
        ]

        run_env = dict(os.environ)
        if fish_model:
            run_env["FISH_MODEL"] = str(fish_model).strip()

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.faceless_root.resolve()),
                timeout=120,
                env=run_env,
            )
            if res.returncode != 0:
                logger.warning("generate-audio.mjs failed (exit %d): %s", res.returncode, res.stderr or res.stdout)
                return None

            expected_audio = output_dir / "audio" / topic_slug / "full-dialogue.mp3"
            if expected_audio.exists():
                return expected_audio
            return None
        except Exception as exc:
            logger.warning("Failed to invoke faceless generate-audio: %s", exc)
            return None

    def generate_video(
        self,
        audio_path: Path,
        topic_slug: str,
        output_dir: Path,
    ) -> Path | None:
        """Invoke generate-video.mjs to combine audio with background template."""
        if not self.is_available():
            return None

        script = self.scripts_dir / "generate-video.mjs"
        if not script.exists() or not audio_path.exists():
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "node",
            str(script.resolve()),
            "--audio",
            str(audio_path.resolve()),
            "--topic",
            topic_slug,
            "--output",
            str(output_dir.resolve()),
        ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.faceless_root.resolve()),
                timeout=300,
            )
            if res.returncode != 0:
                logger.warning("generate-video.mjs failed: %s", res.stderr or res.stdout)
                return None

            expected_video = output_dir / "video" / topic_slug / "final-faceless-reel.mp4"
            if expected_video.exists():
                return expected_video
            return None
        except Exception as exc:
            logger.warning("Failed to invoke faceless generate-video: %s", exc)
            return None
