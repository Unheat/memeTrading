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
        payload = json.dumps(data).encode("utf-8")
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
                        events_data = json.loads(events_file.read_text(encoding="utf-8"))
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
            ticker = req_data.get("ticker", "").strip()
            query = req_data.get("query", "").strip()
            depth = req_data.get("depth", "deep")
            with_video = bool(req_data.get("with_video", False))
            character_pair = req_data.get("character_pair", "rick_morty")

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
            <label class="text-text-muted block mb-1">Ticker Symbol</label>
            <input id="input-ticker" type="text" placeholder="e.g. AAPL, MSFT, GOOGL" class="w-full bg-obsidian border border-obsidian-border rounded-lg px-3 py-2 text-text-primary focus:border-emerald-audit focus:outline-none uppercase font-bold" />
          </div>

          <div>
            <label class="text-text-muted block mb-1">Research Prompt / Thesis Query</label>
            <textarea id="input-query" rows="2" placeholder="e.g. Audit balance sheet inventory drift, gross margin trajectory, and reverse DCF..." class="w-full bg-obsidian border border-obsidian-border rounded-lg px-3 py-2 text-text-primary focus:border-emerald-audit focus:outline-none"></textarea>
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
          <!-- Stage Progress Stepper Bar -->
          <div class="bg-obsidian/70 border border-obsidian-border rounded-xl p-3 text-[11px] font-mono">
            <div class="flex items-center justify-between text-text-muted mb-1.5">
              <span class="font-bold text-text-primary text-xs uppercase flex items-center gap-1.5">
                <i class="fa-solid fa-diagram-project text-cyan-consensus"></i>
                <span id="trace-current-stage-title">Pipeline Ready</span>
              </span>
              <span id="trace-event-counter" class="text-[10px] px-2 py-0.5 rounded bg-obsidian border border-obsidian-border text-emerald-audit font-bold">0 events</span>
            </div>
            <!-- Visual Pipeline Stage Pills -->
            <div class="grid grid-cols-5 gap-1.5 pt-1 text-center text-[10px]">
              <div id="step-pill-scout" class="py-1 rounded bg-obsidian border border-obsidian-border text-text-muted transition-all">1. Scout</div>
              <div id="step-pill-plan" class="py-1 rounded bg-obsidian border border-obsidian-border text-text-muted transition-all">2. Plan</div>
              <div id="step-pill-execute" class="py-1 rounded bg-obsidian border border-obsidian-border text-text-muted transition-all">3. Tools</div>
              <div id="step-pill-diligence" class="py-1 rounded bg-obsidian border border-obsidian-border text-text-muted transition-all">4. Diligence</div>
              <div id="step-pill-synthesis" class="py-1 rounded bg-obsidian border border-obsidian-border text-text-muted transition-all">5. Synthesis</div>
            </div>
          </div>

          <!-- Controls & Filter Toolbar -->
          <div class="flex items-center justify-between gap-2 text-[11px] font-mono flex-wrap bg-obsidian/40 p-2 rounded-xl border border-obsidian-border/60">
            <div class="flex items-center gap-1.5 overflow-x-auto" id="trace-filter-group">
              <button class="filter-btn px-2.5 py-1 rounded-lg bg-emerald-audit/20 text-emerald-audit border border-emerald-audit/40 font-semibold" data-filter="all">All</button>
              <button class="filter-btn px-2.5 py-1 rounded-lg bg-obsidian text-text-muted border border-obsidian-border hover:text-text-primary" data-filter="llm_thinking">🧠 Thinking</button>
              <button class="filter-btn px-2.5 py-1 rounded-lg bg-obsidian text-text-muted border border-obsidian-border hover:text-text-primary" data-filter="tool_call">🛠️ Calls</button>
              <button class="filter-btn px-2.5 py-1 rounded-lg bg-obsidian text-text-muted border border-obsidian-border hover:text-text-primary" data-filter="tool_result">📥 Returns</button>
              <button class="filter-btn px-2.5 py-1 rounded-lg bg-obsidian text-text-muted border border-obsidian-border hover:text-text-primary" data-filter="llm_response">💬 Response</button>
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

          <!-- Live Event Cards Container -->
          <div id="trace-events-stream" class="flex-1 overflow-y-auto max-h-[460px] space-y-2.5 pr-1 font-mono text-xs">
            <div class="text-center text-text-muted py-12">
              <i class="fa-solid fa-terminal text-2xl mb-2 text-obsidian-border"></i>
              <p>No active investigation running. Launch an investigation on the left or select a past case to inspect its model execution trace.</p>
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

    function updateStepper(stage) {
      const active = (stage || '').toLowerCase();
      const stageMap = [
        { id: 'step-pill-scout', label: '1. Scout' },
        { id: 'step-pill-plan', label: '2. Plan' },
        { id: 'step-pill-execute', label: '3. Tools' },
        { id: 'step-pill-diligence', label: '4. Diligence' },
        { id: 'step-pill-synthesis', label: '5. Synthesis' }
      ];

      let currentIndex = -1;
      if (active.includes('scout')) currentIndex = 0;
      else if (active.includes('plan')) currentIndex = 1;
      else if (active.includes('exec') || active.includes('tool')) currentIndex = 2;
      else if (active.includes('reflect') || active.includes('dilig') || active.includes('gate') || active.includes('committee')) currentIndex = 3;
      else if (active.includes('synth') || active.includes('article') || active.includes('reel') || active.includes('video') || active.includes('complete')) currentIndex = 4;

      stageMap.forEach((s, idx) => {
        const el = document.getElementById(s.id);
        if (!el) return;
        const name = s.label.split('. ')[1];
        if (idx < currentIndex) {
          el.className = 'py-1 rounded bg-emerald-audit/10 border border-emerald-audit/40 text-emerald-audit text-[10px] font-semibold';
          el.innerHTML = `✓ ${name}`;
        } else if (idx === currentIndex) {
          el.className = 'py-1 rounded bg-cyan-consensus/20 border border-cyan-consensus text-cyan-consensus text-[10px] font-bold animate-pulse';
          el.innerHTML = `▶ ${name}`;
        } else {
          el.className = 'py-1 rounded bg-obsidian border border-obsidian-border text-text-muted text-[10px]';
          el.innerHTML = s.label;
        }
      });
    }

    function createEventCard(event) {
      const type = event.event_type || 'log';
      const time = event.timestamp ? event.timestamp.slice(11, 19) : '';
      const payload = event.payload || {};
      const title = event.title || type;

      let cardHtml = '';

      if (type === 'llm_thinking') {
        const thinkingText = payload.thinking || '';
        cardHtml = `
          <div class="event-card event-llm_thinking p-3 rounded-xl bg-purple-950/25 border border-purple-500/40 text-purple-200">
            <div class="flex items-center justify-between mb-1.5">
              <div class="flex items-center gap-2">
                <span class="w-5 h-5 rounded-md bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs">🧠</span>
                <span class="font-bold text-[11px] text-purple-300">Model Reasoning & Thinking Trace</span>
              </div>
              <span class="text-[10px] text-purple-400/70 font-mono">${time}</span>
            </div>
            <div class="text-[11px] font-sans leading-relaxed text-purple-200/90 whitespace-pre-wrap bg-purple-950/40 p-2.5 rounded-lg border border-purple-500/20 max-h-64 overflow-y-auto">
              ${escapeHtml(thinkingText)}
            </div>
          </div>
        `;
      } else if (type === 'tool_call') {
        const ticker = payload.ticker ? `<span class="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold">$${payload.ticker}</span>` : '';
        const inputsJson = JSON.stringify(payload.inputs || {}, null, 2);
        cardHtml = `
          <div class="event-card event-tool_call p-3 rounded-xl bg-emerald-950/20 border border-emerald-500/40 text-emerald-100">
            <div class="flex items-center justify-between mb-1.5">
              <div class="flex items-center gap-2">
                <span class="w-5 h-5 rounded-md bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-xs">🛠️</span>
                <span class="font-bold text-[11px] text-emerald-300">${escapeHtml(title)}</span>
                ${ticker}
              </div>
              <span class="text-[10px] text-emerald-400/70 font-mono">${time}</span>
            </div>
            <pre class="text-[10px] font-mono bg-obsidian/80 p-2 rounded border border-emerald-500/20 text-text-secondary overflow-x-auto max-h-36">${escapeHtml(inputsJson)}</pre>
          </div>
        `;
      } else if (type === 'tool_result') {
        const isError = payload.status === 'error';
        const statusBadge = isError 
          ? '<span class="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-warning border border-amber-500/30 text-[10px] font-bold">ERROR</span>'
          : '<span class="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-audit border border-emerald-500/30 text-[10px] font-bold">OK</span>';
        const text = payload.error || payload.output_preview || '';
        cardHtml = `
          <div class="event-card event-tool_result p-3 rounded-xl ${isError ? 'bg-amber-950/20 border border-amber-500/40 text-amber-200' : 'bg-obsidian-subtle border border-cyan-500/25 text-slate-200'}">
            <div class="flex items-center justify-between mb-1.5">
              <div class="flex items-center gap-2">
                <span class="w-5 h-5 rounded-md ${isError ? 'bg-amber-500/20 text-amber-400' : 'bg-cyan-500/20 text-cyan-400'} flex items-center justify-center text-xs">${isError ? '⚠️' : '📥'}</span>
                <span class="font-bold text-[11px] text-text-primary">${escapeHtml(title)}</span>
                ${statusBadge}
              </div>
              <span class="text-[10px] text-text-muted font-mono">${time}</span>
            </div>
            <div class="text-[10px] font-mono bg-obsidian/90 p-2 rounded border border-obsidian-border max-h-36 overflow-y-auto whitespace-pre-wrap text-text-secondary">
              ${escapeHtml(text)}
            </div>
          </div>
        `;
      } else if (type === 'llm_response') {
        const calls = payload.tool_calls && payload.tool_calls.length ? `<div class="mt-1 text-[10px] text-cyan-300 font-mono">Tools Requested: <span class="font-bold">${payload.tool_calls.join(', ')}</span></div>` : '';
        const preview = payload.content_preview ? `<div class="text-[11px] font-sans leading-relaxed text-cyan-100/90 whitespace-pre-wrap bg-cyan-950/40 p-2.5 rounded-lg border border-cyan-500/20 max-h-48 overflow-y-auto">${escapeHtml(payload.content_preview)}</div>` : '';
        cardHtml = `
          <div class="event-card event-llm_response p-3 rounded-xl bg-cyan-950/20 border border-cyan-500/30 text-cyan-100">
            <div class="flex items-center justify-between mb-1.5">
              <div class="flex items-center gap-2">
                <span class="w-5 h-5 rounded-md bg-cyan-500/20 text-cyan-400 flex items-center justify-center text-xs">💬</span>
                <span class="font-bold text-[11px] text-cyan-300">${escapeHtml(title)}</span>
              </div>
              <span class="text-[10px] text-cyan-400/70 font-mono">${time}</span>
            </div>
            ${preview}
            ${calls}
          </div>
        `;
      } else if (type === 'stage') {
        cardHtml = `
          <div class="event-card event-stage p-2.5 rounded-xl bg-obsidian-card border border-obsidian-border flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-cyan-consensus"></span>
              <span class="font-bold text-[11px] text-text-primary uppercase tracking-wider">${escapeHtml(title)}</span>
            </div>
            <span class="text-[10px] text-text-muted font-mono">${time}</span>
          </div>
        `;
      } else {
        cardHtml = `
          <div class="event-card event-log p-2 rounded-lg bg-obsidian/60 border border-obsidian-border text-[11px] text-text-muted flex items-center justify-between font-mono">
            <span>${escapeHtml(title)}</span>
            <span class="text-[10px] text-text-muted/60">${time}</span>
          </div>
        `;
      }

      const wrapper = document.createElement('div');
      wrapper.innerHTML = cardHtml.trim();
      return wrapper.firstElementChild;
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
        const card = createEventCard(ev);
        if (activeFilter !== 'all' && !card.classList.contains(`event-${activeFilter}`)) {
          card.classList.add('hidden');
        }
        container.appendChild(card);
      });

      document.getElementById('trace-event-counter').textContent = `${activeEvents.length} events`;
      
      const lastEvent = activeEvents[activeEvents.length - 1];
      if (lastEvent) {
        document.getElementById('trace-current-stage-title').textContent = lastEvent.title || lastEvent.stage;
        updateStepper(lastEvent.stage);
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
      const ticker = document.getElementById('input-ticker').value;
      const query = document.getElementById('input-query').value;
      const duo = document.getElementById('input-duo').value;
      const depth = document.getElementById('input-depth').value;

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
      const ticker = document.getElementById('input-ticker').value;
      const query = document.getElementById('input-query').value;
      const duo = document.getElementById('input-duo').value;
      const depth = document.getElementById('input-depth').value;

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
