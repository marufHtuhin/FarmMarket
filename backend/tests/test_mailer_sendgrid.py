"""Tests for the SendGrid HTTPS mailer transport (mailer.py).

Render's free plan blocks outbound SMTP ports (25/465/587), so Gmail SMTP
silently fails on Render free. When SENDGRID_API_KEY is set, the mailer
POSTs to the SendGrid v3 Mail Send API over HTTPS instead — and SendGrid
takes precedence over SMTP, so a configured-but-unusable SMTP setup can
never shadow it. Without the key, the SMTP path runs exactly as before.

No live network is used here: httpx.Client is mocked (same pattern as
test_assistant.py's _fake_httpx_client), and the fake key below is not a
real credential. Tests assert the Authorization header is present and
well-formed, but NEVER assert the key value itself.
"""
import smtplib
from unittest.mock import MagicMock

import httpx
import pytest

from app.services import mailer

_FAKE_KEY = "SG.fake-test-key-not-a-real-credential"
SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"

SMTP_ENV = {"SMTP_HOST": "smtp.example.com", "SMTP_USER": "user@example.com",
            "SMTP_PASSWORD": "pw"}


def _set_sendgrid(monkeypatch, **overrides):
    monkeypatch.setenv("SENDGRID_API_KEY", _FAKE_KEY)
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)


def _clear_mail_env(monkeypatch):
    for key in ("MAILJET_API_KEY", "MAILJET_API_SECRET",
                "POSTMARK_SERVER_TOKEN", "SENDGRID_API_KEY", "SMTP_HOST",
                "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def http_mock(monkeypatch):
    """Mock httpx.Client; yields (client_cls, client, response)."""
    response = MagicMock()
    response.status_code = 202
    response.text = ""
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response
    cls = MagicMock(return_value=client)
    monkeypatch.setattr(httpx, "Client", cls)
    return cls, client, response


@pytest.fixture()
def smtp_mock(monkeypatch):
    server = MagicMock()
    cls = MagicMock(return_value=server)
    server.__enter__.return_value = server
    monkeypatch.setattr(smtplib, "SMTP", cls)
    return cls, server


# ---------------- is_configured ----------------
def test_is_configured_sendgrid_key_alone(monkeypatch):
    _clear_mail_env(monkeypatch)
    _set_sendgrid(monkeypatch)
    assert mailer.is_configured() is True


def test_is_configured_blank_sendgrid_key_is_unconfigured(monkeypatch):
    _clear_mail_env(monkeypatch)
    monkeypatch.setenv("SENDGRID_API_KEY", "   ")
    assert mailer.is_configured() is False


def test_is_configured_smtp_still_counts_without_key(monkeypatch):
    _clear_mail_env(monkeypatch)
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    assert mailer.is_configured() is True


# ---------------- send_email via SendGrid ----------------
def test_sendgrid_success_202(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_sendgrid(monkeypatch, SMTP_FROM="user@example.com")
    cls, client, _ = http_mock
    assert mailer.send_email("to@x.t", "Subject", "plain body",
                             "<p>html body</p>") is True
    cls.assert_called_once_with(timeout=10)
    client.post.assert_called_once()
    args, kwargs = client.post.call_args
    assert args[0] == SENDGRID_URL
    auth = kwargs["headers"]["Authorization"]
    assert auth.startswith("Bearer ") and len(auth) > len("Bearer ")
    assert kwargs["headers"]["Content-Type"] == "application/json"
    payload = kwargs["json"]
    assert payload["personalizations"] == [
        {"to": [{"email": "to@x.t"}], "subject": "Subject"}]
    assert payload["from"] == {"email": "user@example.com",
                               "name": "FarmMarket"}
    assert payload["content"] == [
        {"type": "text/plain", "value": "plain body"},
        {"type": "text/html", "value": "<p>html body</p>"},
    ]


def test_sendgrid_text_only_has_no_html_content(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_sendgrid(monkeypatch, SMTP_USER="user@example.com")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    payload = client.post.call_args[1]["json"]
    assert payload["content"] == [{"type": "text/plain", "value": "B"}]
    # SMTP_FROM unset -> SMTP_USER is the sender, display name FarmMarket.
    assert payload["from"] == {"email": "user@example.com",
                               "name": "FarmMarket"}


def test_sendgrid_uses_smtp_from_display_name(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_sendgrid(monkeypatch, SMTP_FROM="Acme Farm <noreply@example.com>")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert client.post.call_args[1]["json"]["from"] == {
        "email": "noreply@example.com", "name": "Acme Farm"}


def test_sendgrid_non_2xx_returns_false(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_sendgrid(monkeypatch, SMTP_USER="user@example.com")
    _, client, response = http_mock
    for status in (400, 401, 403):
        response.status_code = status
        response.text = "sendgrid error"
        assert mailer.send_email("to@x.t", "S", "B") is False
    assert client.post.call_count == 3


def test_sendgrid_exception_returns_false_never_raises(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_sendgrid(monkeypatch, SMTP_USER="user@example.com")
    _, client, _ = http_mock
    client.post.side_effect = httpx.ConnectError(
        "boom", request=httpx.Request("POST", SENDGRID_URL))
    assert mailer.send_email("to@x.t", "S", "B") is False


def test_sendgrid_no_sender_address_returns_false_without_post(monkeypatch,
                                                               http_mock):
    _clear_mail_env(monkeypatch)
    _set_sendgrid(monkeypatch)  # key set, but no SMTP_FROM/SMTP_USER
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is False
    client.post.assert_not_called()


# ---------------- precedence over SMTP ----------------
def test_sendgrid_takes_precedence_over_smtp(monkeypatch, http_mock, smtp_mock):
    """Both transports configured: SendGrid is used, SMTP untouched.
    On Render free the SMTP vars may be set but unusable — precedence
    avoids the silent SMTP failure."""
    _clear_mail_env(monkeypatch)
    _set_sendgrid(monkeypatch)
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    _, client, _ = http_mock
    smtp_cls, _ = smtp_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    client.post.assert_called_once()
    smtp_cls.assert_not_called()


def test_smtp_still_used_without_sendgrid_key(monkeypatch, smtp_mock, http_mock):
    _clear_mail_env(monkeypatch)
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    smtp_cls, server = smtp_mock
    http_cls, _, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    smtp_cls.assert_called_once()
    server.send_message.assert_called_once()
    http_cls.assert_not_called()


# ---------------- reset / verification emails ride the same transport ------
def test_reset_email_uses_sendgrid(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_sendgrid(monkeypatch, SMTP_USER="user@example.com")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com")
    _, client, _ = http_mock
    assert mailer.send_password_reset_email("u@x.t", "tok123") is True
    payload = client.post.call_args[1]["json"]
    link = "https://app.example.com/reset-password?token=tok123"
    assert link in payload["content"][0]["value"]
    assert "reset" in payload["personalizations"][0]["subject"].lower()


def test_verification_email_uses_sendgrid(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_sendgrid(monkeypatch, SMTP_USER="user@example.com")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com")
    _, client, _ = http_mock
    assert mailer.send_verification_email("u@x.t", "tok456") is True
    payload = client.post.call_args[1]["json"]
    link = "https://app.example.com/verify-email?token=tok456"
    assert link in payload["content"][0]["value"]
