#!/usr/bin/env python3
"""Regenerate publication article for an existing completed case without re-running research.

Usage:
    python scripts/regenerate_case_article.py NVDA-2026-09-28-002
    python scripts/regenerate_case_article.py --all
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

# Ensure project root is in sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.agent.media import generate_article_markdown
from app.agent.model_runtime import create_default_model_runtime
from app.config import load_config
from app.storage.cases import find_case_dir

logger = logging.getLogger(__name__)


def regenerate_article_for_case(case_dir: Path | str) -> Path:
    """Regenerate article.md for an existing case from its memo.md and investigation.json.

    Args:
        case_dir: Path to case directory or case ID.

    Returns:
        Path to regenerated article.md.
    """
    case_path = find_case_dir(case_dir)
    inv_file = case_path / "investigation.json"
    memo_file = case_path / "memo.md"
    article_file = case_path / "article.md"

    if not inv_file.exists():
        raise FileNotFoundError(f"investigation.json not found in {case_path}")
    if not memo_file.exists():
        raise FileNotFoundError(f"memo.md not found in {case_path}")

    inv_data = json.loads(inv_file.read_text(encoding="utf-8"))
    memo_md = memo_file.read_text(encoding="utf-8")

    # Backup current article if it exists and backup doesn't exist yet
    backup_file = case_path / "article.old.md"
    if article_file.exists() and not backup_file.exists():
        shutil.copy2(article_file, backup_file)
        logger.info("Backed up existing article to %s", backup_file.name)

    cfg = load_config()
    runtime = create_default_model_runtime(
        model=cfg.llm.model,
        base_url=cfg.llm.base_url,
        temperature=cfg.llm.temperature,
        endpoints=cfg.llm.models,
    )

    logger.info("Regenerating article for case %s using model %s...", case_path.name, cfg.llm.model)
    new_article_md = generate_article_markdown(memo_md, inv_data, model=runtime.model)

    article_file.write_text(new_article_md, encoding="utf-8")
    logger.info("Successfully wrote regenerated article to %s (%d chars)", article_file, len(new_article_md))
    return article_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate article.md for existing cases")
    parser.add_argument("case_id", nargs="?", default=None, help="Case directory or ID")
    parser.add_argument("--all", action="store_true", help="Regenerate all 3 main cases")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    cases_to_run = []
    if args.all:
        cases_to_run = ["NVDA-2026-09-28-002", "PLTR-2026-09-28-001", "INTC-2026-09-28-001"]
    elif args.case_id:
        cases_to_run = [args.case_id]
    else:
        print("Please provide a case_id or --all", file=sys.stderr)
        return 1

    for cid in cases_to_run:
        try:
            print(f"\n=======================================================")
            print(f" Regenerating article for {cid}")
            print(f"=======================================================")
            art_path = regenerate_article_for_case(cid)
            print(f"✅ Generated: {art_path}")
        except Exception as exc:
            print(f"❌ Failed for {cid}: {exc}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
