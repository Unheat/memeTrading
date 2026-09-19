"""Dedicated media CLI for standalone video script and reel rendering from an existing case.

Allows running Stage 2 (Video Generation) independently after human review of article.md.

Usage:
    python -m app.media.cli video --case-id MU-2026-09-18-001
    python -m app.media.cli video --latest --character-pair rick_morty
    python -m app.media.cli script --case-id MU-2026-09-18-001
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from app.agent.media import generate_reel_script
from app.agent.model_runtime import create_default_model_runtime
from app.cli.publish import find_case_dir
from app.config import load_config
from app.media.faceless_bridge import FacelessBridge

logger = logging.getLogger(__name__)


def generate_video_for_case(
    case_dir: Path | str,
    character_pair: str = "rick_morty",
    script_only: bool = False,
) -> Path | None:
    """Generate dialogue script and optionally render full faceless MP4 video reel.

    Args:
        case_dir: Path to case directory.
        character_pair: 'rick_morty' or 'peter_stewie'.
        script_only: If True, only write dialogue.json and caption.txt.

    Returns:
        Path to rendered MP4 video, or None if script_only or failure.
    """
    case_path = Path(case_dir)
    article_file = case_path / "article.md"
    memo_file = case_path / "memo.md"

    source_text = ""
    if article_file.exists():
        source_text = article_file.read_text(encoding="utf-8")
    elif memo_file.exists():
        source_text = memo_file.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"Neither article.md nor memo.md found in {case_path}")

    cfg = load_config()
    runtime = create_default_model_runtime()

    logger.info("Synthesizing viral video dialogue using character pair '%s'...", character_pair)
    dialogue_json, caption_text, reel_script_text = generate_reel_script(
        source_text=source_text,
        model=runtime.model,
        character_pair=character_pair,
        reel_temperature=cfg.media.reel_temperature,
    )

    faceless_dir = case_path / "faceless"
    faceless_dir.mkdir(parents=True, exist_ok=True)

    dialogue_path = faceless_dir / "dialogue.json"
    dialogue_path.write_text(json.dumps(dialogue_json, indent=2), encoding="utf-8")
    (faceless_dir / "source-script.txt").write_text(reel_script_text, encoding="utf-8")
    (faceless_dir / "reel_script.txt").write_text(reel_script_text, encoding="utf-8")
    (faceless_dir / "caption.txt").write_text(caption_text, encoding="utf-8")
    logger.info("Dialogue and caption written to %s", faceless_dir)

    if script_only:
        return None

    # Derive valid 1-to-3-word slug for Node generator
    ticker = ""
    inv_file = case_path / "investigation.json"
    if inv_file.exists():
        try:
            inv_data = json.loads(inv_file.read_text(encoding="utf-8"))
            ticker = inv_data.get("ticker", "")
        except Exception:
            pass

    clean_ticker = ticker.strip().lower()
    if clean_ticker and clean_ticker not in {"research", "unknown"}:
        slug_cand = re.sub(r"[^a-z0-9]+", "-", clean_ticker).strip("-")
        parts = [p for p in slug_cand.split("-") if p][:3]
        topic_slug = "-".join(parts) if parts else "deep-research"
    else:
        clean_name = re.sub(r"[^a-z0-9]+", "-", case_path.name.lower()).strip("-")
        parts = [p for p in clean_name.split("-") if p][:3]
        topic_slug = "-".join(parts) if parts else "deep-research"

    logger.info("Invoking Faceless video rendering bridge for slug '%s'...", topic_slug)
    bridge = FacelessBridge()
    final_video = bridge.compose_reel(
        dialogue_path=dialogue_path,
        topic_slug=topic_slug,
        output_dir=faceless_dir,
        fish_model=cfg.media.fish_model,
    )

    if final_video and final_video.exists():
        logger.info("Video successfully rendered at %s", final_video)
        return final_video
    else:
        logger.warning("Video rendering skipped or incomplete.")
        return None


def main() -> None:
    """Media CLI runner."""
    parser = argparse.ArgumentParser(description="Standalone video generation for existing research cases.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    video_parser = subparsers.add_parser("video", help="Render full MP4 video reel")
    video_parser.add_argument("--case-id", default=None, help="Case identifier or directory (defaults to latest)")
    video_parser.add_argument("--latest", action="store_true", help="Use latest case")
    video_parser.add_argument("--character-pair", choices=["rick_morty", "peter_stewie"], default="rick_morty")

    script_parser = subparsers.add_parser("script", help="Generate dialogue script only")
    script_parser.add_argument("--case-id", default=None, help="Case identifier or directory (defaults to latest)")
    script_parser.add_argument("--latest", action="store_true", help="Use latest case")
    script_parser.add_argument("--character-pair", choices=["rick_morty", "peter_stewie"], default="rick_morty")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    case_ident = "--latest" if getattr(args, "latest", False) or not args.case_id else args.case_id
    try:
        case_dir = find_case_dir(case_ident)
        script_only = args.command == "script"
        rendered = generate_video_for_case(
            case_dir=case_dir,
            character_pair=args.character_pair,
            script_only=script_only,
        )
        if rendered:
            print(f"\n Rendered video reel: {rendered}")
        else:
            print(f"\n Dialogue script generated in {case_dir}/faceless/")
    except Exception as exc:
        print(f"\n❌ Error generating video: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
