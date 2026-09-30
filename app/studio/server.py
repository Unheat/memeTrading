"""Local Studio GUI HTTP server.

Provides a clean browser dashboard for running investigations, reviewing forensic articles,
rendering faceless video reels, and 1-click publishing to the Cloudflare website.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.agent.callbacks import normalize_legacy_stage_events
from app.agent.runner import run_investigation
from app.agent.state import ResearchRequest
from app.cli.publish import publish_case
from app.media.cli import generate_video_for_case
from app.storage.cases import find_case_dir

logger = logging.getLogger(__name__)

# Execution lock and status tracking
_ACTIVE_JOB: dict[str, Any] = {
    "status": "idle",
    "case_id": None,
    "job_id": None,
    "events": [],
    "log": [],
}
_JOB_LOCK = threading.Lock()


def get_active_job_snapshot() -> dict[str, Any]:
    """Return a thread-safe snapshot of active job state."""
    with _JOB_LOCK:
        return {
            "status": _ACTIVE_JOB["status"],
            "case_id": _ACTIVE_JOB["case_id"],
            "job_id": _ACTIVE_JOB["job_id"],
            "events_count": len(_ACTIVE_JOB.get("events", [])),
            "log": list(_ACTIVE_JOB.get("log", [])),
        }


def get_all_cases(cases_root: str = "cases") -> list[dict[str, Any]]:
    """Scan and return list of all local research cases."""
    root = Path(cases_root)
    if not root.exists():
        return []

    results: list[dict[str, Any]] = []
    for d in root.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue

        has_article = (d / "article.md").exists()
        has_memo = (d / "memo.md").exists()
        has_json = (d / "investigation.json").exists()
        video_dir = d / "faceless" / "video"
        has_video = bool(list(video_dir.glob("*/final-faceless-reel.mp4"))) if video_dir.exists() else False

        ticker = ""
        title = ""
        publication_status = "blocked"
        publication_reasons: list[str] = []
        if has_json:
            try:
                data = json.loads((d / "investigation.json").read_text(encoding="utf-8"))
                ticker = data.get("ticker", "")
                pub = data.get("publication_readiness") or {}
                publication_status = pub.get("status", "blocked")
                publication_reasons = list(pub.get("reasons") or [])
            except Exception:
                pass

        if not ticker:
            parts = d.name.split("-")
            ticker = parts[0] if parts else "UNKNOWN"

        if has_article:
            for line in (d / "article.md").read_text(encoding="utf-8").splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

        results.append({
            "case_id": d.name,
            "ticker": ticker,
            "title": title or f"{ticker} Investigation",
            "has_article": has_article,
            "has_memo": has_memo,
            "has_video": has_video,
            "publication_status": publication_status,
            "publication_reasons": publication_reasons,
            "is_publishable": publication_status == "publishable",
            "mtime": d.stat().st_mtime,
        })

    results.sort(key=lambda c: c["mtime"], reverse=True)
    return results


class StudioHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Local Studio."""

    def log_message(self, format: str, *args: Any) -> None:
        """Silence standard request logging to keep terminal tidy."""
        return

    def _send_json(self, data: Any, status: int = 200) -> None:
        try:
            payload = json.dumps(data, default=str).encode("utf-8")
        except Exception as exc:
            logger.error("Failed to JSON-serialize response payload: %s", exc)
            payload = json.dumps({"error": f"Serialization error: {exc}"}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            html = get_studio_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            # Always revalidate the Studio shell so UI updates land on refresh
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(html)
            return

        if path == "/api/cases":
            cases = get_all_cases()
            self._send_json({"cases": cases, "job": get_active_job_snapshot()})
            return

        if path == "/api/job-events":
            qs = parse_qs(parsed.query)
            since_raw = qs.get("since", ["0"])[0]
            try:
                since = max(0, int(since_raw))
            except ValueError:
                since = 0

            with _JOB_LOCK:
                all_events = list(_ACTIVE_JOB.get("events", []))
                status = _ACTIVE_JOB.get("status", "idle")
                case_id = _ACTIVE_JOB.get("case_id")
                job_id = _ACTIVE_JOB.get("job_id")

            new_events = all_events[since:] if since < len(all_events) else []
            self._send_json({
                "status": status,
                "case_id": case_id,
                "job_id": job_id,
                "since": since,
                "next_seq": len(all_events),
                "events": new_events,
            })
            return

        if path.startswith("/api/case/") and path.endswith("/events"):
            parts = [p for p in path.split("/") if p]
            # ['api', 'case', '<case_id>', 'events']
            if len(parts) >= 4:
                case_id = parts[2]
                try:
                    case_dir = find_case_dir(case_id)
                    events_file = case_dir / "events.json"
                    if events_file.exists():
                        events_data = normalize_legacy_stage_events(
                            json.loads(events_file.read_text(encoding="utf-8"))
                        )
                    else:
                        events_data = []
                        inv_file = case_dir / "investigation.json"
                        if inv_file.exists():
                            inv_json = json.loads(inv_file.read_text(encoding="utf-8"))
                            for idx, s in enumerate(inv_json.get("searches_performed", []), 1):
                                events_data.append({
                                    "seq": idx,
                                    "timestamp": "",
                                    "event_type": "tool_call",
                                    "stage": "executor",
                                    "title": f"Executed tool: {s.get('tool')}",
                                    "payload": s,
                                })
                    self._send_json({"case_id": case_dir.name, "events": events_data})
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=404)
                return

        if path.startswith("/api/case/"):
            case_id = path[len("/api/case/"):]
            try:
                case_dir = find_case_dir(case_id)
                article_path = case_dir / "article.md"
                article_text = article_path.read_text(encoding="utf-8") if article_path.exists() else ""

                caption_path = case_dir / "faceless" / "caption.txt"
                caption_text = caption_path.read_text(encoding="utf-8") if caption_path.exists() else ""

                video_dir = case_dir / "faceless" / "video"
                vids = list(video_dir.glob("*/final-faceless-reel.mp4")) if video_dir.exists() else []
                has_video = bool(vids)

                inv_path = case_dir / "investigation.json"
                pub_readiness: dict[str, Any] = {}
                if inv_path.exists():
                    try:
                        inv_data = json.loads(inv_path.read_text(encoding="utf-8"))
                        pub_readiness = dict(inv_data.get("publication_readiness") or {})
                    except Exception:
                        pass

                self._send_json({
                    "case_id": case_dir.name,
                    "article": article_text,
                    "caption": caption_text,
                    "has_video": has_video,
                    "publication_readiness": pub_readiness,
                })
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=404)
            return

        if path.startswith("/api/video/"):
            case_id = path[len("/api/video/"):]
            try:
                case_dir = find_case_dir(case_id)
                video_dir = case_dir / "faceless" / "video"
                vids = list(video_dir.glob("*/final-faceless-reel.mp4"))
                if not vids or not vids[0].exists():
                    self.send_error(404, "Video not found")
                    return

                video_file = vids[0]
                file_size = video_file.stat().st_size

                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

                with open(video_file, "rb") as f:
                    while chunk := f.read(65536):
                        self.wfile.write(chunk)
            except Exception as exc:
                self.send_error(500, str(exc))
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            req_data = json.loads(post_body)
        except Exception:
            req_data = {}

        if path == "/api/run-research":
            raw_ticker = req_data.get("ticker", "").strip()
            raw_query = req_data.get("query", "").strip()
            depth = req_data.get("depth", "deep")
            with_video = bool(req_data.get("with_video", False))
            character_pair = req_data.get("character_pair", "rick_morty")

            # Auto-route multi-word phrases or conversational prompts from ticker into query
            ticker = raw_ticker
            query = raw_query
            if ticker:
                has_spaces = " " in ticker or "\t" in ticker or "\n" in ticker
                is_too_long = len(ticker) > 10
                is_prompt = any(
                    w in ticker.upper().split()
                    for w in ("FIND", "BEST", "INVEST", "STOCK", "STOCKS", "RIGHT", "NOW", "WHAT", "HOW", "WHICH", "TECH")
                )
                if has_spaces or is_too_long or is_prompt:
                    if not query:
                        query = ticker
                    else:
                        query = f"{ticker} — {query}"
                    ticker = ""

            if not query and not ticker:
                self._send_json({"error": "Ticker or Query is required"}, status=400)
                return

            with _JOB_LOCK:
                if _ACTIVE_JOB["status"] in {"running", "rendering_video"}:
                    self._send_json({"error": "A job is already actively running"}, status=409)
                    return
                job_id = f"job-{int(datetime.now(timezone.utc).timestamp()*1000)}"
                _ACTIVE_JOB["status"] = "running"
                _ACTIVE_JOB["job_id"] = job_id
                _ACTIVE_JOB["case_id"] = None
                _ACTIVE_JOB["events"] = [
                    {
                        "seq": 1,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event_type": "stage",
                        "stage": "starting",
                        "title": f"Dispatching research for {ticker or query}",
                        "payload": {"ticker": ticker, "query": query, "depth": depth},
                    }
                ]
                _ACTIVE_JOB["log"] = [f"Starting research for {ticker or query}..."]

            def _on_event(event: dict[str, Any]) -> None:
                with _JOB_LOCK:
                    _ACTIVE_JOB.setdefault("events", []).append(event)
                    if event.get("event_type") in {"stage", "log"} and event.get("title"):
                        _ACTIVE_JOB.setdefault("log", []).append(event.get("title", ""))

            def _background_worker():
                try:
                    req = ResearchRequest(
                        ticker=ticker or None,
                        query=query or f"Forensic equity diligence on {ticker}",
                        depth=depth,
                    )
                    res = run_investigation(
                        request=req,
                        generate_article=True,
                        generate_video=with_video,
                        render_video=with_video,
                        character_pair=character_pair,
                        event_callback=_on_event,
                    )
                    with _JOB_LOCK:
                        _ACTIVE_JOB["status"] = "completed"
                        _ACTIVE_JOB["case_id"] = res.case_id
                        _ACTIVE_JOB["log"].append(f"Completed! Case generated: {res.case_id}")
                except Exception as e:
                    with _JOB_LOCK:
                        _ACTIVE_JOB["status"] = "failed"
                        _ACTIVE_JOB["log"].append(f"Failed: {e}")
                        _ACTIVE_JOB.setdefault("events", []).append({
                            "seq": len(_ACTIVE_JOB.get("events", [])) + 1,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event_type": "stage",
                            "stage": "failed",
                            "title": f"Investigation Failed: {e}",
                            "payload": {"error": str(e)},
                        })

            threading.Thread(target=_background_worker, daemon=True).start()
            self._send_json({"status": "started", "message": "Research job dispatched", "job_id": job_id})
            return

        if path == "/api/run-video":
            case_id = req_data.get("case_id", "")
            character_pair = req_data.get("character_pair", "rick_morty")
            if not case_id:
                self._send_json({"error": "case_id is required"}, status=400)
                return

            try:
                case_path = find_case_dir(case_id)
            except Exception as e:
                self._send_json({"error": f"Case not found: {e}"}, status=404)
                return

            inv_path = case_path / "investigation.json"
            if not inv_path.exists():
                self._send_json({"error": f"Case {case_id} lacks investigation.json audit record."}, status=400)
                return

            try:
                inv_data = json.loads(inv_path.read_text(encoding="utf-8"))
            except Exception as e:
                self._send_json({"error": f"Invalid investigation.json for {case_id}: {e}"}, status=400)
                return

            pub = inv_data.get("publication_readiness") or {}
            if pub.get("status") != "publishable" or not pub.get("passed"):
                reasons = pub.get("reasons") or ["Case publication readiness is not publishable"]
                self._send_json(
                    {
                        "error": f"Case {case_id} is blocked from video generation: {'; '.join(reasons)}",
                        "publication_readiness": pub,
                    },
                    status=400,
                )
                return

            if not (case_path / "article.md").exists():
                self._send_json({"error": f"Case {case_id} lacks a verified article.md"}, status=400)
                return

            with _JOB_LOCK:
                if _ACTIVE_JOB["status"] in {"running", "rendering_video"}:
                    self._send_json({"error": "A job is already actively running"}, status=409)
                    return
                job_id = f"video-{int(datetime.now(timezone.utc).timestamp()*1000)}"
                _ACTIVE_JOB["status"] = "rendering_video"
                _ACTIVE_JOB["job_id"] = job_id
                _ACTIVE_JOB["case_id"] = case_id
                _ACTIVE_JOB["events"] = [
                    {
                        "seq": 1,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event_type": "stage",
                        "stage": "video_rendering",
                        "title": f"Rendering video reel for {case_id}",
                        "payload": {"character_pair": character_pair},
                    }
                ]
                _ACTIVE_JOB["log"] = [f"Rendering video reel for {case_id}..."]

            def _video_worker():
                try:
                    rendered = generate_video_for_case(case_path, character_pair=character_pair)
                    with _JOB_LOCK:
                        _ACTIVE_JOB["status"] = "completed"
                        _ACTIVE_JOB["case_id"] = case_id
                        _ACTIVE_JOB["log"].append(f"Video rendered successfully: {rendered}")
                        _ACTIVE_JOB.setdefault("events", []).append({
                            "seq": len(_ACTIVE_JOB.get("events", [])) + 1,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event_type": "stage",
                            "stage": "completed",
                            "title": f"Video rendered successfully: {rendered}",
                            "payload": {"video": str(rendered)},
                        })
                except Exception as e:
                    with _JOB_LOCK:
                        _ACTIVE_JOB["status"] = "failed"
                        _ACTIVE_JOB["log"].append(f"Video failed: {e}")
                        _ACTIVE_JOB.setdefault("events", []).append({
                            "seq": len(_ACTIVE_JOB.get("events", [])) + 1,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event_type": "stage",
                            "stage": "failed",
                            "title": f"Video rendering failed: {e}",
                            "payload": {"error": str(e)},
                        })

            threading.Thread(target=_video_worker, daemon=True).start()
            self._send_json({"status": "started", "message": "Video rendering dispatched", "job_id": job_id})
            return

        if path == "/api/publish":
            case_id = req_data.get("case_id", "")
            youtube_id = req_data.get("youtube_id", "").strip() or None
            youtube_upload = bool(req_data.get("youtube_upload", True))
            deploy = bool(req_data.get("deploy", False))

            try:
                case_path = find_case_dir(case_id)
            except Exception as e:
                self._send_json({"error": f"Case not found: {e}"}, status=404)
                return

            inv_path = case_path / "investigation.json"
            if not inv_path.exists():
                self._send_json({"error": f"Case {case_id} lacks investigation.json audit record."}, status=400)
                return

            try:
                inv_data = json.loads(inv_path.read_text(encoding="utf-8"))
            except Exception as e:
                self._send_json({"error": f"Invalid investigation.json for {case_id}: {e}"}, status=400)
                return

            pub = inv_data.get("publication_readiness") or {}
            if pub.get("status") != "publishable" or not pub.get("passed"):
                reasons = pub.get("reasons") or ["Case publication readiness is not publishable"]
                self._send_json(
                    {
                        "error": f"Case {case_id} is blocked from publication: {'; '.join(reasons)}",
                        "publication_readiness": pub,
                    },
                    status=400,
                )
                return

            try:
                res = publish_case(
                    case_dir=case_path,
                    youtube_upload=youtube_upload,
                    youtube_id=youtube_id,
                    deploy=deploy,
                )
                self._send_json({
                    "success": True,
                    "case_id": res.case_id,
                    "target_mdx": str(res.target_mdx_path),
                    "youtube_id": res.youtube_id,
                    "is_deployed": res.is_deployed,
                    "deploy_url": res.deployment_url,
                })
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        self.send_error(404, "Not found")


def get_studio_html() -> str:
    """Return the self-contained Obsidian Dark HTML/JS interface for the Local Studio."""
    return """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MemeTrading Local Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            obsidian: { DEFAULT: '#0A0D12', card: '#121722', subtle: '#181F2E', border: '#1E2638' },
            emerald: { audit: '#10B981' },
            cyan: { consensus: '#06B6D4' },
            amber: { warning: '#F59E0B' }
          }
        }
      }
    }
  </script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    body { background-color: #0A0D12; color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-thumb { background: #1E2638; border-radius: 3px; }
  </style>
</head>
<body class="min-h-screen flex flex-col">
  <!-- Top Navigation -->
  <header class="border-b border-obsidian-border bg-obsidian-card/80 backdrop-blur-md px-6 py-3.5 flex items-center justify-between sticky top-0 z-30">
    <div class="flex items-center gap-3">
      <div class="w-8 h-8 rounded-lg bg-emerald-audit/20 border border-emerald-audit/40 flex items-center justify-center text-emerald-audit font-mono font-bold">
        MT
      </div>
      <div>
        <div class="flex items-center gap-2">
          <h1 class="font-bold text-sm tracking-tight">MEMETRADING LOCAL STUDIO</h1>
          <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-audit/10 text-emerald-audit border border-emerald-audit/30 font-semibold uppercase">Operator Hub</span>
        </div>
      </div>
    </div>
    <div class="flex items-center gap-3">
      <div id="job-badge" class="px-2.5 py-1 rounded-full text-xs font-mono bg-obsidian border border-obsidian-border text-text-muted flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-emerald-audit"></span>
        <span id="job-status-text">Idle</span>
      </div>
      <a href="http://localhost:4321" target="_blank" class="text-xs font-mono text-emerald-audit hover:underline flex items-center gap-1.5 bg-emerald-audit/10 px-3 py-1 rounded-lg border border-emerald-audit/30">
        <span>Open Public Site</span>
        <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
      </a>
    </div>
  </header>

  <!-- Main Grid -->
  <div class="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
    <!-- Left Column: Controls & Launcher (5 cols) -->
    <div class="lg:col-span-5 space-y-6">
      <!-- Launcher Box -->
      <div class="bg-obsidian-card border border-obsidian-border rounded-2xl p-5 shadow-xl">
        <div class="flex items-center gap-2 mb-4">
          <i class="fa-solid fa-bolt text-emerald-audit"></i>
          <h2 class="font-semibold text-sm">Launch Investigation</h2>
        </div>

        <div class="space-y-4 text-xs font-mono">
          <div>
            <label class="text-text-muted block mb-1">Target Ticker <span class="text-[10px] text-text-muted/70">(Optional — leave blank to screen universe)</span></label>
            <input id="input-ticker" type="text" placeholder="e.g. NVDA (or blank for wide screening)" class="w-full bg-obsidian border border-obsidian-border rounded-lg px-3 py-2 text-text-primary focus:border-emerald-audit focus:outline-none uppercase font-bold" />
          </div>

          <div>
            <label class="text-text-muted block mb-1">Research Prompt / Screening Mandate</label>
            <textarea id="input-query" rows="2" placeholder="e.g. Find best high-growth tech stocks to invest right now, or audit inventory drift..." class="w-full bg-obsidian border border-obsidian-border rounded-lg px-3 py-2 text-text-primary focus:border-emerald-audit focus:outline-none"></textarea>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="text-text-muted block mb-1">Character Duo</label>
              <select id="input-duo" class="w-full bg-obsidian border border-obsidian-border rounded-lg px-2.5 py-2 text-text-primary focus:border-emerald-audit focus:outline-none">
                <option value="rick_morty">Rick & Morty</option>
                <option value="peter_stewie">Peter & Stewie</option>
              </select>
            </div>
            <div>
              <label class="text-text-muted block mb-1">Depth</label>
              <select id="input-depth" class="w-full bg-obsidian border border-obsidian-border rounded-lg px-2.5 py-2 text-text-primary focus:border-emerald-audit focus:outline-none">
                <option value="deep">Deep Institutional</option>
                <option value="standard">Standard Quick</option>
              </select>
            </div>
          </div>

          <!-- Staged Action Buttons -->
          <div class="pt-2 space-y-2.5">
            <button id="btn-run-article" class="w-full py-2.5 rounded-xl bg-emerald-audit/20 hover:bg-emerald-audit/30 text-emerald-audit border border-emerald-audit/40 font-semibold flex items-center justify-center gap-2 transition-all">
              <i class="fa-solid fa-file-lines"></i>
              <span>Step 1: Run Research & Article Only</span>
            </button>
            <button id="btn-run-all" class="w-full py-2.5 rounded-xl bg-obsidian-subtle hover:bg-obsidian-border text-text-secondary border border-obsidian-border font-semibold flex items-center justify-center gap-2 transition-all">
              <i class="fa-solid fa-film"></i>
              <span>One-Shot: Research + Article + Video</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Case Archive List -->
      <div class="bg-obsidian-card border border-obsidian-border rounded-2xl p-5 shadow-xl">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <i class="fa-solid fa-folder-open text-cyan-consensus"></i>
            <h3 class="font-semibold text-sm">Past Investigations</h3>
          </div>
          <button id="btn-refresh" class="text-xs text-text-muted hover:text-text-primary">
            <i class="fa-solid fa-rotate-right"></i>
          </button>
        </div>
        <div id="cases-list" class="space-y-2 max-h-72 overflow-y-auto pr-1 text-xs font-mono">
          <div class="text-text-muted text-center py-6">Loading cases...</div>
        </div>
      </div>
    </div>

    <!-- Right Column: Case Review & Publishing Station (7 cols) -->
    <div class="lg:col-span-7 space-y-6">
      <div class="bg-obsidian-card border border-obsidian-border rounded-2xl p-5 shadow-xl min-h-[600px] flex flex-col">
        <!-- Review Station Header -->
        <div class="flex items-center justify-between pb-3 border-b border-obsidian-border">
          <div>
            <span class="text-[10px] font-mono text-text-muted uppercase">Active Case Review</span>
            <h3 id="active-case-title" class="font-bold text-base text-text-primary">Select a case to inspect</h3>
          </div>
          <div class="flex items-center gap-2" id="case-badges"></div>
        </div>

        <!-- Review Tabs -->
        <div class="flex items-center gap-4 border-b border-obsidian-border pt-3 text-xs font-mono overflow-x-auto">
          <button class="tab-btn pb-2 border-b-2 border-emerald-audit text-emerald-audit font-semibold flex items-center gap-1.5" data-tab="tab-trace">
            <span id="trace-pulse-dot" class="w-2 h-2 rounded-full bg-emerald-audit animate-pulse hidden"></span>
            <i class="fa-solid fa-microchip text-[11px]"></i>
            <span>Live Model Trace</span>
          </button>
          <button class="tab-btn pb-2 border-b-2 border-transparent text-text-muted hover:text-text-secondary flex items-center gap-1.5" data-tab="tab-article">
            <i class="fa-solid fa-file-lines text-[11px]"></i>
            <span>Article & Receipts</span>
          </button>
          <button class="tab-btn pb-2 border-b-2 border-transparent text-text-muted hover:text-text-secondary flex items-center gap-1.5" data-tab="tab-video">
            <i class="fa-solid fa-clapperboard text-[11px]"></i>
            <span>Faceless Video Reel</span>
          </button>
          <button class="tab-btn pb-2 border-b-2 border-transparent text-text-muted hover:text-text-secondary flex items-center gap-1.5" data-tab="tab-publish">
            <i class="fa-solid fa-cloud-arrow-up text-[11px]"></i>
            <span>Cloudflare Publish</span>
          </button>
        </div>

        <!-- Tab Content: Live Execution & Model Trace -->
        <div id="tab-trace" class="tab-pane flex-1 pt-4 flex flex-col space-y-3 min-h-[500px]">
          <!-- Status Bar: current stage + progress rail + counter -->
          <div class="trace-shell border border-obsidian-border rounded-xl px-4 py-3">
            <div class="flex items-center justify-between gap-3">
              <div class="flex items-center gap-2.5 min-w-0">
                <span id="trace-pulse-dot" class="w-2 h-2 rounded-full bg-emerald-audit animate-pulse hidden"></span>
                <span class="text-[10px] uppercase tracking-[0.14em] text-text-muted font-semibold">Pipeline</span>
                <span id="trace-current-stage-title" class="text-[12px] font-bold text-text-primary truncate">Ready — launch an investigation</span>
              </div>
              <span id="trace-event-counter" class="text-[10px] font-mono text-text-muted whitespace-nowrap">0 events</span>
            </div>
            <!-- Progress rail: 5 canonical pipeline stages (PIPELINE_ARCHITECTURE.md) -->
            <div class="relative mt-3.5 mb-1.5 mx-1">
              <div class="absolute left-0 right-0 top-[5px] h-px bg-obsidian-border"></div>
              <div id="trace-rail-progress" class="absolute left-0 top-[5px] h-px bg-emerald-audit transition-all duration-500" style="width:0%"></div>
              <div class="relative flex justify-between">
                <div class="flex flex-col items-center gap-1.5 w-24" data-step="planner">
                  <div class="step-node w-[11px] h-[11px] rounded-full border-2 border-obsidian-border bg-obsidian-card transition-all duration-300"></div>
                  <span class="step-label text-[9px] uppercase tracking-wider text-text-muted text-center">Plan &amp; Discovery</span>
                </div>
                <div class="flex flex-col items-center gap-1.5 w-24" data-step="executor">
                  <div class="step-node w-[11px] h-[11px] rounded-full border-2 border-obsidian-border bg-obsidian-card transition-all duration-300"></div>
                  <span class="step-label text-[9px] uppercase tracking-wider text-text-muted text-center">Research Loop</span>
                </div>
                <div class="flex flex-col items-center gap-1.5 w-24" data-step="ingest">
                  <div class="step-node w-[11px] h-[11px] rounded-full border-2 border-obsidian-border bg-obsidian-card transition-all duration-300"></div>
                  <span class="step-label text-[9px] uppercase tracking-wider text-text-muted text-center">Ingestion</span>
                </div>
                <div class="flex flex-col items-center gap-1.5 w-24" data-step="reflect">
                  <div class="step-node w-[11px] h-[11px] rounded-full border-2 border-obsidian-border bg-obsidian-card transition-all duration-300"></div>
                  <span class="step-label text-[9px] uppercase tracking-wider text-text-muted text-center">Reflection</span>
                </div>
                <div class="flex flex-col items-center gap-1.5 w-24" data-step="diligence">
                  <div class="step-node w-[11px] h-[11px] rounded-full border-2 border-obsidian-border bg-obsidian-card transition-all duration-300"></div>
                  <span class="step-label text-[9px] uppercase tracking-wider text-text-muted text-center">Governance &amp; Verdict</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Controls & Filter Toolbar -->
          <div class="flex items-center justify-between gap-2 text-[11px] font-mono flex-wrap bg-obsidian/40 p-2 rounded-xl border border-obsidian-border/60">
            <div class="flex items-center gap-1.5 overflow-x-auto" id="trace-filter-group">
              <button class="filter-btn px-2.5 py-1 rounded-lg bg-emerald-audit/20 text-emerald-audit border border-emerald-audit/40 font-semibold" data-filter="all">All</button>
              <button class="filter-btn px-2.5 py-1 rounded-lg bg-obsidian text-text-muted border border-obsidian-border hover:text-text-primary" data-filter="llm_thinking">🧠 Reasoning</button>
              <button class="filter-btn px-2.5 py-1 rounded-lg bg-obsidian text-text-muted border border-obsidian-border hover:text-text-primary" data-filter="tool_call">🛠️ Calls</button>
              <button class="filter-btn px-2.5 py-1 rounded-lg bg-obsidian text-text-muted border border-obsidian-border hover:text-text-primary" data-filter="tool_result">📥 Returns</button>
              <button class="filter-btn px-2.5 py-1 rounded-lg bg-obsidian text-text-muted border border-obsidian-border hover:text-text-primary" data-filter="llm_response">💬 Decisions</button>
              <button class="filter-btn px-2.5 py-1 rounded-lg bg-obsidian text-text-muted border border-obsidian-border hover:text-text-primary" data-filter="gate">🎯 Gates</button>
            </div>
            <div class="flex items-center gap-3">
              <label class="flex items-center gap-1.5 text-text-muted text-[10px] cursor-pointer">
                <input id="check-autoscroll" type="checkbox" checked class="rounded bg-obsidian border-obsidian-border text-emerald-audit" />
                <span>Auto-scroll</span>
              </label>
              <button id="btn-clear-trace" class="text-text-muted hover:text-amber-warning text-[10px]">
                <i class="fa-solid fa-trash-can mr-1"></i>Clear
              </button>
            </div>
          </div>

          <!-- Chat-style event stream: grouped by agent with avatars -->
          <div id="trace-events-stream" class="flex-1 overflow-y-auto max-h-[460px] px-1 pr-2 text-xs">
            <div class="text-center text-text-muted py-12">
              <i class="fa-solid fa-terminal text-2xl mb-2 text-obsidian-border"></i>
              <p>No active investigation. Launch one on the left, or select a past case to replay its trace.</p>
            </div>
          </div>
        </div>

        <!-- Tab Content: Article -->
        <div id="tab-article" class="tab-pane hidden flex-1 pt-4 overflow-y-auto max-h-[500px]">
          <pre id="article-markdown" class="text-xs font-sans whitespace-pre-wrap text-text-secondary leading-relaxed bg-obsidian/50 p-4 rounded-xl border border-obsidian-border/50">
No case selected. Choose an investigation on the left to read the forensic audit.
          </pre>
        </div>

        <!-- Tab Content: Video -->
        <div id="tab-video" class="tab-pane hidden flex-1 pt-4 flex flex-col items-center justify-center">
          <div id="video-container" class="w-full max-w-xs aspect-[9/16] bg-black rounded-2xl border border-obsidian-border overflow-hidden flex items-center justify-center">
            <p class="text-xs text-text-muted font-mono p-4 text-center">Select a case with a rendered reel</p>
          </div>
          <div class="mt-4 w-full max-w-xs">
            <button id="btn-generate-video-step" class="w-full py-2.5 rounded-xl bg-cyan-consensus/20 hover:bg-cyan-consensus/30 text-cyan-consensus border border-cyan-consensus/40 text-xs font-mono font-bold flex items-center justify-center gap-2">
              <i class="fa-solid fa-clapperboard"></i>
              <span>Step 2: Generate Video Reel for this Case</span>
            </button>
          </div>
        </div>

        <!-- Tab Content: Publish -->
        <div id="tab-publish" class="tab-pane hidden flex-1 pt-6 space-y-4">
          <div class="p-4 rounded-xl bg-obsidian/60 border border-obsidian-border text-xs font-mono space-y-3">
            <h4 class="font-bold text-text-primary text-sm">Step 3: Publish to Cloudflare Edge</h4>
            <p class="text-text-secondary">This will sync the audited markdown, regulatory receipts, and embedded video into <code class="text-emerald-audit">web/src/content/articles/</code> and deploy to Cloudflare.</p>
            <div>
              <label class="text-text-muted block mb-1">Optional YouTube Video ID (Override or Pre-uploaded):</label>
              <input id="input-yt-id" type="text" placeholder="e.g. dQw4w9WgXcQ (leave blank to auto-upload)" class="w-full bg-obsidian border border-obsidian-border rounded-lg px-3 py-2 text-text-primary text-xs" />
            </div>
            <div class="space-y-2 pt-1">
              <div class="flex items-center gap-2">
                <input id="check-yt-upload" type="checkbox" checked class="rounded bg-obsidian border-obsidian-border text-emerald-audit" />
                <label for="check-yt-upload" class="text-text-secondary cursor-pointer">Auto-upload video reel to YouTube if credentials exist (otherwise hosts on Cloudflare)</label>
              </div>
              <div class="flex items-center gap-2">
                <input id="check-deploy" type="checkbox" checked class="rounded bg-obsidian border-obsidian-border text-emerald-audit" />
                <label for="check-deploy" class="text-text-secondary cursor-pointer">Build and Deploy to Cloudflare Workers Static Assets immediately</label>
              </div>
            </div>
          </div>

          <button id="btn-publish-submit" class="w-full py-3 rounded-xl bg-emerald-audit text-black font-bold text-sm shadow-glowEmerald hover:bg-emerald-300 transition-all flex items-center justify-center gap-2">
            <i class="fa-solid fa-cloud-arrow-up"></i>
            <span>Approve & Publish to Cloudflare Edge</span>
          </button>

          <div id="publish-outcome" class="hidden p-4 rounded-xl bg-obsidian-subtle border border-emerald-audit/40 text-xs font-mono"></div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let activeCaseId = null;
    let activeEvents = [];
    let activeFilter = 'all';
    let lastEventSeq = 0;
    let liveEventsTimer = null;

    function escapeHtml(str) {
      if (str === null || str === undefined) return '';
      if (typeof str !== 'string') {
        try { str = JSON.stringify(str, null, 2); } catch (_) { str = String(str); }
      }
      return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(btn => {
        if (btn.getAttribute('data-tab') === tabId) {
          btn.classList.remove('border-transparent', 'text-text-muted');
          btn.classList.add('border-emerald-audit', 'text-emerald-audit', 'font-semibold');
        } else {
          btn.classList.remove('border-emerald-audit', 'text-emerald-audit', 'font-semibold');
          btn.classList.add('border-transparent', 'text-text-muted');
        }
      });
      document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.add('hidden'));
      const activePane = document.getElementById(tabId);
      if (activePane) activePane.classList.remove('hidden');
    }

    // Canonical pipeline stages per PIPELINE_ARCHITECTURE.md:
    // 1 Plan & Discovery (planner) -> 2 Research Loop (executor) -> 3 Ingestion (ingest)
    // -> 4 Reflection (reflect) -> 5 Governance & Verdict (diligence) -> Memo & media render
    const STAGE_COLORS = {
      planner: '#F59E0B',
      executor: '#3DDBA5',
      ingest: '#22D3EE',
      reflect: '#8B7CF6',
      diligence: '#F5C542',
      complete: '#3DDBA5',
      failed: '#F87171'
    };
    const STAGE_ORDER = ['planner', 'executor', 'ingest', 'reflect', 'diligence'];

    function canonicalStage(stage) {
      const s = (stage || '').toLowerCase();
      if (s.includes('scout') || s.includes('plan')) return 'planner';
      if (s.includes('exec') || s.includes('tool')) return 'executor';
      if (s.includes('ingest')) return 'ingest';
      if (s.includes('reflect')) return 'reflect';
      if (s.includes('dilig') || s.includes('gate') || s.includes('committee') || s.includes('synth') || s.includes('verdict')) return 'diligence';
      if (s.includes('article') || s.includes('reel') || s.includes('video') || s.includes('complete')) return 'complete';
      if (s.includes('fail')) return 'failed';
      return '';
    }

    function stageColor(stage) {
      const c = canonicalStage(stage);
      if (c && STAGE_COLORS[c]) return STAGE_COLORS[c];
      return '#7D8590';
    }

    function stageNumber(stage) {
      const c = canonicalStage(stage);
      const idx = STAGE_ORDER.indexOf(c);
      return idx; // -1 for unknown/complete/failed
    }

    function updateStepper(stage) {
      const c = canonicalStage(stage);
      const isComplete = c === 'complete';
      const isFailed = c === 'failed';
      const currentIndex = STAGE_ORDER.indexOf(c); // -1 unless a canonical stage

      const nodes = document.querySelectorAll('.step-node');
      const labels = document.querySelectorAll('.step-label');
      const rail = document.getElementById('trace-rail-progress');

      nodes.forEach((node, idx) => {
        const color = STAGE_COLORS[STAGE_ORDER[idx]];
        if (isFailed) {
          node.style.borderColor = STAGE_COLORS.failed;
          node.style.background = idx === 0 ? STAGE_COLORS.failed : '#151A20';
          node.classList.remove('animate-pulse');
        } else if (isComplete || (currentIndex !== -1 && idx < currentIndex)) {
          node.style.borderColor = color;
          node.style.background = color;
          node.classList.remove('animate-pulse');
        } else if (currentIndex !== -1 && idx === currentIndex) {
          node.style.borderColor = color;
          node.style.background = color;
          node.classList.add('animate-pulse');
        } else {
          node.style.borderColor = '#1E2638';
          node.style.background = '#151A20';
          node.classList.remove('animate-pulse');
        }
      });

      labels.forEach((label, idx) => {
        const color = STAGE_COLORS[STAGE_ORDER[idx]];
        if (idx === currentIndex && !isComplete && !isFailed) {
          label.style.color = color;
          label.classList.add('font-bold');
        } else if (isComplete || (currentIndex !== -1 && idx < currentIndex)) {
          label.style.color = '#A8B1BC';
          label.classList.remove('font-bold');
        } else {
          label.style.color = '#7D8590';
          label.classList.remove('font-bold');
        }
      });

      if (rail) {
        const pct = isComplete ? 100 : (currentIndex <= 0 ? 0 : (currentIndex / (STAGE_ORDER.length - 1)) * 100);
        rail.style.width = `${pct}%`;
      }
    }

    // Chat-style agent identity map for the trace stream
    const AGENT_PROFILE = {
      llm_thinking: { name: 'Reasoning', icon: 'fa-brain', color: '#A78BFA', bg: 'rgba(139,124,246,0.14)' },
      llm_start: { name: 'Model Turn', icon: 'fa-paper-plane', color: '#A78BFA', bg: 'rgba(139,124,246,0.14)' },
      llm_response: { name: 'Decision', icon: 'fa-comment-dots', color: '#22D3EE', bg: 'rgba(34,211,238,0.13)' },
      tool_call: { name: 'Tool Call', icon: 'fa-screwdriver-wrench', color: '#3DDBA5', bg: 'rgba(61,219,165,0.13)' },
      tool_result: { name: 'Tool Output', icon: 'fa-inbox', color: '#8B949E', bg: 'rgba(139,148,158,0.12)' },
      gate: { name: 'Quant Gate', icon: 'fa-filter', color: '#F59E0B', bg: 'rgba(245,158,11,0.14)' },
      stage: { name: 'Pipeline', icon: 'fa-flag-checkered', color: '#F5C542', bg: 'rgba(245,197,66,0.12)' },
      log: { name: 'Log', icon: 'fa-terminal', color: '#8B949E', bg: 'rgba(139,148,158,0.10)' }
    };

    function shortArgs(inputs) {
      if (inputs === null || inputs === undefined) return '';
      if (typeof inputs === 'string') return inputs;
      try {
        const parts = [];
        for (const [k, v] of Object.entries(inputs)) {
          const s = typeof v === 'string' ? v : JSON.stringify(v);
          parts.push(`${k}=${s.length > 80 ? s.slice(0, 77) + '…' : s}`);
        }
        return parts.join('  ·  ');
      } catch (_) {
        return JSON.stringify(inputs);
      }
    }

    function createEventCard(event) {
      const type = event.event_type || 'log';
      const stage = event.stage || '';
      const stageHex = stageColor(stage);
      const time = event.timestamp ? event.timestamp.slice(11, 19) : '';
      const payload = event.payload || {};
      const title = event.title || type;
      const profile = AGENT_PROFILE[type] || AGENT_PROFILE.log;

      const isThought = type === 'llm_thinking';
      const isError = type === 'tool_result' && payload.status === 'error';

      // Stage transitions render as centered divider chips
      if (type === 'stage') {
        const html = `
          <div class="event-card event-stage flex items-center gap-3 py-1.5 my-1" data-filter="stage">
            <div class="h-px flex-1 bg-obsidian-border"></div>
            <div class="flex items-center gap-2 px-3 py-1 rounded-full border bg-obsidian-card" style="border-color:${stageHex}44">
              <span class="w-1.5 h-1.5 rounded-full" style="background:${stageHex}"></span>
              <span class="text-[10px] font-bold uppercase tracking-[0.12em]" style="color:${stageHex}">${escapeHtml(title)}</span>
            </div>
            <span class="text-[10px] font-mono text-text-muted">${time}</span>
            <div class="h-px flex-1 bg-obsidian-border"></div>
          </div>`;
        return htmlToNode(html);
      }

      // Quiet single-line logs
      if (type === 'log') {
        const html = `
          <div class="event-card event-log flex items-center gap-2 py-1 px-1" data-filter="log">
            <span class="w-4 text-center text-[9px] text-text-muted"><i class="fa-solid fa-terminal"></i></span>
            <span class="flex-1 truncate text-[11px] text-text-muted">${escapeHtml(title)}</span>
            <span class="text-[10px] font-mono text-text-muted/60">${time}</span>
          </div>`;
        return htmlToNode(html);
      }

      const avatar = `
        <div class="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] shrink-0" style="background:${profile.bg};color:${profile.color}">
          <i class="fa-solid ${profile.icon}"></i>
        </div>`;

      let body = '';

      if (isThought) {
        body = `
          <div class="event-body rounded-lg border border-purple-400/25 bg-purple-500/[0.06]">
            <button class="think-toggle w-full flex items-center gap-2 px-3 py-2 text-left" onclick="toggleThink(this)">
              <i class="fa-solid fa-chevron-right text-[9px] text-purple-300/70 transition-transform"></i>
              <span class="text-[10px] font-semibold text-purple-300/90">Show reasoning</span>
              <span class="ml-auto text-[9px] font-mono text-purple-300/50">${(payload.thinking || '').length} chars</span>
            </button>
            <div class="think-content hidden px-3 pb-2.5 text-[11px] leading-relaxed text-purple-100/85 whitespace-pre-wrap max-h-60 overflow-y-auto">${escapeHtml(payload.thinking || '')}</div>
          </div>`;
      } else if (type === 'tool_call') {
        const ticker = payload.ticker ? `<span class="px-1.5 py-0.5 rounded font-bold text-[10px]" style="background:rgba(61,219,165,0.15);color:#3DDBA5">$${escapeHtml(payload.ticker)}</span>` : '';
        const args = shortArgs(payload.inputs);
        body = `
          <div class="event-body rounded-lg border border-emerald-400/25 bg-emerald-500/[0.05]">
            <div class="flex items-center gap-2 px-3 py-2 flex-wrap">
              <span class="text-[11px] font-bold font-mono text-emerald-300">${escapeHtml(payload.tool || title)}</span>
              ${ticker}
              ${args ? `<span class="text-[10px] font-mono text-text-muted truncate max-w-[340px]" title="${escapeHtml(args)}">${escapeHtml(args)}</span>` : ''}
            </div>
          </div>`;
      } else if (type === 'tool_result') {
        const badge = isError
          ? '<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/15 text-amber-warning border border-amber-500/30">ERROR</span>'
          : '<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-500/15 text-emerald-audit border border-emerald-500/30">OK</span>';
        const text = payload.error || payload.output_preview || '';
        body = `
          <div class="event-body rounded-lg border ${isError ? 'border-amber-400/30 bg-amber-500/[0.05]' : 'border-obsidian-border bg-obsidian/60'}">
            <div class="flex items-center gap-2 px-3 py-1.5">
              <span class="text-[10px] font-semibold text-text-secondary">Returned</span>
              ${badge}
              <span class="ml-auto text-[9px] font-mono text-text-muted">${(text || '').length} chars</span>
            </div>
            <div class="px-3 pb-2.5 text-[10px] font-mono text-text-secondary whitespace-pre-wrap max-h-40 overflow-y-auto leading-relaxed">${escapeHtml(text)}</div>
          </div>`;
      } else if (type === 'llm_response') {
        const calls = (payload.tool_calls || []).map(c =>
          `<span class="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold" style="background:rgba(34,211,238,0.13);color:#22D3EE">${escapeHtml(c)}</span>`
        ).join(' ');
        const preview = payload.content_preview
          ? `<div class="text-[11px] leading-relaxed text-text-secondary whitespace-pre-wrap max-h-44 overflow-y-auto">${escapeHtml(payload.content_preview)}</div>`
          : '';
        body = `
          <div class="event-body rounded-lg border border-cyan-400/20 bg-cyan-500/[0.05] px-3 py-2.5 space-y-1.5">
            ${preview}
            ${calls ? `<div class="flex items-center gap-1.5 flex-wrap"><span class="text-[9px] uppercase tracking-wider text-text-muted font-semibold">Dispatch</span>${calls}</div>` : ''}
          </div>`;
      } else if (type === 'gate') {
        const shortlisted = (payload.shortlisted || []).map(t =>
          `<span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500/15 text-amber-warning border border-amber-500/30">$${escapeHtml(t)}</span>`
        ).join(' ');
        body = `
          <div class="event-body rounded-lg border border-amber-400/30 bg-amber-500/[0.08] px-3 py-2.5 space-y-2">
            <div class="flex items-center gap-2">
              <span class="text-[11px] font-bold text-amber-300 font-mono"><i class="fa-solid fa-filter mr-1.5"></i>${escapeHtml(title)}</span>
            </div>
            ${shortlisted ? `<div class="flex items-center gap-1.5 flex-wrap pt-1"><span class="text-[9px] uppercase tracking-wider text-text-muted font-semibold">Shortlist:</span>${shortlisted}</div>` : ''}
          </div>`;
      } else {
        body = `
          <div class="event-body rounded-lg border border-obsidian-border bg-obsidian/50 px-3 py-2 text-[11px] text-text-secondary">
            ${escapeHtml(title)}
          </div>`;
      }

      const html = `
        <div class="event-card event-${type} flex gap-2.5 py-1.5" data-filter="${type}">
          ${avatar}
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-[10px] font-bold uppercase tracking-wider" style="color:${profile.color}">${profile.name}</span>
              <span class="text-[9px] font-mono px-1.5 rounded" style="color:${stageHex};background:${stageHex}1A">${escapeHtml(stage || 'run')}</span>
              <span class="ml-auto text-[9px] font-mono text-text-muted">${time}</span>
            </div>
            ${body}
          </div>
        </div>`;
      return htmlToNode(html);
    }

    function htmlToNode(html) {
      const wrapper = document.createElement('div');
      wrapper.innerHTML = html.trim();
      return wrapper.firstElementChild;
    }

    function toggleThink(btn) {
      const content = btn.nextElementSibling;
      const icon = btn.querySelector('i');
      const label = btn.querySelector('span');
      content.classList.toggle('hidden');
      const isOpen = !content.classList.contains('hidden');
      if (icon) icon.style.transform = isOpen ? 'rotate(90deg)' : 'rotate(0deg)';
      if (label) label.textContent = isOpen ? 'Hide reasoning' : 'Show reasoning';
    }

    function applyFilter(filter) {
      activeFilter = filter;
      document.querySelectorAll('#trace-filter-group .filter-btn').forEach(btn => {
        if (btn.getAttribute('data-filter') === filter) {
          btn.className = 'filter-btn px-2.5 py-1 rounded-lg bg-emerald-audit/20 text-emerald-audit border border-emerald-audit/40 font-semibold';
        } else {
          btn.className = 'filter-btn px-2.5 py-1 rounded-lg bg-obsidian text-text-muted border border-obsidian-border hover:text-text-primary';
        }
      });

      const cards = document.querySelectorAll('#trace-events-stream .event-card');
      cards.forEach(card => {
        if (filter === 'all' || card.classList.contains(`event-${filter}`)) {
          card.classList.remove('hidden');
        } else {
          card.classList.add('hidden');
        }
      });
    }

    // DOM cap: keep the stream fast during very long runs (backend ledger keeps full history)
    const TRACE_DOM_CAP = 350;

    function renderEvents(events, append = true) {
      const container = document.getElementById('trace-events-stream');
      if (!append || !activeEvents.length) {
        container.innerHTML = '';
      }

      if (!events.length && !activeEvents.length) {
        container.innerHTML = '<div class="text-center text-text-muted py-12"><i class="fa-solid fa-terminal text-2xl mb-2 text-obsidian-border"></i><p>No model execution events recorded yet.</p></div>';
        return;
      }

      events.forEach(ev => {
        let card;
        try {
          card = createEventCard(ev);
        } catch (err) {
          console.error('Trace render error on event', ev && ev.seq, err);
          return;
        }
        if (!card) return;
        if (activeFilter !== 'all' && !card.classList.contains(`event-${activeFilter}`)) {
          card.classList.add('hidden');
        }
        container.appendChild(card);
      });

      // Trim oldest nodes when over the render cap
      while (container.childElementCount > TRACE_DOM_CAP) {
        container.removeChild(container.firstElementChild);
      }

      document.getElementById('trace-event-counter').textContent = `${activeEvents.length} events`;

      // Stage banner should follow the most recent stage transition, not just the newest event
      let stageEvent = null;
      for (let i = activeEvents.length - 1; i >= 0; i--) {
        if (activeEvents[i].event_type === 'stage') { stageEvent = activeEvents[i]; break; }
      }
      if (stageEvent) {
        document.getElementById('trace-current-stage-title').textContent = stageEvent.title || stageEvent.stage;
        updateStepper(stageEvent.stage);
      }

      const autoscroll = document.getElementById('check-autoscroll').checked;
      if (autoscroll) {
        container.scrollTop = container.scrollHeight;
      }
    }

    async function fetchCases() {
      try {
        const res = await fetch('/api/cases');
        const data = await res.json();
        renderCasesList(data.cases);
        if (data.job) {
          const badge = document.getElementById('job-status-text');
          badge.textContent = data.job.status;
          const pulse = document.getElementById('trace-pulse-dot');
          if (data.job.status === 'running' || data.job.status === 'rendering_video') {
            pulse.classList.remove('hidden');
            startLiveEventStream();
          } else {
            pulse.classList.add('hidden');
          }
        }
      } catch (err) {
        console.error('Failed to load cases', err);
      }
    }

    function renderCasesList(cases) {
      const container = document.getElementById('cases-list');
      if (!cases.length) {
        container.innerHTML = '<div class="text-text-muted text-center py-6">No cases generated yet.</div>';
        return;
      }

      container.innerHTML = cases.map(c => `
        <div onclick="selectCase('${c.case_id}')" class="p-3 rounded-xl bg-obsidian/60 hover:bg-obsidian-subtle border border-obsidian-border hover:border-emerald-audit/40 cursor-pointer transition-all ${activeCaseId === c.case_id ? 'border-emerald-audit bg-emerald-audit/10' : ''}">
          <div class="flex items-center justify-between mb-1">
            <span class="font-bold text-text-primary">$${c.ticker}</span>
            <div class="flex items-center gap-1.5 text-[10px]">
              ${c.has_video ? '<span class="text-emerald-audit bg-emerald-audit/10 px-1.5 py-0.5 rounded">Reel</span>' : '<span class="text-text-muted bg-obsidian px-1.5 py-0.5 rounded">Article</span>'}
            </div>
          </div>
          <p class="text-text-secondary truncate text-[11px]">${c.title}</p>
          <span class="text-[10px] text-text-muted">${c.case_id}</span>
        </div>
      `).join('');
    }

    async function selectCase(caseId) {
      activeCaseId = caseId;
      document.getElementById('active-case-title').textContent = caseId;
      fetchCases();

      try {
        const res = await fetch(`/api/case/${caseId}`);
        const data = await res.json();

        // Populate article preview
        document.getElementById('article-markdown').textContent = data.article || 'No article.md found';

        // Populate video tab
        const vContainer = document.getElementById('video-container');
        if (data.has_video) {
          vContainer.innerHTML = `<video class="w-full h-full object-cover" controls playsinline src="/api/video/${caseId}"></video>`;
        } else {
          vContainer.innerHTML = `<div class="p-4 text-center text-xs text-text-muted font-mono">No video reel rendered yet. Click below to render Stage 2.</div>`;
        }
      } catch (err) {
        console.error('Failed to load case', err);
      }

      // Load case events for model trace inspection
      try {
        const evRes = await fetch(`/api/case/${caseId}/events`);
        const evData = await evRes.json();
        if (evData.events && evData.events.length) {
          activeEvents = evData.events;
          lastEventSeq = activeEvents.length;
          renderEvents(activeEvents, false);
        } else {
          activeEvents = [];
          lastEventSeq = 0;
          renderEvents([], false);
        }
      } catch (err) {
        console.debug('No historical events for case', err);
      }
    }

    function startLiveEventStream() {
      if (liveEventsTimer) return;
      liveEventsTimer = setInterval(async () => {
        try {
          const res = await fetch(`/api/job-events?since=${lastEventSeq}`);
          const data = await res.json();
          if (data.events && data.events.length) {
            data.events.forEach(ev => activeEvents.push(ev));
            lastEventSeq = data.next_seq;
            renderEvents(data.events, true);
          }
          if (data.status === 'completed' || data.status === 'failed') {
            stopLiveEventStream();
            fetchCases();
            if (data.case_id) selectCase(data.case_id);
          }
        } catch (err) {
          console.debug('Polling job events error', err);
        }
      }, 600);
    }

    function stopLiveEventStream() {
      if (liveEventsTimer) {
        clearInterval(liveEventsTimer);
        liveEventsTimer = null;
      }
      document.getElementById('trace-pulse-dot').classList.add('hidden');
    }

    // Tabs switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.getAttribute('data-tab');
        switchTab(target);
      });
    });

    // Trace filter toolbar
    document.querySelectorAll('#trace-filter-group .filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const filter = btn.getAttribute('data-filter');
        applyFilter(filter);
      });
    });

    // Clear trace screen
    document.getElementById('btn-clear-trace').addEventListener('click', () => {
      activeEvents = [];
      lastEventSeq = 0;
      renderEvents([], false);
    });

    // Run Stage 1 (Article only)
    document.getElementById('btn-run-article').addEventListener('click', async () => {
      let ticker = (document.getElementById('input-ticker').value || '').trim();
      let query = (document.getElementById('input-query').value || '').trim();
      const duo = document.getElementById('input-duo').value;
      const depth = document.getElementById('input-depth').value;

      // Auto-route conversational prompts or multi-word sentences to query
      if (ticker && (ticker.includes(' ') || ticker.length > 10)) {
        query = query ? `${ticker} — ${query}` : ticker;
        ticker = '';
      }

      activeEvents = [];
      lastEventSeq = 0;
      renderEvents([], false);
      switchTab('tab-trace');
      document.getElementById('trace-pulse-dot').classList.remove('hidden');

      await fetch('/api/run-research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, query, character_pair: duo, depth, with_video: false })
      });
      startLiveEventStream();
      fetchCases();
    });

    // Run One-Shot (Article + Video)
    document.getElementById('btn-run-all').addEventListener('click', async () => {
      let ticker = (document.getElementById('input-ticker').value || '').trim();
      let query = (document.getElementById('input-query').value || '').trim();
      const duo = document.getElementById('input-duo').value;
      const depth = document.getElementById('input-depth').value;

      // Auto-route conversational prompts or multi-word sentences to query
      if (ticker && (ticker.includes(' ') || ticker.length > 10)) {
        query = query ? `${ticker} — ${query}` : ticker;
        ticker = '';
      }

      activeEvents = [];
      lastEventSeq = 0;
      renderEvents([], false);
      switchTab('tab-trace');
      document.getElementById('trace-pulse-dot').classList.remove('hidden');

      await fetch('/api/run-research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, query, character_pair: duo, depth, with_video: true })
      });
      startLiveEventStream();
      fetchCases();
    });

    // Generate video for selected case
    document.getElementById('btn-generate-video-step').addEventListener('click', async () => {
      if (!activeCaseId) return alert('Select a case first');
      const duo = document.getElementById('input-duo').value;

      activeEvents = [];
      lastEventSeq = 0;
      renderEvents([], false);
      switchTab('tab-trace');
      document.getElementById('trace-pulse-dot').classList.remove('hidden');

      await fetch('/api/run-video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_id: activeCaseId, character_pair: duo })
      });
      startLiveEventStream();
      fetchCases();
    });

    // Publish button
    document.getElementById('btn-publish-submit').addEventListener('click', async () => {
      if (!activeCaseId) return alert('Select a case first');
      const ytId = document.getElementById('input-yt-id').value;
      const ytUpload = document.getElementById('check-yt-upload').checked;
      const deploy = document.getElementById('check-deploy').checked;

      const outcome = document.getElementById('publish-outcome');
      outcome.classList.remove('hidden');
      outcome.innerHTML = '<span class="text-cyan-consensus">Syncing to Astro & Deploying to Cloudflare...</span>';

      try {
        const res = await fetch('/api/publish', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ case_id: activeCaseId, youtube_id: ytId, youtube_upload: ytUpload, deploy })
        });
        const data = await res.json();
        if (data.success) {
          outcome.innerHTML = `
            <div class="text-emerald-audit font-bold mb-1">✓ Published successfully!</div>
            <div>Synced to: <code class="text-text-primary">${data.target_mdx}</code></div>
            ${data.youtube_id ? `<div>YouTube: <a class="text-emerald-audit underline" href="https://youtube.com/watch?v=${data.youtube_id}" target="_blank">${data.youtube_id}</a></div>` : ''}
            ${data.is_deployed ? `<div class="mt-2 text-cyan-consensus">Live at Cloudflare: <a class="underline" href="${data.deploy_url || '#'}" target="_blank">${data.deploy_url || 'Active'}</a></div>` : ''}
          `;
        } else {
          outcome.innerHTML = `<span class="text-amber-warning">Error: ${data.error}</span>`;
        }
      } catch (err) {
        outcome.innerHTML = `<span class="text-amber-warning">Error: ${err.message}</span>`;
      }
    });

    document.getElementById('btn-refresh').addEventListener('click', fetchCases);
    fetchCases();
  </script>
</body>
</html>
"""


def run_studio(host: str = "127.0.0.1", port: int = 3000) -> None:
    """Start the Local Studio GUI server."""
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, StudioHandler)
    logger.info("MemeTrading Local Studio running at http://%s:%d", host, port)
    print(f"\n🚀 MemeTrading Local Studio is running at: http://{host}:{port}")
    print("Press Ctrl+C to stop the studio.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Local Studio...")
        httpd.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_studio()
