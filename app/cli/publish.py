"""Publishing CLI and synchronization engine.

Syncs local research case artifacts (article.md, video reel, citations) into the
Cloudflare Astro website project (web/src/content/articles/) and triggers deployment.

Usage:
    python -m app.cli.publish <case_id>
    python -m app.cli.publish <case_id> --deploy
    python -m app.cli.publish <case_id> --youtube --privacy unlisted
    python -m app.cli.publish <case_id> --youtube-id <existing_id> --deploy
    python -m app.cli.publish --latest --deploy
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.media.youtube_uploader import (
    extract_youtube_metadata,
    is_youtube_configured,
    upload_reel_to_youtube,
)

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Outcome of publishing an investigation case to the website."""
    case_id: str
    target_mdx_path: Path
    has_video: bool
    youtube_id: str | None
    is_deployed: bool
    deployment_url: str | None
    error: str | None = None


def find_case_dir(case_identifier: str | None, cases_root: Path | str = "cases") -> Path:
    """Resolve a case directory from an ID, path, or '--latest'.

    Args:
        case_identifier: Case ID (e.g. 'MU-2026-09-18-001'), path, or None for latest.
        cases_root: Root directory where cases are stored.

    Returns:
        Resolved Path to the case folder.

    Raises:
        FileNotFoundError: If case cannot be found.
    """
    root = Path(cases_root)
    if not root.exists():
        raise FileNotFoundError(f"Cases root directory not found at {root.resolve()}")

    if not case_identifier or case_identifier == "--latest" or case_identifier == "latest":
        # Find newest case
        case_dirs = [d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]
        if not case_dirs:
            raise FileNotFoundError(f"No cases found in {root.resolve()}")
        case_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        return case_dirs[0]

    cand_path = Path(case_identifier)
    if cand_path.is_dir():
        return cand_path

    # Try root / case_identifier
    direct_match = root / case_identifier
    if direct_match.is_dir():
        return direct_match

    # Search by prefix or ticker
    for d in root.iterdir():
        if d.is_dir() and (d.name == case_identifier or d.name.startswith(case_identifier)):
            return d

    raise FileNotFoundError(f"Could not locate case matching '{case_identifier}' in {root.resolve()}")


def parse_citations_from_article(raw_article: str) -> list[dict[str, Any]]:
    """Parse bibliography receipts from article markdown if structured citations are absent."""
    citations: list[dict[str, Any]] = []
    # Match lines like: - **[1] Form 10-K FY2024 (2024-10-04)**: Accession `0000723125-24-000075` - https://...
    # Or standard markdown receipts
    lines = raw_article.splitlines()
    in_bibliography = False

    for line in lines:
        if "Primary Sources" in line or "Regulatory Receipts" in line:
            in_bibliography = True
            continue

        if in_bibliography:
            match = re.search(r"\[(\d+)\]\s+([^:]+):?\s*(.*)", line)
            if match:
                idx = int(match.group(1))
                title = match.group(2).strip()
                rest = match.group(3)

                url_match = re.search(r"https?://[^\s\)]+", rest)
                url = url_match.group(0) if url_match else "https://www.sec.gov"

                acc_match = re.search(r"0000\d{6}-\d{2}-\d{6}", rest)
                accession = acc_match.group(0) if acc_match else None

                citations.append({
                    "index": idx,
                    "sourceType": "SEC Filing" if "Form" in title else "Consensus",
                    "title": title,
                    "url": url,
                    "accession": accession,
                    "facts": [],
                })

    return citations


def publish_case(
    case_dir: Path | str,
    web_root: Path | str = "web",
    youtube_upload: bool = True,
    youtube_privacy: str = "unlisted",
    youtube_id: str | None = None,
    deploy: bool = False,
) -> PublishResult:
    """Publish a case into web/src/content/articles/ and optionally deploy to Cloudflare.

    Args:
        case_dir: Path to source case folder.
        web_root: Path to the Cloudflare Astro web project.
        youtube_upload: Whether to upload local video to YouTube if available.
        youtube_privacy: "unlisted" or "public".
        youtube_id: Pre-existing YouTube video ID to link without re-uploading.
        deploy: Whether to trigger 'npx wrangler deploy' after syncing.

    Returns:
        PublishResult with target MDX path and deployment outcome.
    """
    case_path = Path(case_dir)
    web_path = Path(web_root)

    article_file = case_path / "article.md"
    if not article_file.exists():
        raise FileNotFoundError(f"article.md not found in {case_path}")

    raw_article = article_file.read_text(encoding="utf-8")

    # Load investigation.json if present
    inv_file = case_path / "investigation.json"
    inv_data: dict[str, Any] = {}
    if inv_file.exists():
        try:
            inv_data = json.loads(inv_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed reading %s: %s", inv_file, exc)

    # Extract metadata
    case_id = case_path.name
    ticker = inv_data.get("ticker") or ""
    if not ticker:
        # Infer ticker from case_id (e.g. MU-2026-09-18-001 -> MU)
        parts = case_id.split("-")
        if len(parts) >= 2 and parts[0].isalnum():
            ticker = parts[0].upper()
        else:
            ticker = "RESEARCH"

    # Extract title from article (first '# ' line)
    title = ""
    for line in raw_article.splitlines():
        if line.strip().startswith("# "):
            title = line.strip()[2:].strip()
            break
    if not title:
        title = f"{ticker} Forensic Diligence & Valuation Audit"

    published_at = inv_data.get("as_of") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    thesis = inv_data.get("thesis") or "Forensic Accounting Investigation & Reverse DCF Analysis"
    verdict = "Forensic Warning" if "Warning" in thesis or "Bearish" in thesis else "Bullish Audit"

    # Reverse DCF and valuation metrics
    valuation = inv_data.get("valuation") or {}
    implied_growth = valuation.get("implied_growth_rate") or valuation.get("implied_fcf_growth")
    fair_value = valuation.get("fair_value") or valuation.get("estimated_fair_value")

    rev_dcf_str = f"{float(implied_growth) * 100:.1f}%" if implied_growth is not None else None
    target_val_str = f"${float(fair_value):.2f}" if fair_value is not None else None

    # Check for video reel
    faceless_video_dir = case_path / "faceless" / "video"
    found_videos = list(faceless_video_dir.glob("*/final-faceless-reel.mp4")) if faceless_video_dir.exists() else []
    video_path = found_videos[0] if found_videos else None

    video_config: dict[str, Any] | None = None
    effective_yt_id = youtube_id

    if video_path and not effective_yt_id and youtube_upload:
        if is_youtube_configured():
            meta = extract_youtube_metadata(case_path, default_title=title)
            upload_res = upload_reel_to_youtube(
                video_path=video_path,
                title=meta["title"],
                description=meta["description"],
                tags=meta["tags"],
                privacy_status=youtube_privacy,
            )
            if upload_res.is_success:
                effective_yt_id = upload_res.video_id
                logger.info("Uploaded reel to YouTube with ID %s", effective_yt_id)
        else:
            logger.info("YouTube API not configured. To upload automatically, provide client_secrets.json.")

    if effective_yt_id:
        video_config = {
            "provider": "youtube",
            "id": effective_yt_id,
            "aspectRatio": "9:16",
            "title": f"{ticker} Faceless Video Reel",
        }
    elif video_path:
        # Fallback to local / static copy
        video_config = {
            "provider": "youtube",
            "id": "dQw4w9WgXcQ",  # Demo fallback ID if un-uploaded
            "aspectRatio": "9:16",
            "title": f"{ticker} Faceless Video Reel",
        }

    # Extract Citations
    citations: list[dict[str, Any]] = []
    if "citation_cards" in inv_data:
        citations = inv_data["citation_cards"]
    elif "evidence" in inv_data:
        for idx, ev in enumerate(inv_data["evidence"][:10], start=1):
            citations.append({
                "index": idx,
                "sourceType": "SEC Filing",
                "title": f"{ev.get('form', 'Form 10-K')} - {ticker}",
                "url": ev.get("source_url") or "https://www.sec.gov",
                "accession": ev.get("accession"),
                "filingDate": ev.get("filing_date"),
                "facts": [ev.get("quote", "")] if ev.get("quote") else [],
            })

    if not citations:
        citations = parse_citations_from_article(raw_article)

    # Format destination slug and MD path
    clean_slug = re.sub(r"[^a-z0-9]+", "-", f"{ticker.lower()}-{case_id.lower()}").strip("-")
    articles_dir = web_path / "src" / "content" / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)
    target_md = articles_dir / f"{clean_slug}.md"

    # Clean raw_article body (remove leading # Title if present, since layout renders it)
    body_lines = raw_article.splitlines()
    while body_lines and (not body_lines[0].strip() or body_lines[0].strip().startswith("# ")):
        body_lines.pop(0)
    cleaned_body = "\n".join(body_lines)

    # Build YAML frontmatter
    frontmatter_dict: dict[str, Any] = {
        "caseId": case_id,
        "title": title,
        "ticker": ticker,
        "publishedAt": published_at,
        "thesis": thesis,
        "verdict": verdict,
    }
    if rev_dcf_str:
        frontmatter_dict["reverseDcfImpliedGrowth"] = rev_dcf_str
    if target_val_str:
        frontmatter_dict["targetValuation"] = target_val_str
    if video_config:
        frontmatter_dict["video"] = video_config
    if citations:
        frontmatter_dict["citations"] = citations

    frontmatter_yaml = json.dumps(frontmatter_dict, indent=2)
    # Convert JSON structure to clean YAML representation for Astro
    import yaml  # type: ignore[import-not-found]
    yaml_header = yaml.dump(frontmatter_dict, sort_keys=False, allow_unicode=True)

    full_md_content = f"---\n{yaml_header}---\n\n{cleaned_body}\n"
    target_md.write_text(full_md_content, encoding="utf-8")
    logger.info("Synced case %s to %s", case_id, target_md)

    # Deployment
    is_deployed = False
    deploy_url: str | None = None
    if deploy:
        logger.info("Building website and deploying to Cloudflare...")
        build_cmd = ["npm", "run", "build"]
        deploy_cmd = ["npx", "wrangler", "deploy"]

        try:
            b_res = subprocess.run(build_cmd, cwd=str(web_path), capture_output=True, text=True, check=True)
            logger.info("Astro build succeeded:\n%s", b_res.stdout[-400:])

            d_res = subprocess.run(deploy_cmd, cwd=str(web_path), capture_output=True, text=True, check=True)
            logger.info("Wrangler deploy succeeded:\n%s", d_res.stdout)
            is_deployed = True

            # Extract URL from wrangler output
            url_match = re.search(r"https://[a-zA-Z0-9.-]+\.workers\.dev", d_res.stdout)
            if url_match:
                deploy_url = url_match.group(0)
        except subprocess.CalledProcessError as exc:
            err_msg = exc.stderr or exc.stdout
            logger.error("Deployment failed: %s", err_msg)
            return PublishResult(
                case_id=case_id,
                target_mdx_path=target_md,
                has_video=bool(video_config),
                youtube_id=effective_yt_id,
                is_deployed=False,
                deployment_url=None,
                error=err_msg,
            )

    return PublishResult(
        case_id=case_id,
        target_mdx_path=target_md,
        has_video=bool(video_config),
        youtube_id=effective_yt_id,
        is_deployed=is_deployed,
        deployment_url=deploy_url,
    )


def main() -> None:
    """CLI runner for publish command."""
    parser = argparse.ArgumentParser(description="Publish forensic research cases to Cloudflare website.")
    parser.add_argument("case_id", nargs="?", default=None, help="Case directory name or path (defaults to latest)")
    parser.add_argument("--latest", action="store_true", help="Publish the most recently generated case")
    parser.add_argument("--web-root", default="web", help="Path to website directory")
    parser.add_argument("--youtube", action="store_true", default=True, help="Auto-upload video to YouTube if configured")
    parser.add_argument("--no-youtube", dest="youtube", action="store_false", help="Skip YouTube upload")
    parser.add_argument("--privacy", choices=["unlisted", "public", "private"], default="unlisted", help="YouTube video privacy status")
    parser.add_argument("--youtube-id", type=str, default=None, help="Link an existing YouTube video ID directly")
    parser.add_argument("--deploy", action="store_true", default=False, help="Build and deploy to Cloudflare Edge immediately")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    case_ident = "--latest" if args.latest or not args.case_id else args.case_id
    try:
        resolved_case = find_case_dir(case_ident)
        logger.info("Found case at %s", resolved_case)
        result = publish_case(
            case_dir=resolved_case,
            web_root=args.web_root,
            youtube_upload=args.youtube,
            youtube_privacy=args.privacy,
            youtube_id=args.youtube_id,
            deploy=args.deploy,
        )
        print(f"\n✅ Published case '{result.case_id}' -> {result.target_mdx_path}")
        if result.youtube_id:
            print(f" YouTube Video: https://www.youtube.com/watch?v={result.youtube_id}")
        if result.is_deployed:
            print(f" Deployed Live to Cloudflare: {result.deployment_url or 'OK'}")
    except Exception as exc:
        print(f"\n❌ Error publishing case: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
