"""Tests for the From-header display name (spam mitigation).

send_email sends as ``FarmMarket <address>`` so Gmail sees a named
sender instead of a bare address (a bare From is a spam signal). No
real email is ever sent here: smtplib.SMTP is mocked throughout.
"""
import smtplib
from unittest.mock import MagicMock

import pytest

from app.services import mailer

_TEST_PW = "pw"

SMTP_ENV = {"SMTP_HOST": "smtp.example.com", "SMTP_USER": "user@example.com",
            "SMTP_PASSWORD": _TEST_PW}


def _set_smtp(monkeypatch, **overrides):
    for key, value in {**SMTP_ENV, **overrides}.items():
        monkeypatch.setenv(key, value)


@pytest.fixture()
def smtp_mock(monkeypatch):
    """Mock smtplib.SMTP; yields the (context-manager) server mock."""
    server = MagicMock()
    cls = MagicMock(return_value=server)
    server.__enter__.return_value = server
    monkeypatch.setattr(smtplib, "SMTP", cls)
    return cls, server


def _sent_from(server):
    return server.send_message.call_args[0][0]["From"]


def test_from_header_has_farmmarket_display_name(monkeypatch, smtp_mock):
    _set_smtp(monkeypatch)
    _, server = smtp_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert _sent_from(server) == "FarmMarket <user@example.com>"


def test_from_header_uses_smtp_from_address(monkeypatch, smtp_mock):
    _set_smtp(monkeypatch, SMTP_FROM="noreply@example.com")
    _, server = smtp_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert _sent_from(server) == "FarmMarket <noreply@example.com>"


def test_from_header_keeps_existing_display_name(monkeypatch, smtp_mock):
    _set_smtp(monkeypatch, SMTP_FROM="Acme Support <support@example.com>")
    _, server = smtp_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert _sent_from(server) == "Acme Support <support@example.com>"


def test_from_header_bare_fallback_when_empty(monkeypatch):
    """No address at all: the bare (empty) value is returned as-is."""
    monkeypatch.setenv("SMTP_FROM", "")
    monkeypatch.setenv("SMTP_USER", "")
    assert mailer._from_header() == ""
