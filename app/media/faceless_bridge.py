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

# Subprocess timeout limits (seconds)
DOCTOR_TIMEOUT_SECONDS = 15
AUDIO_TIMEOUT_SECONDS = 180
VIDEO_TIMEOUT_SECONDS = 300
CHARACTER_TIMEOUT_SECONDS = 300
CAPTION_TIMEOUT_SECONDS = 300


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
        """Run doctor.mjs to verify environment readiness (node, ffmpeg, fish audio, templates).

        Returns:
            Dictionary with availability flags for each dependency.
        """
        if not self.is_available():
            return {"available": False, "node_ready": False, "error": "Node or scripts missing"}

        doctor_script = self.scripts_dir / "doctor.mjs"
        try:
            res = subprocess.run(
                ["node", str(doctor_script.resolve())],
                capture_output=True,
                text=True,
                cwd=str(self.faceless_root.resolve()),
                timeout=DOCTOR_TIMEOUT_SECONDS,
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
        """Invoke generate-audio.mjs to produce full-dialogue.mp3 via Fish Audio.

        Args:
            dialogue_path: Path to the dialogue.json file.
            topic_slug: Short topic identifier for directory naming.
            output_dir: Root output directory for faceless artifacts.
            fish_model: Optional Fish Audio model override (e.g. "s2", "s2-free").

        Returns:
            Path to the generated full-dialogue.mp3, or None on failure.
        """
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
                timeout=AUDIO_TIMEOUT_SECONDS,
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
        """Invoke generate-video.mjs to combine audio with background template.

        Args:
            audio_path: Path to the full-dialogue.mp3 audio file.
            topic_slug: Short topic identifier for directory naming.
            output_dir: Root output directory for faceless artifacts.

        Returns:
            Path to the generated base video, or None on failure.
        """
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
                timeout=VIDEO_TIMEOUT_SECONDS,
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

    def add_characters(
        self,
        video_path: Path,
        audio_dir: Path,
        topic_slug: str,
        output_dir: Path,
    ) -> Path | None:
        """Invoke add-characters.mjs to overlay synchronized character sprites.

        Args:
            video_path: Path to the base video (final-faceless-reel.mp4).
            audio_dir: Path to the audio topic directory containing per-line mp3s.
            topic_slug: Short topic identifier for directory naming.
            output_dir: Root output directory for faceless artifacts.

        Returns:
            Path to the updated video with character overlays, or None on failure.
        """
        if not self.is_available():
            return None

        script = self.scripts_dir / "add-characters.mjs"
        if not script.exists() or not video_path.exists():
            return None

        cmd = [
            "node",
            str(script.resolve()),
            "--video",
            str(video_path.resolve()),
            "--audio-dir",
            str(audio_dir.resolve()),
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
                timeout=CHARACTER_TIMEOUT_SECONDS,
            )
            if res.returncode != 0:
                logger.warning("add-characters.mjs failed: %s", res.stderr or res.stdout)
                return None

            expected_video = output_dir / "video" / topic_slug / "final-faceless-reel.mp4"
            if expected_video.exists():
                return expected_video
            return None
        except Exception as exc:
            logger.warning("Failed to invoke faceless add-characters: %s", exc)
            return None

    def add_captions(
        self,
        video_path: Path,
        dialogue_path: Path,
        audio_dir: Path,
        topic_slug: str,
        output_dir: Path,
    ) -> Path | None:
        """Invoke add-captions.mjs to burn animated subtitles into the video.

        Args:
            video_path: Path to the video with character overlays.
            dialogue_path: Path to the dialogue.json script file.
            audio_dir: Path to the audio topic directory containing per-line mp3s.
            topic_slug: Short topic identifier for directory naming.
            output_dir: Root output directory for faceless artifacts.

        Returns:
            Path to the final captioned video, or None on failure.
        """
        if not self.is_available():
            return None

        script = self.scripts_dir / "add-captions.mjs"
        if not script.exists() or not video_path.exists():
            return None

        cmd = [
            "node",
            str(script.resolve()),
            "--video",
            str(video_path.resolve()),
            "--script",
            str(dialogue_path.resolve()),
            "--audio-dir",
            str(audio_dir.resolve()),
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
                timeout=CAPTION_TIMEOUT_SECONDS,
            )
            if res.returncode != 0:
                logger.warning("add-captions.mjs failed: %s", res.stderr or res.stdout)
                return None

            expected_video = output_dir / "video" / topic_slug / "final-faceless-reel.mp4"
            if expected_video.exists():
                return expected_video
            return None
        except Exception as exc:
            logger.warning("Failed to invoke faceless add-captions: %s", exc)
            return None

    def compose_reel(
        self,
        dialogue_path: Path,
        topic_slug: str,
        output_dir: Path,
        fish_model: str | None = None,
    ) -> Path | None:
        """Execute the full 4-stage Faceless pipeline to produce a finished video reel.

        Chains generate-audio -> generate-video -> add-characters -> add-captions.
        Each stage is a black-box subprocess call to the existing faceless Node.js scripts.
        If any stage fails, logs the failure and returns None without corrupting earlier artifacts.

        Args:
            dialogue_path: Path to the dialogue.json script file.
            topic_slug: Short topic identifier for directory naming.
            output_dir: Root output directory for faceless artifacts.
            fish_model: Optional Fish Audio model override (e.g. "s2", "s2-free").

        Returns:
            Path to the final rendered video (.mp4), or None if any stage failed.
        """
        doctor = self.check_doctor()
        if not doctor.get("available"):
            logger.warning("Faceless not available: %s", doctor.get("error", "unknown"))
            return None
        if not doctor.get("ffmpeg_ready"):
            logger.warning("FFmpeg not found. Install FFmpeg to render video reels.")
            return None
        if not doctor.get("fish_ready"):
            logger.warning("Fish Audio not configured. Set FISH_API_KEY or run faceless setup-fish.mjs.")
            return None

        logger.info("compose_reel: Stage 1/4 — Generating audio via Fish Audio TTS...")
        audio_path = self.generate_audio(dialogue_path, topic_slug, output_dir, fish_model=fish_model)
        if audio_path is None:
            logger.warning("compose_reel: Audio generation failed; aborting video pipeline.")
            return None

        logger.info("compose_reel: Stage 2/4 — Muxing audio over background template...")
        video_path = self.generate_video(audio_path, topic_slug, output_dir)
        if video_path is None:
            logger.warning("compose_reel: Video generation failed; aborting video pipeline.")
            return None

        audio_dir = output_dir / "audio" / topic_slug
        logger.info("compose_reel: Stage 3/4 — Overlaying character sprites...")
        video_path = self.add_characters(video_path, audio_dir, topic_slug, output_dir)
        if video_path is None:
            logger.warning("compose_reel: Character overlay failed; aborting video pipeline.")
            return None

        logger.info("compose_reel: Stage 4/4 — Burning animated captions...")
        final_video = self.add_captions(video_path, dialogue_path, audio_dir, topic_slug, output_dir)
        if final_video is None:
            logger.warning("compose_reel: Caption burn failed; video may be incomplete.")
            return None

        logger.info("compose_reel: Finished. Video reel: %s", final_video)
        return final_video
