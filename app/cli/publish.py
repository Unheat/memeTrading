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
    check_youtube_auth,
    extract_youtube_metadata,
    is_youtube_configured,
    upload_reel_to_youtube,
)
from app.storage.cases import find_case_dir

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

    ic_verdict = inv_data.get("ic_verdict", {}) or {}
    raw_verdict = str(ic_verdict.get("verdict") or "").upper()
    if "BULL" in raw_verdict or "BUY" in raw_verdict:
        verdict = "Bullish Audit"
    elif "CAUTION" in raw_verdict or "WATCH" in raw_verdict:
        verdict = "Validation Watch"
    elif "NEUTRAL" in raw_verdict or "HOLD" in raw_verdict:
        verdict = "Neutral"
    else:
        verdict = "Forensic Warning"

    # Reverse DCF and valuation metrics
    quant = inv_data.get("quant_report", {}) or {}
    valuation = quant.get("valuation") or inv_data.get("valuation") or {}
    rev_dcf = valuation.get("reverse_dcf") or {}
    implied_growth = rev_dcf.get("implied_growth_pct") or rev_dcf.get("implied_fcf_growth_rate") or valuation.get("implied_growth_rate")

    base_case = valuation.get("cases", {}).get("base", {})
    fair_value = base_case.get("fair_value_per_share") or valuation.get("fair_value") or valuation.get("estimated_fair_value")

    rev_dcf_str = str(implied_growth) if isinstance(implied_growth, str) else (f"{float(implied_growth) * 100:.1f}%" if implied_growth is not None else None)
    target_val_str = f"${float(fair_value):.2f}" if fair_value is not None else None

    # M-Score risk
    forensic = inv_data.get("forensic_report", {}) or {}
    m_score_val = forensic.get("beneish_m_score") or forensic.get("verdict")
    beneish_m_str = str(m_score_val).replace("_", " ").title() if m_score_val else None

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

    clean_slug = re.sub(r"[^a-z0-9]+", "-", f"{ticker.lower()}-{case_id.lower()}").strip("-")

    if effective_yt_id:
        video_config = {
            "provider": "youtube",
            "id": effective_yt_id,
            "aspectRatio": "9:16",
            "title": f"{ticker} Faceless Video Reel",
        }
    elif video_path and video_path.exists():
        # Copy or optimize video for Cloudflare Edge delivery (<25MB limit)
        web_videos_dir = web_path / "public" / "videos"
        web_videos_dir.mkdir(parents=True, exist_ok=True)
        target_video = web_videos_dir / f"{clean_slug}.mp4"

        source_size_mb = video_path.stat().st_size / (1024 * 1024)
        if source_size_mb > 24:
            logger.info("Optimizing video (%.1fMB) for Cloudflare Edge delivery (<24MB)...", source_size_mb)
            ffmpeg_cand = Path(__file__).resolve().parents[2] / "faceless" / "skills" / "faceless" / ".runtime" / "node_modules" / "ffmpeg-static" / "ffmpeg"
            ffmpeg_bin = str(ffmpeg_cand) if ffmpeg_cand.exists() else "ffmpeg"
            opt_cmd = [
                ffmpeg_bin, "-y", "-i", str(video_path),
                "-vf", "scale=720:1280",
                "-c:v", "libx264", "-preset", "fast",
                "-b:v", "1400k", "-maxrate", "1600k", "-bufsize", "2500k",
                "-c:a", "aac", "-b:a", "96k",
                "-movflags", "+faststart",
                str(target_video),
            ]
            try:
                subprocess.run(opt_cmd, capture_output=True, check=True)
                logger.info("Web video optimized: %s (%.1fMB)", target_video.name, target_video.stat().st_size / (1024 * 1024))
            except Exception as e:
                logger.warning("Video optimization failed, copying directly: %s", e)
                shutil.copy2(video_path, target_video)
        else:
            shutil.copy2(video_path, target_video)

        video_config = {
            "provider": "local",
            "url": f"/videos/{clean_slug}.mp4",
            "aspectRatio": "9:16",
            "title": f"{ticker} Faceless Video Reel",
        }

    # Extract Citations
    citations: list[dict[str, Any]] = []
    if "citation_cards" in inv_data and inv_data["citation_cards"]:
        citations = inv_data["citation_cards"]
    else:
        try:
            from app.agent.media import build_source_registry
            cards = build_source_registry(inv_data)
            if cards:
                citations = [
                    {
                        "index": c.index,
                        "sourceType": c.source_type,
                        "title": c.title,
                        "url": c.url,
                        "accession": c.accession,
                        "filingDate": c.filing_date,
                        "facts": list(c.facts),
                        "quotes": list(c.quotes),
                    }
                    for c in cards
                ]
        except Exception as exc:
            logger.debug("build_source_registry fallback failed: %s", exc)

    if not citations and "evidence" in inv_data:
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

    # Format destination MD path
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
    if beneish_m_str:
        frontmatter_dict["beneishMScore"] = beneish_m_str
    if video_config:
        frontmatter_dict["video"] = video_config
    if citations:
        frontmatter_dict["citations"] = citations
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

        # Ensure Node >= 22 is available for Wrangler
        node_env = os.environ.copy()
        nvm_node_dirs = sorted(Path.home().glob(".nvm/versions/node/v22*/bin"), reverse=True)
        if nvm_node_dirs:
            node_env["PATH"] = f"{nvm_node_dirs[0]}:{node_env.get('PATH', '')}"

        try:
            b_res = subprocess.run(build_cmd, cwd=str(web_path), capture_output=True, text=True, check=True, env=node_env)
            logger.info("Astro build succeeded:\n%s", b_res.stdout[-400:])

            d_res = subprocess.run(deploy_cmd, cwd=str(web_path), capture_output=True, text=True, check=True, env=node_env)
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


def list_published_articles(web_root: Path | str = "web") -> list[dict[str, Any]]:
    """List all published articles in the website content directory."""
    articles_dir = Path(web_root) / "src" / "content" / "articles"
    if not articles_dir.exists():
        return []
    res = []
    for md_file in sorted(articles_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        title_m = re.search(r"^title:\s*(?:'|\")?(.*?)(?:'|\")?$", text, re.MULTILINE)
        case_m = re.search(r"^caseId:\s*(?:'|\")?(.*?)(?:'|\")?$", text, re.MULTILINE)
        video_m = re.search(r"url:\s*(/videos/[^\s]+)", text)
        res.append({
            "slug": md_file.stem,
            "path": md_file,
            "case_id": case_m.group(1) if case_m else "N/A",
            "title": title_m.group(1) if title_m else md_file.stem,
            "video_url": video_m.group(1) if video_m else None,
        })
    return res


def delete_published_article(
    identifier: str,
    web_root: Path | str = "web",
    deploy: bool = False,
) -> bool:
    """Delete an article and its companion video from the website and optionally redeploy.

    Args:
        identifier: Slug, filename, or caseId (e.g. 'mu-mu-2026-09-20-001' or 'MU-2026-09-20-001').
        web_root: Path to the web project root.
        deploy: If True, rebuild and redeploy to Cloudflare immediately.

    Returns:
        True if an article was deleted, False otherwise.
    """
    web_path = Path(web_root)
    articles_dir = web_path / "src" / "content" / "articles"
    if not articles_dir.exists():
        logger.error("Articles directory not found: %s", articles_dir)
        return False

    clean_id = identifier.lower().strip()
    matched_file: Path | None = None

    for md_file in articles_dir.glob("*.md"):
        if md_file.stem.lower() == clean_id:
            matched_file = md_file
            break
        text = md_file.read_text(encoding="utf-8")
        if f"caseId: {identifier}" in text or f"caseId: '{identifier}'" in text or f'caseId: "{identifier}"' in text:
            matched_file = md_file
            break
        if clean_id in md_file.stem.lower():
            matched_file = md_file
            break

    if not matched_file:
        logger.error("No published article matched identifier '%s'", identifier)
        return False

    # Extract video path from frontmatter before deleting markdown
    content = matched_file.read_text(encoding="utf-8")
    video_m = re.search(r"url:\s*(/videos/[^\s]+)", content)
    video_subpath = video_m.group(1).lstrip("/") if video_m else None

    # Delete markdown
    matched_file.unlink()
    logger.info("Deleted article markdown: %s", matched_file)

    # Delete companion video file if it exists in web/public/videos/
    if video_subpath:
        video_file = web_path / "public" / video_subpath
        if video_file.exists():
            video_file.unlink()
            logger.info("Deleted companion video asset: %s", video_file)

    if deploy:
        logger.info("Rebuilding website and redeploying to Cloudflare...")
        build_cmd = ["npm", "run", "build"]
        deploy_cmd = ["npx", "wrangler", "deploy"]

        node_env = os.environ.copy()
        nvm_node_dirs = sorted(Path.home().glob(".nvm/versions/node/v22*/bin"), reverse=True)
        if nvm_node_dirs:
            node_env["PATH"] = f"{nvm_node_dirs[0]}:{node_env.get('PATH', '')}"

        try:
            subprocess.run(build_cmd, cwd=str(web_path), capture_output=True, text=True, check=True, env=node_env)
            d_res = subprocess.run(deploy_cmd, cwd=str(web_path), capture_output=True, text=True, check=True, env=node_env)
            logger.info("Cloudflare deployment updated successfully!")
            url_match = re.search(r"https://[a-zA-Z0-9.-]+\.workers\.dev", d_res.stdout)
            if url_match:
                print(f"🚀 Updated live on Cloudflare: {url_match.group(0)}")
        except subprocess.CalledProcessError as exc:
            logger.error("Redeployment failed: %s", exc.stderr or exc.stdout)
            return False

    return True


def main() -> None:
    """CLI runner for publish command."""
    parser = argparse.ArgumentParser(description="Publish forensic research cases to Cloudflare website.")
    parser.add_argument("case_id", nargs="?", default=None, help="Case directory name or path (defaults to latest)")
    parser.add_argument("--latest", action="store_true", help="Publish the most recently generated case")
    parser.add_argument("--list", action="store_true", help="List all currently published articles")
    parser.add_argument("--check-youtube", action="store_true", help="Test and verify YouTube OAuth authorization")
    parser.add_argument("--delete", type=str, default=None, help="Delete an article + companion video by slug or caseId")
    parser.add_argument("--web-root", default="web", help="Path to website directory")
    parser.add_argument("--youtube", action="store_true", default=True, help="Auto-upload video to YouTube if configured")
    parser.add_argument("--no-youtube", dest="youtube", action="store_false", help="Skip YouTube upload")
    parser.add_argument("--privacy", choices=["unlisted", "public", "private"], default="unlisted", help="YouTube video privacy status")
    parser.add_argument("--youtube-id", type=str, default=None, help="Link an existing YouTube video ID directly")
    parser.add_argument("--deploy", action="store_true", default=False, help="Build and deploy to Cloudflare Edge immediately")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.list:
        articles = list_published_articles(args.web_root)
        print("\n📰 Published Articles on Website:")
        print("=" * 80)
        if not articles:
            print("  (No articles published yet)")
        for a in articles:
            print(f"• Slug:    {a['slug']}")
            print(f"  Title:   {a['title']}")
            print(f"  Case:    {a['case_id']}")
            print(f"  Video:   {a['video_url'] or 'None'}")
            print("-" * 80)
        return

    if args.check_youtube:
        print("\n🔍 Checking YouTube OAuth Configuration...")
        res = check_youtube_auth()
        if res.get("status") == "ok":
            print("✅ YouTube Authentication Successful!")
            print(f"• Scope:        {res.get('scope')}")
            print(f"• Token file:   {res.get('token_file')}")
            print(f"• Secrets file: {res.get('secrets_file')}")
            print(f"• Expires in:   {res.get('expires_in')}s")
        else:
            print(f"❌ YouTube Auth Check Failed: {res.get('error')}", file=sys.stderr)
            sys.exit(1)
        return

    if args.delete:
        ok = delete_published_article(args.delete, web_root=args.web_root, deploy=args.deploy)
        if ok:
            print(f"\n✅ Successfully deleted article and video matching '{args.delete}'.")
            if not args.deploy:
                print("💡 Tip: Run with --deploy to push the changes live to Cloudflare.")
        else:
            print(f"\n❌ Could not find article matching '{args.delete}'.", file=sys.stderr)
            sys.exit(1)
        return

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
