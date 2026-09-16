"""Red-phase tests for metadata-only SEC filing discovery."""

from datetime import date

from app.sec.acquisition import list_sec_filings


class FakeFiling:
    """Minimal upstream filing metadata; document access is intentionally absent."""

    def __init__(self, form: str, filing_date: str, accession_no: str) -> None:
        """Store fake filing metadata for contract tests."""
        self.form = form
        self.filing_date = filing_date
        self.accession_no = accession_no
        self.url = f"https://www.sec.gov/Archives/{accession_no}-index.html"


class FakeCompany:
    """Minimal Edgartools-compatible company fake."""

    cik = 123456

    def __init__(self, filings: list[FakeFiling]) -> None:
        """Store metadata-only filings."""
        self._filings = filings
        self.calls: list[dict[str, object]] = []

    def get_filings(self, **kwargs):
        """Record metadata-only request and return fixture filings."""
        self.calls.append(kwargs)
        return self._filings


def test_lists_metadata_sorted_newest_first_without_document_access() -> None:
    """Map fake upstream filing metadata without touching document properties."""
    company = FakeCompany(
        [
            FakeFiling("8-K", "2026-08-30", "0000123456-26-000001"),
            FakeFiling("10-Q", "2026-09-01", "0000123456-26-000002"),
        ]
    )

    result = list_sec_filings("xyz", company_factory=lambda ticker: company)

    assert result.error is None
    assert [filing.accession for filing in result.filings] == [
        "0000123456-26-000002",
        "0000123456-26-000001",
    ]
    assert company.calls == [{"form": None, "trigger_full_load": False}]


def test_filters_forms_and_includes_since_date() -> None:
    """Apply normalized form and inclusive local date filters."""
    company = FakeCompany(
        [
            FakeFiling("8-K", "2026-09-01", "0000123456-26-000001"),
            FakeFiling("10-Q", "2026-09-01", "0000123456-26-000002"),
            FakeFiling("8-K", "2026-08-31", "0000123456-26-000003"),
        ]
    )

    result = list_sec_filings(
        "XYZ",
        forms=["8-k"],
        since=date(2026, 9, 1),
        company_factory=lambda ticker: company,
    )

    assert result.error is None
    assert [filing.accession for filing in result.filings] == ["0000123456-26-000001"]
    assert company.calls == [{"form": ["8-K"], "trigger_full_load": False}]


def test_accepts_json_native_iso_since_date() -> None:
    """Accept the ISO date strings emitted by the model-facing tool schema."""
    company = FakeCompany([
        FakeFiling("8-K", "2026-09-01", "0000123456-26-000001"),
        FakeFiling("8-K", "2026-08-31", "0000123456-26-000002"),
    ])
    result = list_sec_filings("XYZ", forms=["8-k"], since="2026-09-01", company_factory=lambda ticker: company)
    assert result.error is None
    assert [filing.accession for filing in result.filings] == ["0000123456-26-000001"]


def test_rejects_malformed_iso_since_date() -> None:
    """Reject invalid JSON date strings before contacting the SEC provider."""
    result = list_sec_filings("XYZ", since="2026/09/01", company_factory=lambda ticker: (_ for _ in ()).throw(AssertionError()))
    assert result.error is not None
    assert result.error.code == "INVALID_INPUT"


def test_returns_structured_invalid_input_failure() -> None:
    """Reject invalid ticker before calling upstream factory."""
    result = list_sec_filings("XYZ!", company_factory=lambda ticker: (_ for _ in ()).throw(AssertionError()))

    assert result.filings == ()
    assert result.error is not None
    assert result.error.code == "INVALID_INPUT"
    assert not result.error.retryable


def test_returns_structured_provider_failure() -> None:
    """Translate provider failure without leaking exception details."""
    def unavailable_factory(ticker: str):
        """Simulate a transient upstream SEC provider failure."""
        raise ConnectionError("provider unavailable")

    result = list_sec_filings("XYZ", company_factory=unavailable_factory)

    assert result.filings == ()
    assert result.error is not None
    assert result.error.code == "UNAVAILABLE"
    assert result.error.retryable


def test_returns_not_found_when_company_has_no_cik() -> None:
    """Reject an unresolved upstream company before filing enumeration."""
    company = FakeCompany([])
    company.cik = None

    result = list_sec_filings("XYZ", company_factory=lambda ticker: company)

    assert result.error is not None
    assert result.error.code == "NOT_FOUND"


def test_returns_malformed_upstream_for_incomplete_filing() -> None:
    """Translate incomplete upstream metadata into a recoverable failure."""
    filing = FakeFiling("8-K", "2026-09-01", "0000123456-26-000001")
    filing.url = ""

    result = list_sec_filings("XYZ", company_factory=lambda ticker: FakeCompany([filing]))

    assert result.error is not None
    assert result.error.code == "MALFORMED_UPSTREAM"
