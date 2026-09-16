"""Tests for server-issued SEC discovery receipts and receipt-bound pull resolution."""
from datetime import date
from app.sec.receipts import SecReceiptStore
from app.sec.schemas import FilingMetadata


def test_receipt_store_registers_filings_and_resolves_selection():
    """Verify receipt store issues opaque IDs and resolves valid selections."""
    store = SecReceiptStore()
    filing = FilingMetadata(
        ticker="MSFT",
        cik="789019",
        form="10-K",
        filing_date=date(2026, 7, 30),
        accession="0000789019-26-000001",
        filing_url="https://www.sec.gov/Archives/edgar/data/789019/000078901926000001/msft-20260630.htm",
        primary_document="msft-20260630.htm",
        exhibits=("ex-21.1.htm",),
    )

    receipts = store.register_discovery([filing], candidate_id="cand_msft")
    assert len(receipts) == 1
    rec = receipts[0]
    assert rec.ticker == "MSFT"
    assert rec.filing_receipt_id.startswith("frec_")
    assert len(rec.documents) == 2  # primary + 1 exhibit

    # Resolve primary document
    primary = store.resolve_selection(rec.filing_receipt_id, candidate_id="cand_msft")
    assert primary is not None
    assert primary.document_name == "msft-20260630.htm"
    assert primary.filing.accession == "0000789019-26-000001"

    # Resolve specific exhibit
    exhibit_doc_id = rec.documents[1].document_receipt_id
    exhibit = store.resolve_selection(rec.filing_receipt_id, exhibit_doc_id, candidate_id="cand_msft")
    assert exhibit is not None
    assert exhibit.document_name == "ex-21.1.htm"

    # Reject cross-candidate access
    cross_cand = store.resolve_selection(rec.filing_receipt_id, candidate_id="cand_nvda")
    assert cross_cand is None

    # Reject non-existent receipt
    assert store.resolve_selection("frec_unknown") is None
