"""Tests for deterministic SEC Form 4 XML parser."""
import pytest
from app.sec.form4 import parse_form4_xml, Form4AuditSummary, Form4Transaction

# Real SEC Form 4 XML snippet demonstrating Code F tax withholding vs Code S sale
FORM4_XML_FIXTURE = """<?xml version="1.0"?>
<ownershipDocument>
    <schemaVersion>X0508</schemaVersion>
    <documentType>4</documentType>
    <periodOfReport>2026-09-01</periodOfReport>
    <notSubjectToSection16>0</notSubjectToSection16>
    <issuer>
        <issuerCik>0000723125</issuerCik>
        <issuerName>MICRON TECHNOLOGY INC</issuerName>
        <issuerTradingSymbol>MU</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>0001234567</rptOwnerCik>
            <rptOwnerName>Mehrotra Sanjay</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>1</isDirector>
            <isOfficer>1</isOfficer>
            <isTenPercentOwner>0</isTenPercentOwner>
            <isOther>0</isOther>
            <officerTitle>President and CEO</officerTitle>
        </reportingOwnerRelationship>
    </reportingOwner>
    <aff10b5One>1</aff10b5One>
    <nonDerivativeTable>
        <!-- Code F: Automatic tax withholding on RSU vesting (NOT a discretionary market sale) -->
        <nonDerivativeTransaction>
            <securityTitle><value>Common Stock</value></securityTitle>
            <transactionDate><value>2026-09-01</value></transactionDate>
            <transactionCoding>
                <transactionFormType>4</transactionFormType>
                <transactionCode>F</transactionCode>
                <equitySwapInvolved>0</equitySwapInvolved>
            </transactionCoding>
            <transactionTimeliness><value></value></transactionTimeliness>
            <transactionAmounts>
                <transactionShares><value>45000</value></transactionShares>
                <transactionPricePerShare><value>118.50</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>950000</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
            <ownershipNature>
                <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
            </ownershipNature>
        </nonDerivativeTransaction>
        <!-- Code S: Discretionary open-market sale -->
        <nonDerivativeTransaction>
            <securityTitle><value>Common Stock</value></securityTitle>
            <transactionDate><value>2026-09-02</value></transactionDate>
            <transactionCoding>
                <transactionFormType>4</transactionFormType>
                <transactionCode>S</transactionCode>
                <equitySwapInvolved>0</equitySwapInvolved>
            </transactionCoding>
            <transactionTimeliness><value></value></transactionTimeliness>
            <transactionAmounts>
                <transactionShares><value>10000</value></transactionShares>
                <transactionPricePerShare><value>121.00</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>940000</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
            <ownershipNature>
                <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
            </ownershipNature>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
    <footnotes>
        <footnote id="F1">Sales were effected pursuant to a Rule 10b5-1 trading plan adopted on October 12, 2025.</footnote>
    </footnotes>
</ownershipDocument>
"""


def test_parse_form4_xml_isolates_code_f_and_detects_10b5_1():
    summary = parse_form4_xml(FORM4_XML_FIXTURE)

    assert isinstance(summary, Form4AuditSummary)
    assert summary.ticker == "MU"
    assert summary.filing_date == "2026-09-01"
    assert summary.insider_name == "Mehrotra Sanjay"
    assert summary.position == "President and CEO"
    assert summary.is_director is True
    assert summary.is_officer is True
    assert summary.rule_10b5_1_active is True

    # 45,000 shares withheld for taxes (Code F), NOT discretionary
    assert summary.tax_withholding_shares == 45000.0

    # 10,000 shares sold discretionary on open market (Code S)
    assert summary.open_market_sales_shares == 10000.0
    assert summary.open_market_buys_shares == 0.0

    # Net discretionary shares = buys - sales = 0 - 10000 = -10000
    assert summary.net_discretionary_shares == -10000.0

    assert len(summary.transactions) == 2
    t1 = summary.transactions[0]
    assert t1.transaction_code == "F"
    assert t1.shares == 45000.0
    assert t1.price == 118.50

    t2 = summary.transactions[1]
    assert t2.transaction_code == "S"
    assert t2.shares == 10000.0
    assert t2.price == 121.00


def test_parse_form4_xml_purchase():
    buy_xml = """<?xml version="1.0"?>
<ownershipDocument>
    <issuer><issuerTradingSymbol>ABC</issuerTradingSymbol></issuer>
    <periodOfReport>2026-09-03</periodOfReport>
    <reportingOwner>
        <reportingOwnerId><rptOwnerName>Jane Investor</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>0</isOfficer></reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-09-03</value></transactionDate>
            <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>5000</value></transactionShares>
                <transactionPricePerShare><value>25.00</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
</ownershipDocument>
"""
    summary = parse_form4_xml(buy_xml)
    assert summary.ticker == "ABC"
    assert summary.open_market_buys_shares == 5000.0
    assert summary.open_market_sales_shares == 0.0
    assert summary.net_discretionary_shares == 5000.0
    assert summary.tax_withholding_shares == 0.0
    assert summary.rule_10b5_1_active is False


def test_parse_form4_xml_invalid_handled():
    with pytest.raises(ValueError):
        parse_form4_xml("")
    with pytest.raises(ValueError):
        parse_form4_xml("<notXml")
