"""Tests for SEC User-Agent identity initialization."""
import os
from unittest.mock import patch
import pytest
from app.sec.identity import ensure_sec_identity, DEFAULT_SEC_IDENTITY


def test_ensure_sec_identity_default():
    with patch.dict("os.environ", {}, clear=True):
        ident = ensure_sec_identity()
        assert ident == DEFAULT_SEC_IDENTITY
        assert os.environ.get("SEC_USER_AGENT") == DEFAULT_SEC_IDENTITY
        assert os.environ.get("EDGAR_IDENTITY") == DEFAULT_SEC_IDENTITY


def test_ensure_sec_identity_from_env():
    with patch.dict("os.environ", {"SEC_USER_AGENT": "CustomAgent test@example.com"}, clear=True):
        ident = ensure_sec_identity()
        assert ident == "CustomAgent test@example.com"
        assert os.environ.get("EDGAR_IDENTITY") == "CustomAgent test@example.com"


def test_ensure_sec_identity_custom_param():
    with patch.dict("os.environ", {}, clear=True):
        ident = ensure_sec_identity("ExplicitAgent custom@example.com")
        assert ident == "ExplicitAgent custom@example.com"
        assert os.environ.get("SEC_USER_AGENT") == "ExplicitAgent custom@example.com"
