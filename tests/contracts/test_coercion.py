"""Tests for Pydantic pre-validation numeric coercion helper adapted from donor."""
import pytest
from app.contracts.coercion import coerce_optional_float


def test_coerce_optional_float_placeholders():
    assert coerce_optional_float("None") is None
    assert coerce_optional_float("N/A") is None
    assert coerce_optional_float("na") is None
    assert coerce_optional_float("null") is None
    assert coerce_optional_float("-") is None
    assert coerce_optional_float("TBD") is None
    assert coerce_optional_float("") is None
    assert coerce_optional_float(None) is None


def test_coerce_optional_float_percentages():
    # Percentage strings should be dropped rather than interpreted as a raw price
    assert coerce_optional_float("15%") is None
    assert coerce_optional_float("2.5%") is None


def test_coerce_optional_float_currency():
    assert coerce_optional_float("$150.25") == 150.25
    assert coerce_optional_float("€1,250.00") == 1250.00
    assert coerce_optional_float("£99.99") == 99.99


def test_coerce_optional_float_numbers():
    assert coerce_optional_float(100) == 100.0
    assert coerce_optional_float(45.67) == 45.67
    assert coerce_optional_float("189.5") == 189.5


def test_coerce_optional_float_invalid_strings():
    assert coerce_optional_float("around 150") is None
    assert coerce_optional_float("150-160") is None
    assert coerce_optional_float("invalid") is None
