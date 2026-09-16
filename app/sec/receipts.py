"""Server-issued SEC discovery receipts.

This module is locally written. It provides opaque, server-verified receipt IDs
for discovered SEC filings and declared documents so model tool calls cannot forge
or cross-contaminate filing provenance.
"""
from __future__ import annotations

import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.sec.pull import SelectedSecDocument
from app.sec.schemas import FilingMetadata


@dataclass(frozen=True)
class DocumentReceipt:
    """Opaque server-resolved document reference."""

    document_receipt_id: str
    filing_receipt_id: str
    document_name: str
    source_url: str
    form: str
    accession: str
    filing_date: str


@dataclass(frozen=True)
class DiscoveredFilingReceipt:
    """Opaque server-resolved filing reference."""

    filing_receipt_id: str
    ticker: str
    cik: str
    form: str
    filing_date: str
    accession: str
    filing_url: str
    candidate_id: str | None = None
    documents: tuple[DocumentReceipt, ...] = field(default_factory=tuple)
    filing_metadata: FilingMetadata | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize safe public descriptor for model discovery output."""
        return {
            "filing_receipt_id": self.filing_receipt_id,
            "ticker": self.ticker,
            "cik": self.cik,
            "form": self.form,
            "filing_date": self.filing_date,
            "accession": self.accession,
            "filing_url": self.filing_url,
            "candidate_id": self.candidate_id,
            "documents": [
                {
                    "document_receipt_id": doc.document_receipt_id,
                    "document_name": doc.document_name,
                    "form": doc.form,
                }
                for doc in self.documents
            ],
        }


class SecReceiptStore:
    """In-memory thread-safe registry of discovered SEC filings and document targets."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._filings: dict[str, DiscoveredFilingReceipt] = {}
        self._documents: dict[str, DocumentReceipt] = {}

    def register_discovery(
        self,
        filings: Sequence[FilingMetadata],
        candidate_id: str | None = None,
    ) -> list[DiscoveredFilingReceipt]:
        """Register verified discovered filings and issue immutable receipt IDs."""
        with self._lock:
            issued: list[DiscoveredFilingReceipt] = []
            for filing in filings:
                f_id = f"frec_{uuid.uuid4().hex[:12]}"
                doc_receipts: list[DocumentReceipt] = []

                # Primary document receipt
                doc_name = filing.primary_document or f"{filing.form.lower()}_primary.htm"
                p_doc_id = f"drec_{uuid.uuid4().hex[:12]}"
                primary_doc = DocumentReceipt(
                    document_receipt_id=p_doc_id,
                    filing_receipt_id=f_id,
                    document_name=doc_name,
                    source_url=filing.filing_url,
                    form=filing.form,
                    accession=filing.accession,
                    filing_date=filing.filing_date.isoformat(),
                )
                doc_receipts.append(primary_doc)
                self._documents[p_doc_id] = primary_doc

                # Declared exhibits receipts
                for ex_name in filing.exhibits:
                    ex_doc_id = f"drec_{uuid.uuid4().hex[:12]}"
                    ex_doc = DocumentReceipt(
                        document_receipt_id=ex_doc_id,
                        filing_receipt_id=f_id,
                        document_name=ex_name,
                        source_url=filing.filing_url,
                        form=filing.form,
                        accession=filing.accession,
                        filing_date=filing.filing_date.isoformat(),
                    )
                    doc_receipts.append(ex_doc)
                    self._documents[ex_doc_id] = ex_doc

                discovered = DiscoveredFilingReceipt(
                    filing_receipt_id=f_id,
                    ticker=filing.ticker,
                    cik=filing.cik,
                    form=filing.form,
                    filing_date=filing.filing_date.isoformat(),
                    accession=filing.accession,
                    filing_url=filing.filing_url,
                    candidate_id=candidate_id,
                    documents=tuple(doc_receipts),
                    filing_metadata=filing,
                )
                self._filings[f_id] = discovered
                issued.append(discovered)
            return issued

    def resolve_selection(
        self,
        filing_receipt_id: str,
        document_receipt_id: str | None = None,
        candidate_id: str | None = None,
    ) -> SelectedSecDocument | None:
        """Resolve a server-verified SelectedSecDocument using opaque receipt IDs."""
        with self._lock:
            filing = self._filings.get(filing_receipt_id)
            if not filing or not filing.filing_metadata:
                return None
            if candidate_id and filing.candidate_id and filing.candidate_id != candidate_id:
                return None

            if document_receipt_id:
                doc = self._documents.get(document_receipt_id)
                if not doc or doc.filing_receipt_id != filing_receipt_id:
                    return None
            else:
                doc = filing.documents[0] if filing.documents else None

            if not doc:
                return None

            return SelectedSecDocument(
                filing=filing.filing_metadata,
                document_name=doc.document_name,
                source_url=doc.source_url,
            )


# Global process receipt registry
_GLOBAL_RECEIPT_STORE = SecReceiptStore()


def get_sec_receipt_store() -> SecReceiptStore:
    """Return the active server-side SEC discovery receipt store."""
    return _GLOBAL_RECEIPT_STORE
