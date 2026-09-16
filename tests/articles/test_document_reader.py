"""Tests for document reader URL validation and safe argument handling."""
from app.articles.document_reader import read_document


def test_read_document_rejects_credentials_in_url():
    """Verify embedded username and password in URL are rejected."""
    res = read_document("https://user:pass@example.com/doc.pdf")
    assert res["status"] == "error"
    assert "user credentials" in res["message"].lower()


def test_read_document_rejects_non_http_schemes():
    """Verify non-HTTP/HTTPS URLs are rejected."""
    res = read_document("ftp://example.com/doc.pdf")
    assert res["status"] == "error"
    assert "http://" in res["message"]


def test_read_document_handles_empty_or_invalid_inputs():
    """Verify empty or non-string URLs fail gracefully."""
    res1 = read_document("")
    assert res1["status"] == "error"
    res2 = read_document(None)
    assert res2["status"] == "error"
