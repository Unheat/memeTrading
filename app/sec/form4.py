"""Deterministic SEC Form 4 XML parser.

Extracts insider transactions directly from official EDGAR Form 4 XML disclosures
using standard library xml.etree.ElementTree with zero hallucination risk.
Explicitly isolates Code F tax withholding from discretionary open-market sales
and detects Rule 10b5-1 pre-scheduled trading plans.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Form4Transaction:
    """One individual transaction reported in a Form 4."""

    security_title: str
    transaction_date: str
    transaction_code: str
    acquired_disposed: str
    shares: float
    price: float | None
    remaining_shares: float | None
    direct_or_indirect: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "security_title": self.security_title,
            "transaction_date": self.transaction_date,
            "transaction_code": self.transaction_code,
            "acquired_disposed": self.acquired_disposed,
            "shares": self.shares,
            "price": self.price,
            "remaining_shares": self.remaining_shares,
            "direct_or_indirect": self.direct_or_indirect,
        }


@dataclass(frozen=True)
class Form4AuditSummary:
    """Consolidated insider trading audit summary from Form 4 XML."""

    ticker: str
    filing_date: str
    insider_name: str
    position: str
    is_director: bool
    is_officer: bool
    is_ten_pct_owner: bool
    rule_10b5_1_active: bool
    open_market_buys_shares: float
    open_market_sales_shares: float
    net_discretionary_shares: float
    tax_withholding_shares: float
    option_exercises_shares: float
    transactions: tuple[Form4Transaction, ...]
    footnotes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "filing_date": self.filing_date,
            "insider_name": self.insider_name,
            "position": self.position,
            "is_director": self.is_director,
            "is_officer": self.is_officer,
            "is_ten_pct_owner": self.is_ten_pct_owner,
            "rule_10b5_1_active": self.rule_10b5_1_active,
            "open_market_buys_shares": self.open_market_buys_shares,
            "open_market_sales_shares": self.open_market_sales_shares,
            "net_discretionary_shares": self.net_discretionary_shares,
            "tax_withholding_shares": self.tax_withholding_shares,
            "option_exercises_shares": self.option_exercises_shares,
            "transactions": [t.to_dict() for t in self.transactions],
            "footnotes": list(self.footnotes),
        }


def _find_text(element: ET.Element | None, path: str, default: str = "") -> str:
    """Find text inside a nested XML element path."""
    if element is None:
        return default
    target = element.find(path)
    if target is not None and target.text:
        return target.text.strip()
    return default


def _find_float(element: ET.Element | None, path: str) -> float | None:
    """Find and parse float inside a nested XML element path."""
    val_str = _find_text(element, path)
    if not val_str:
        return None
    try:
        return float(val_str.replace(",", ""))
    except ValueError:
        return None


def parse_form4_xml(xml_content: str) -> Form4AuditSummary:
    """Parse raw SEC EDGAR Form 4 XML string into an audit summary.

    :param xml_content: Non-empty Form 4 XML string.
    :returns: Form4AuditSummary with isolated transaction codes and 10b5-1 flag.
    :raises ValueError: On invalid, empty, or unparseable XML.
    """
    if not xml_content or not xml_content.strip():
        raise ValueError("Form 4 XML content cannot be empty")

    try:
        root = ET.fromstring(xml_content)
    except Exception as exc:
        raise ValueError(f"Failed to parse Form 4 XML: {exc}") from exc

    ticker = _find_text(root, ".//issuer/issuerTradingSymbol") or "UNKNOWN"
    period = _find_text(root, ".//periodOfReport") or ""

    # Insider identity & relationship
    owner = root.find(".//reportingOwner")
    insider_name = _find_text(owner, ".//reportingOwnerId/rptOwnerName") or "Unknown Insider"
    relationship = owner.find(".//reportingOwnerRelationship") if owner is not None else None
    position = _find_text(relationship, "officerTitle") or "Insider"
    is_director = _find_text(relationship, "isDirector") == "1"
    is_officer = _find_text(relationship, "isOfficer") == "1"
    is_ten_pct = _find_text(relationship, "isTenPercentOwner") == "1"

    # Rule 10b5-1 plan detection (checkbox or footnote)
    rule_10b5_1_active = _find_text(root, "aff10b5One") == "1"
    footnotes: list[str] = []
    for fn in root.findall(".//footnotes/footnote"):
        fn_text = (fn.text or "").strip()
        if fn_text:
            footnotes.append(fn_text)
            if "10b5-1" in fn_text or "10b51" in fn_text:
                rule_10b5_1_active = True

    # Parse Non-Derivative Transactions
    transactions: list[Form4Transaction] = []
    buys_shares = 0.0
    sales_shares = 0.0
    tax_withholding_shares = 0.0
    option_exercises_shares = 0.0

    for tx in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
        sec_title = _find_text(tx, ".//securityTitle/value")
        tx_date = _find_text(tx, ".//transactionDate/value")
        tx_code = _find_text(tx, ".//transactionCoding/transactionCode").upper()
        acq_disp = _find_text(tx, ".//transactionAmounts/transactionAcquiredDisposedCode/value").upper()
        shares = _find_float(tx, ".//transactionAmounts/transactionShares/value") or 0.0
        price = _find_float(tx, ".//transactionAmounts/transactionPricePerShare/value")
        remaining = _find_float(tx, ".//postTransactionAmounts/sharesOwnedFollowingTransaction/value")
        direct_indirect = _find_text(tx, ".//ownershipNature/directOrIndirectOwnership/value")

        transactions.append(
            Form4Transaction(
                security_title=sec_title,
                transaction_date=tx_date,
                transaction_code=tx_code,
                acquired_disposed=acq_disp,
                shares=shares,
                price=price,
                remaining_shares=remaining,
                direct_or_indirect=direct_indirect,
            )
        )

        # Code accounting
        if tx_code == "P" and acq_disp == "A":
            buys_shares += shares
        elif tx_code == "S" and acq_disp == "D":
            sales_shares += shares
        elif tx_code == "F" and acq_disp == "D":
            # Code F: Statutory tax withholding on vesting
            tax_withholding_shares += shares
        elif tx_code == "M":
            # Code M: Option exercise
            option_exercises_shares += shares

    net_discretionary = buys_shares - sales_shares

    return Form4AuditSummary(
        ticker=ticker.upper(),
        filing_date=period,
        insider_name=insider_name,
        position=position,
        is_director=is_director,
        is_officer=is_officer,
        is_ten_pct_owner=is_ten_pct,
        rule_10b5_1_active=rule_10b5_1_active,
        open_market_buys_shares=round(buys_shares, 2),
        open_market_sales_shares=round(sales_shares, 2),
        net_discretionary_shares=round(net_discretionary, 2),
        tax_withholding_shares=round(tax_withholding_shares, 2),
        option_exercises_shares=round(option_exercises_shares, 2),
        transactions=tuple(transactions),
        footnotes=tuple(footnotes),
    )
