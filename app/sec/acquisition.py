"""Metadata-only Edgartools adapter for controlled SEC filing discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterable

from app.sec.schemas import FilingMetadata


VALID_ERROR_CODES = frozenset(
    {
        "INVALID_INPUT",
        "NOT_FOUND",
        "UNAVAILABLE",
        "MALFORMED_UPSTREAM",
        "DEPENDENCY_UNAVAILABLE",
    }
)
TICKER_MIN_LENGTH = 1
TICKER_MAX_LENGTH = 10


@dataclass(frozen=True)
class DiscoveryError:
    """Recoverable filing-discovery failure for a future agent-tool boundary.

    Attributes:
        code: Stable error classification.
        message: Safe caller-facing explanation.
        retryable: Whether retrying later may succeed.
    """

    code: str
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        """Validate stable error values.

        Raises:
            ValueError: If error code or message is invalid.
        """
        if self.code not in VALID_ERROR_CODES:
            raise ValueError("error code is invalid")
        if not self.message.strip():
            raise ValueError("error message must not be empty")


@dataclass(frozen=True)
class FilingDiscoveryResult:
    """Normalized metadata-only filing discovery outcome.

    Attributes:
        filings: Newest-first validated filing records on success.
        error: Recoverable failure details, or `None` on success.
    """

    filings: tuple[FilingMetadata, ...]
    error: DiscoveryError | None = None

    def __post_init__(self) -> None:
        """Enforce mutually exclusive success and failure states.

        Raises:
            ValueError: If a failed result also includes filings.
        """
        if self.error is not None and self.filings:
            raise ValueError("failed discovery result must not include filings")


CompanyFactory = Callable[[str], Any]


def _failure(code: str, message: str, retryable: bool) -> FilingDiscoveryResult:
    """Build one structured discovery failure.

    Args:
        code: Stable failure code.
        message: Safe caller-facing failure explanation.
        retryable: Whether a later retry may succeed.

    Returns:
        Empty discovery result containing one validated error.
    """
    return FilingDiscoveryResult((), DiscoveryError(code, message, retryable))


def _normalize_ticker(ticker: str) -> str:
    """Validate and normalize a caller-supplied ticker.

    Args:
        ticker: Candidate ticker text.

    Returns:
        Uppercase alphabetic ticker.

    Raises:
        ValueError: If ticker is not 1–10 alphabetic characters.
    """
    normalized = ticker.strip().upper()
    if not normalized.isalpha() or not TICKER_MIN_LENGTH <= len(normalized) <= TICKER_MAX_LENGTH:
        raise ValueError("ticker must contain 1 to 10 letters")
    return normalized


def _normalize_forms(forms: Iterable[str] | None) -> list[str] | None:
    """Normalize optional SEC form filters.

    Args:
        forms: Optional iterable of non-blank form strings.

    Returns:
        Uppercase form list, or `None` when no filter is requested.

    Raises:
        ValueError: If forms is a string or contains a blank/non-string value.
    """
    if forms is None:
        return None
    if isinstance(forms, str):
        raise ValueError("forms must be an iterable of form strings, not one string")
    normalized = []
    for form in forms:
        if not isinstance(form, str) or not form.strip():
            raise ValueError("forms must contain non-empty strings")
        normalized.append(form.strip().upper())
    return normalized or None


def _normalize_since(since: date | str | None) -> date | None:
    """Normalize direct dates and JSON-native ISO dates at the SEC boundary.

    Args:
        since: Optional ``date`` or ``YYYY-MM-DD`` string.

    Returns:
        A date value, or ``None`` when no lower bound was supplied.

    Raises:
        ValueError: If the supplied value is not a valid ISO date.
    """
    if since is None:
        return None
    if isinstance(since, date):
        return since
    if isinstance(since, str) and since.strip():
        return date.fromisoformat(since.strip())
    raise ValueError("since must be a date or ISO date string")


def _default_company_factory(ticker: str) -> Any:
    """Create Edgartools company lazily for production discovery.

    Args:
        ticker: Valid normalized ticker.

    Returns:
        Edgartools company object.

    Raises:
        ModuleNotFoundError: If optional runtime dependency is not installed.
        Exception: Any Edgartools construction failure for caller translation.
    """
    from app.sec.identity import ensure_sec_identity
    ensure_sec_identity()
    from edgar import Company

    return Company(ticker)


def _map_filing(ticker: str, cik: Any, filing: Any) -> FilingMetadata:
    """Map safe upstream metadata fields to one local filing contract.

    Args:
        ticker: Valid normalized ticker.
        cik: Company CIK supplied by Edgartools.
        filing: Upstream filing metadata object.

    Returns:
        Validated filing metadata without document or exhibit inspection.

    Raises:
        ValueError: If required upstream metadata is absent or invalid.
    """
    accession = getattr(filing, "accession_no", None) or getattr(filing, "accession_number", None)
    source_url = getattr(filing, "url", None) or getattr(filing, "homepage_url", None)
    raw_date = getattr(filing, "filing_date", None)
    filing_date = raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date))
    return FilingMetadata(
        ticker=ticker,
        cik=str(cik),
        form=str(getattr(filing, "form", "")),
        filing_date=filing_date,
        accession=str(accession or ""),
        filing_url=str(source_url or ""),
    )


def list_sec_filings(
    ticker: str,
    forms: Iterable[str] | None = None,
    since: date | str | None = None,
    until: date | str | None = None,
    company_factory: CompanyFactory | None = None,
) -> FilingDiscoveryResult:
    """Discover filing metadata without downloading SEC documents.

    Args:
        ticker: Caller-supplied 1–10 letter ticker.
        forms: Optional iterable of SEC form filters.
        since: Optional inclusive filing-date lower bound as a date or ISO string.
        until: Optional inclusive filing-date upper bound (as-of / PIT cutoff).
        company_factory: Optional injected Edgartools-compatible test seam.

    Returns:
        Newest-first filing metadata or a structured recoverable failure.
    """
    try:
        normalized_ticker = _normalize_ticker(ticker)
        normalized_forms = _normalize_forms(forms)
        normalized_since = _normalize_since(since)
        normalized_until = _normalize_since(until)
    except (AttributeError, TypeError, ValueError):
        return _failure("INVALID_INPUT", "Ticker, forms, or since date is invalid.", False)

    try:
        company = (company_factory or _default_company_factory)(normalized_ticker)
    except ModuleNotFoundError:
        return _failure("DEPENDENCY_UNAVAILABLE", "Edgartools is not installed.", False)
    except ValueError:
        return _failure("NOT_FOUND", "Company could not be resolved for ticker.", False)
    except Exception:
        return _failure("UNAVAILABLE", "SEC filing provider is currently unavailable.", True)

    cik = getattr(company, "cik", None)
    if cik is None or not str(cik).strip():
        return _failure("NOT_FOUND", "Company did not provide a CIK.", False)

    try:
        upstream_filings = company.get_filings(form=normalized_forms, trigger_full_load=False)
    except Exception:
        return _failure("UNAVAILABLE", "SEC filing provider is currently unavailable.", True)

    try:
        filings = tuple(_map_filing(normalized_ticker, cik, filing) for filing in upstream_filings)
        if normalized_forms is not None:
            allowed_forms = frozenset(normalized_forms)
            filings = tuple(filing for filing in filings if filing.form.upper() in allowed_forms)
        if normalized_since is not None:
            filings = tuple(filing for filing in filings if filing.filing_date >= normalized_since)
        if normalized_until is not None:
            filings = tuple(filing for filing in filings if filing.filing_date <= normalized_until)
        return FilingDiscoveryResult(
            tuple(sorted(filings, key=lambda filing: (filing.filing_date, filing.accession), reverse=True))
        )
    except (AttributeError, TypeError, ValueError):
        return _failure("MALFORMED_UPSTREAM", "SEC provider returned incomplete filing metadata.", True)
