"""Multi-format primary document reader supporting PDF presentations, reports, and HTML.

Uses pdfplumber for born-digital PDFs and tables, trafilatura for HTML text extraction,
and BeautifulSoup for harvesting investor document / presentation / PDF download links.
Always returns structured receipts with cryptographic digests for durable research ledgers.
"""
from __future__ import annotations

from hashlib import sha256
import io
import logging
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 MemeResearch/1.0"
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024  # 25 MiB ceiling
MAX_RETURN_CHARACTERS = 15000


def _fetch_bytes(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> tuple[bytes, str]:
    """Fetch raw document bytes and detected Content-Type header."""
    req = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as response:
        content_type = str(response.headers.get("Content-Type", "")).lower()
        raw_body = response.read(MAX_DOCUMENT_BYTES + 1)
        encoding = str(response.headers.get("Content-Encoding", "")).lower()

    if "gzip" in encoding or raw_body.startswith(b"\x1f\x8b"):
        import gzip
        try:
            body = gzip.decompress(raw_body)
        except Exception:
            body = raw_body
    else:
        body = raw_body

    if len(body) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"Document exceeds maximum size of {MAX_DOCUMENT_BYTES} bytes")
    return body, content_type


def _extract_pdf(body: bytes, max_pages: int = 20) -> tuple[str, list[list[list[str]]], int]:
    """Extract visible text and structured tables from PDF bytes using pdfplumber."""
    import pdfplumber

    page_texts: list[str] = []
    all_tables: list[list[list[str]]] = []
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        total_pages = len(pdf.pages)
        pages_to_process = min(total_pages, max_pages)
        for i in range(pages_to_process):
            page = pdf.pages[i]
            text = page.extract_text() or ""
            if text.strip():
                page_texts.append(f"--- Page {i + 1} ---\n{text.strip()}")
            tables = page.extract_tables() or []
            for t in tables:
                clean_table = [[str(c or "").strip() for c in row] for row in t if any(row)]
                if clean_table:
                    all_tables.append(clean_table)

    combined_text = "\n\n".join(page_texts)
    return combined_text, all_tables, pages_to_process


def _extract_html(body: bytes, url: str) -> str:
    """Extract clean content from HTML text using trafilatura."""
    from trafilatura import extract
    try:
        decoded = body.decode("utf-8")
    except UnicodeDecodeError:
        decoded = body.decode("latin-1")
    extracted = extract(decoded, url=url, favor_recall=True)
    if extracted and extracted.strip():
        return extracted.strip()
    return " ".join(decoded.split())[:MAX_RETURN_CHARACTERS]


def _extract_document_links(body: bytes, base_url: str, max_links: int = 20) -> list[dict[str, Any]]:
    """Harvest document, presentation, PDF, and report links from HTML pages."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(body, "html.parser")
    except Exception:
        return []

    discovered: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    doc_extensions = (".pdf", ".xlsx", ".xls", ".csv", ".docx", ".pptx")
    doc_keywords = (
        "/investor", "/financial", "/report", "/earnings", "/sec", "/presentation",
        "/deck", "/transcript", "/shareholder", "/filing", "/quarterly", "/annual"
    )

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue

        text = (a.get_text(strip=True) or a.get("title") or "").strip()
        lower_url = full_url.lower()
        lower_text = text.lower()

        is_doc = any(lower_url.endswith(ext) or (ext + "?") in lower_url for ext in doc_extensions)
        is_ir_link = any(kw in lower_url for kw in doc_keywords) or any(
            kw in lower_text for kw in ("pdf", "presentation", "earnings", "transcript", "10-k", "10-q", "report", "deck", "slide", "letter")
        )

        if is_doc or is_ir_link:
            seen_urls.add(full_url)
            discovered.append({
                "title": text[:120] if text else "Document Link",
                "url": full_url,
                "is_pdf": lower_url.endswith(".pdf") or ".pdf?" in lower_url,
            })
            if len(discovered) >= max_links:
                break

    return discovered


def read_document(
    url: str,
    candidate_id: str | None = None,
    max_pages: int = 20,
) -> dict[str, Any]:
    """Read an authoritative primary document (PDF deck, earnings release, HTML report).

    When reading an HTML landing or IR page, automatically extracts both visible text
    and discovered document/PDF download links so the agent can explore linked files.

    Args:
        url: Valid HTTP or HTTPS URL to the document.
        candidate_id: Optional registered candidate identifier.
        max_pages: Maximum number of PDF pages to parse (default 20).

    Returns:
        Structured document receipt with text, tables, discovered links, and metadata.
    """
    if not url or not isinstance(url, str):
        return {"status": "error", "message": "url must be a non-empty string"}

    clean_url = url.strip()
    parsed = urlparse(clean_url)
    if parsed.scheme not in ("http", "https"):
        return {"status": "error", "message": "url must start with http:// or https://"}
    if parsed.username or parsed.password:
        return {"status": "error", "message": "URL must not contain embedded user credentials"}

    effective_max_pages = max(1, min(int(max_pages or 20), 50))

    try:
        body, content_type = _fetch_bytes(clean_url)
        content_hash = sha256(body).hexdigest()
        is_pdf = "pdf" in content_type or clean_url.lower().endswith(".pdf") or body.startswith(b"%PDF")

        if is_pdf:
            text, tables, pages_read = _extract_pdf(body, max_pages=effective_max_pages)
            return {
                "status": "ok",
                "url": clean_url,
                "content_type": "application/pdf",
                "pages_read": pages_read,
                "character_count": len(text),
                "text": text[:MAX_RETURN_CHARACTERS],
                "text_truncated": len(text) > MAX_RETURN_CHARACTERS,
                "tables": tables[:5],
                "discovered_documents": [],
                "content_sha256": content_hash,
                "candidate_id": candidate_id,
            }
        else:
            text = _extract_html(body, clean_url)
            discovered_links = _extract_document_links(body, clean_url)
            return {
                "status": "ok",
                "url": clean_url,
                "content_type": "text/html",
                "character_count": len(text),
                "text": text[:MAX_RETURN_CHARACTERS],
                "text_truncated": len(text) > MAX_RETURN_CHARACTERS,
                "discovered_documents": discovered_links,
                "content_sha256": content_hash,
                "candidate_id": candidate_id,
            }
    except Exception as exc:
        logger.warning("read_document failed for %s: %s", clean_url, exc)
        return {
            "status": "error",
            "url": clean_url,
            "message": f"read_document error: {exc}",
            "candidate_id": candidate_id,
        }
