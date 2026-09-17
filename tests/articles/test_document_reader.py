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


def test_extract_document_links_filters_governance_and_esg_links():
    """Verify document link extractor drops administrative, board, policy, and ESG links."""
    from app.articles.document_reader import _extract_document_links

    html = b"""
    <html>
      <body>
        <a href="/en-us/investor/corporate-governance/overview">Corporate Governance Overview</a>
        <a href="/en-us/investor/corporate-governance/board-of-directors">Board of Directors</a>
        <a href="/en-us/investor/corporate-governance/policies">Policies & Guidelines</a>
        <a href="/en-us/corporate-responsibility/sustainability-report">Sustainability CSR Report</a>
        <a href="/en-us/investor/earnings/FY26-Q4-Press-Release.pdf">Q4 FY26 Earnings Release (PDF)</a>
        <a href="/financial-results/quarterly-presentation.pptx">Investor Presentation Deck</a>
      </body>
    </html>
    """
    links = _extract_document_links(html, "https://www.microsoft.com")
    urls = [link["url"] for link in links]

    assert any("FY26-Q4-Press-Release.pdf" in u for u in urls)
    assert any("quarterly-presentation.pptx" in u for u in urls)
    assert not any("corporate-governance" in u for u in urls)
    assert not any("board-of-directors" in u for u in urls)
    assert not any("sustainability" in u for u in urls)
