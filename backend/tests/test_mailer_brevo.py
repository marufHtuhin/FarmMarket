"""Tests for the Brevo HTTPS mailer transport (mailer.py).

Brevo is the PRIMARY transport for Render free (Render's free plan
blocks outbound SMTP ports; Mailjet blocked this user's account with
mj-0001 "temporarily blocked"; Postmark requires a work email at signup;
SendGrid blocked this user's account at login). Precedence is Brevo,
then Mailjet, then Postmark, then SendGrid, then SMTP — first configured
wins. Brevo is configured when BREVO_API_KEY is set.

Brevo authenticates with a custom ``api-key`` header (NOT an
Authorization Bearer token) and answers success with HTTP 201. No live
network is used here: httpx.Client is mocked (same pattern as
test_assistant.py's _fake_httpx_client), and the fake credential below
is not real. Tests assert the ``api-key`` header is wired but NEVER
assert the credential value itself.
"""
import smtplib
from unittest.mock import MagicMock

import httpx
import pytest

from app.services import mailer

_FAKE_KEY = "xkeysib-fake-brevo-api-key-not-a-real-credential"
BREVO_URL = "https://api.brevo.com/v3/smtp/email"

SMTP_ENV = {"SMTP_HOST": "smtp.example.com", "SMTP_USER": "user@example.com",
            "SMTP_PASSWORD": "pw"}


def _set_brevo(monkeypatch, **overrides):
    monkeypatch.setenv("BREVO_API_KEY", _FAKE_KEY)
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)


def _clear_mail_env(monkeypatch):
    for key in ("BREVO_API_KEY", "MAILJET_API_KEY", "MAILJET_API_SECRET",
                "POSTMARK_SERVER_TOKEN", "SENDGRID_API_KEY", "SMTP_HOST",
                "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def http_mock(monkeypatch):
    """Mock httpx.Client; yields (client_cls, client, response)."""
    response = MagicMock()
    response.status_code = 201
    response.text = '{"messageId": "fake-message-id"}'
    response.json.return_value = {"messageId": "fake-message-id"}
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
def test_is_configured_brevo_key(monkeypatch):
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch)
    assert mailer.is_configured() is True


def test_is_configured_blank_brevo_key_is_unconfigured(monkeypatch):
    _clear_mail_env(monkeypatch)
    monkeypatch.setenv("BREVO_API_KEY", "   ")
    assert mailer.is_configured() is False


# ---------------- send_email via Brevo ----------------
def test_brevo_success_201(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch, SMTP_FROM="user@example.com")
    cls, client, _ = http_mock
    assert mailer.send_email("to@x.t", "Subject", "plain body",
                             "<p>html body</p>") is True
    assert cls.call_args[1]["timeout"] == 10
    client.post.assert_called_once()
    args, kwargs = client.post.call_args
    assert args[0] == BREVO_URL
    headers = kwargs["headers"]
    # Brevo uses the custom api-key header — NOT Authorization: Bearer.
    assert "api-key" in headers
    assert isinstance(headers["api-key"], str) and headers["api-key"]
    assert "Authorization" not in headers
    assert headers["accept"] == "application/json"
    assert headers["content-type"] == "application/json"
    assert kwargs["json"] == {
        "sender": {"name": "FarmMarket", "email": "user@example.com"},
        "to": [{"email": "to@x.t"}],
        "subject": "Subject",
        "textContent": "plain body",
        "htmlContent": "<p>html body</p>",
    }


def test_brevo_text_only_omits_html_content_key(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch, SMTP_USER="user@example.com")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    payload = client.post.call_args[1]["json"]
    assert "htmlContent" not in payload
    assert payload["textContent"] == "B"
    # SMTP_FROM unset -> SMTP_USER is the sender, name FarmMarket.
    assert payload["sender"] == {"name": "FarmMarket",
                                 "email": "user@example.com"}


def test_brevo_uses_smtp_from_display_name(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch, SMTP_FROM="Acme Farm <noreply@example.com>")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert (client.post.call_args[1]["json"]["sender"]
            == {"name": "Acme Farm", "email": "noreply@example.com"})


def test_brevo_201_with_empty_body_still_succeeds(monkeypatch, http_mock):
    """Success is status-based only: a 201 with no parseable body
    still counts — the messageId is never read."""
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch, SMTP_USER="user@example.com")
    _, _, response = http_mock
    response.status_code = 201
    response.text = ""
    response.json.side_effect = ValueError("no json")
    assert mailer.send_email("to@x.t", "S", "B") is True


def test_brevo_non_201_returns_false(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch, SMTP_USER="user@example.com")
    _, client, response = http_mock
    for status in (200, 400, 401, 500):
        # Even a 200 is NOT success for Brevo — only 201 counts.
        response.status_code = status
        response.text = "brevo error"
        assert mailer.send_email("to@x.t", "S", "B") is False
    assert client.post.call_count == 4


def test_brevo_exception_returns_false_never_raises(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch, SMTP_USER="user@example.com")
    _, client, _ = http_mock
    client.post.side_effect = httpx.ConnectError(
        "boom", request=httpx.Request("POST", BREVO_URL))
    assert mailer.send_email("to@x.t", "S", "B") is False


def test_brevo_no_sender_address_returns_false_without_post(monkeypatch,
                                                            http_mock):
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch)  # key set, but no SMTP_FROM/SMTP_USER
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is False
    client.post.assert_not_called()


# ---------------- precedence ----------------
def test_brevo_takes_precedence_over_mailjet(monkeypatch, http_mock):
    """Brevo key + Mailjet creds both set: Brevo wins."""
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch, SMTP_USER="user@example.com")
    monkeypatch.setenv("MAILJET_API_KEY", "fake-mailjet-key")
    monkeypatch.setenv("MAILJET_API_SECRET", "fake-mailjet-secret")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    client.post.assert_called_once()
    assert client.post.call_args[0][0] == BREVO_URL


def test_brevo_takes_precedence_over_postmark_and_sendgrid(monkeypatch,
                                                           http_mock):
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch, SMTP_USER="user@example.com")
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "fake-postmark-token")
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.fake-key")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    client.post.assert_called_once()
    assert client.post.call_args[0][0] == BREVO_URL


def test_brevo_takes_precedence_over_smtp(monkeypatch, http_mock, smtp_mock):
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch)
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    _, client, _ = http_mock
    smtp_cls, _ = smtp_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    client.post.assert_called_once()
    smtp_cls.assert_not_called()


def test_mailjet_still_used_without_brevo(monkeypatch, http_mock):
    """Mailjet stays the fallback when only its creds are set."""
    _clear_mail_env(monkeypatch)
    monkeypatch.setenv("MAILJET_API_KEY", "fake-mailjet-key")
    monkeypatch.setenv("MAILJET_API_SECRET", "fake-mailjet-secret")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    _, client, response = http_mock
    response.status_code = 200
    response.text = '{"Messages":[{"Status":"success"}]}'
    response.json.return_value = {"Messages": [{"Status": "success"}]}
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert (client.post.call_args[0][0]
            == "https://api.mailjet.com/v3.1/send")


# ---------------- reset / verification emails ride the same transport ------
def test_reset_email_uses_brevo(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch, SMTP_USER="user@example.com")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com")
    _, client, _ = http_mock
    assert mailer.send_password_reset_email("u@x.t", "tok123") is True
    payload = client.post.call_args[1]["json"]
    link = "https://app.example.com/reset-password?token=tok123"
    assert link in payload["textContent"]
    assert "reset" in payload["subject"].lower()


def test_verification_email_uses_brevo(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_brevo(monkeypatch, SMTP_USER="user@example.com")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com")
    _, client, _ = http_mock
    assert mailer.send_verification_email("u@x.t", "tok456") is True
    payload = client.post.call_args[1]["json"]
    link = "https://app.example.com/verify-email?token=tok456"
    assert link in payload["textContent"]
    assert "confirm" in payload["subject"].lower()
