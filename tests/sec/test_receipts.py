"""Tests for server-issued SEC discovery receipts and receipt-bound pull resolution."""
from datetime import date
from app.sec.receipts import SecReceiptStore, get_sec_company_url
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

    # Resolve an accession only when it maps to this store's prior discovery.
    accession_selection = store.resolve_accession_selection("0000789019-26-000001", candidate_id="cand_msft")
    assert accession_selection is not None
    assert accession_selection.document_name == "msft-20260630.htm"
    assert store.resolve_accession_selection("0000789019-26-000001", candidate_id="cand_nvda") is None
    assert store.resolve_accession_selection("0000000000-00-000000", candidate_id="cand_msft") is None

    # Reject non-existent receipt
    assert store.resolve_selection("frec_unknown") is None


def test_get_sec_company_url_resolution():
    """Verify canonical SEC browse URLs use modern 10-digit CIK or classic ticker lookup."""
    # 1. Numeric CIK zero-padded to 10 digits for modern EDGAR entity landing page
    assert get_sec_company_url(ticker="NVDA", cik="1045810") == "https://www.sec.gov/edgar/browse/?CIK=0001045810"
    assert get_sec_company_url(ticker="NVDA", cik=1045810) == "https://www.sec.gov/edgar/browse/?CIK=0001045810"
    assert get_sec_company_url(ticker="INTC", cik="50863") == "https://www.sec.gov/edgar/browse/?CIK=0000050863"

    # 2. Ticker symbol fallback uses classic EDGAR browse endpoint which resolves tickers natively
    assert get_sec_company_url(ticker="NVDA", cik=None) == "https://www.sec.gov/cgi-bin/browse-edgar?CIK=NVDA"
    assert get_sec_company_url(ticker="DELL", cik="") == "https://www.sec.gov/cgi-bin/browse-edgar?CIK=DELL"

    # 3. Ticker mistakenly passed in cik parameter does not generate invalid zero-padded string like 000000NVDA
    assert get_sec_company_url(cik="NVDA") == "https://www.sec.gov/cgi-bin/browse-edgar?CIK=NVDA"

    # 4. Numeric string in ticker treated as CIK
    assert get_sec_company_url(ticker="1045810") == "https://www.sec.gov/edgar/browse/?CIK=0001045810"

    # 5. Missing or unknown identifiers fall back to general company search
    assert get_sec_company_url(ticker="UNKNOWN") == "https://www.sec.gov/edgar/searchedgar/companysearch"
    assert get_sec_company_url(ticker=None, cik=None) == "https://www.sec.gov/edgar/searchedgar/companysearch"

