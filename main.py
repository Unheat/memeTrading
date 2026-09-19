#!/usr/bin/env python3
"""Main CLI entrypoint for the Meme Market Forensic Research Agent.

Run autonomous forensic equity investigations, generate SEC-audited research memos,
cited Substack articles, and viral character reels (Peter & Stewie / Rick & Morty).

Usage:
    python main.py --ticker MU --query "Investigate DDR5 memory shortages and gross margin expansion"
    python main.py --query "Is there a cloud GPU wait time bottleneck for NVDA?"
    python main.py --query "find best 2 tech stocks" --article
    python main.py -t MU -q "Should I invest?" --article-video
    python main.py  # Interactive mode
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.agent.runner import run_investigation
from app.agent.state import ResearchRequest
from app.config import load_config
from app.storage.cases import case_path


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Prompt-first deep research agent with optional equity diligence",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--ticker",
        "-t",
        type=str,
        default=None,
        help="Stock ticker symbol (e.g. MU, NVDA, TSLA)",
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        default=None,
        help="Research prompt / question / thesis to investigate",
    )
    parser.add_argument(
        "--company",
        "-c",
        type=str,
        default=None,
        help="Full company name (optional, e.g. 'Micron Technology')",
    )
    parser.add_argument(
        "--theme",
        type=str,
        default=None,
        help="Industry theme or narrative (e.g. 'DDR5 Shortage', 'AI Data Centers')",
    )
    parser.add_argument(
        "--mandate",
        type=str,
        default=None,
        help="Specific research mandate or angle to focus on",
    )
    parser.add_argument(
        "--depth",
        choices=["standard", "deep"],
        default="deep",
        help="Research breadth policy",
    )

    # --- Media generation flags ---
    media_group = parser.add_argument_group("Media Generation (opt-in)")
    media_group.add_argument(
        "--article",
        action="store_true",
        default=False,
        help="Generate cited Substack-style forensic article (article.md)",
    )
    media_group.add_argument(
        "--video",
        action="store_true",
        default=False,
        help="Generate article + dialogue script + render video reel (.mp4) via Faceless",
    )
    media_group.add_argument(
        "--video-script-only",
        action="store_true",
        default=False,
        help="Generate article + dialogue script without rendering .mp4 video",
    )
    media_group.add_argument(
        "--article-video",
        "--media",
        action="store_true",
        default=False,
        help="Generate both the cited article and the rendered video reel",
    )
    media_group.add_argument(
        "--character-pair",
        choices=["peter_stewie", "rick_morty"],
        default=None,
        help="Character duo for viral video reel dialogue",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed debug logging",
    )
    return parser.parse_args()


def _resolve_media_flags(args: argparse.Namespace) -> tuple[bool, bool, bool]:
    """Resolve CLI media flags into (generate_article, generate_video, render_video).

    Args:
        args: Parsed CLI arguments.

    Returns:
        Tuple of (generate_article, generate_video, render_video) booleans.
    """
    gen_article = False
    gen_video = False
    render = False

    if args.article_video:
        gen_article = True
        gen_video = True
        render = True
    if args.video:
        gen_article = True
        gen_video = True
        render = True
    if args.video_script_only:
        gen_article = True
        gen_video = True
        render = False
    if args.article:
        gen_article = True

    return gen_article, gen_video, render


def setup_logging(verbose: bool = False) -> None:
    """Configure terminal logging format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    """Execute main CLI workflow."""
    args = parse_args()
    setup_logging(args.verbose)

    config = load_config()

    print("=" * 70)
    print(" 🔎 PROMPT-FIRST DEEP RESEARCH AGENT")
    print("=" * 70)

    # Prompt user interactively if no query provided
    query = args.query
    ticker = args.ticker
    company = args.company
    theme = args.theme

    if not query:
        print("\n[Interactive Mode]\n")
        try:
            query = input("Deep research request: ").strip()
            while not query:
                print("A research request is required.")
                query = input("Deep research request: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return 1

    gen_article, gen_video, render = _resolve_media_flags(args)

    print("\n[1/3] Initializing Deep Research Engine...")
    print(f"  • Prompt:  {query}")
    if ticker:
        print(f"  • Ticker:  {ticker}")
    if theme:
        print(f"  • Theme:   {theme}")
    if company:
        print(f"  • Company: {company}")
    print(f"  • Model:   {config.llm.model}")
    print("  • Engine:  Multi-Stage Deep Research (Plan -> Execute -> Reflect -> Synthesize)")
    print(f"  • Depth:   {args.depth.capitalize()}")
    media_modes = []
    if gen_article:
        media_modes.append("Article")
    if gen_video and render:
        media_modes.append("Video Reel")
    elif gen_video:
        media_modes.append("Video Script Only")
    print(f"  • Media:   {', '.join(media_modes) if media_modes else 'None (memo only)'}")
    print("-" * 70)

    request = ResearchRequest(
        query=query,
        ticker=ticker,
        company=company,
        theme=theme,
        mandate=args.mandate,
        depth=args.depth,
    )

    character_pair = args.character_pair or config.media.character_pair

    print("[2/3] Planning, researching, and validating cited evidence...")
    try:
        result = run_investigation(
            request=request,
            generate_article=gen_article,
            generate_video=gen_video,
            render_video=render,
            character_pair=character_pair,
            config=config,
        )
    except Exception as exc:
        print(f"\n❌ Investigation failed: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    case_dir = case_path(Path(config.research.cases_root), result.case_id)

    completion = "✅ Deep Research Completed"
    if result.status == "research_incomplete":
        completion = "⚠️ Deep Research Completed With Evidence Gaps"
    elif result.status in {"insufficient_evidence", "validation_required"}:
        completion = "⚠️ Investment Research Completed — No Position"
    print(f"\n[3/3] {completion}")
    print("=" * 70)
    print(f"Case ID:        {result.case_id}")
    print(f"Artifacts Dir:  {case_dir.resolve()}")
    print(f"  📄 Memo:      {case_dir / 'memo.md'}")
    print(f"  📊 JSON:      {case_dir / 'investigation.json'}")
    if (case_dir / "article.md").exists():
        print(f"  📰 Article:   {case_dir / 'article.md'}")
    if (case_dir / "faceless" / "dialogue.json").exists():
        print(f"  🎬 Reel Script: {case_dir / 'faceless' / 'dialogue.json'}")
        print(f"  📱 Caption:   {case_dir / 'faceless' / 'caption.txt'}")
    if (case_dir / "faceless" / "video" ).exists():
        for mp4 in (case_dir / "faceless").rglob("*.mp4"):
            print(f"  🎥 Video:     {mp4}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
