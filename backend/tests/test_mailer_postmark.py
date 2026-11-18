"""Tests for the Postmark HTTPS mailer transport (mailer.py).

Postmark is the PRIMARY transport for Render free (Render's free plan
blocks outbound SMTP ports, and SendGrid blocked this user's account at
login). Precedence is Postmark, then SendGrid, then SMTP — first
configured wins.

No live network is used here: httpx.Client is mocked (same pattern as
test_assistant.py's _fake_httpx_client), and the fake token below is not
a real credential. Tests assert the token header is present and
non-empty, but NEVER assert the token value itself.
"""
import smtplib
from unittest.mock import MagicMock

import httpx
import pytest

from app.services import mailer

_FAKE_TOKEN = "fake-postmark-server-token-not-a-real-credential"
POSTMARK_URL = "https://api.postmarkapp.com/email"

SMTP_ENV = {"SMTP_HOST": "smtp.example.com", "SMTP_USER": "user@example.com",
            "SMTP_PASSWORD": "pw"}


def _set_postmark(monkeypatch, **overrides):
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", _FAKE_TOKEN)
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
    response.status_code = 200
    response.text = '{"ErrorCode":0,"Message":"OK"}'
    response.json.return_value = {"ErrorCode": 0, "Message": "OK",
                                  "MessageID": "abc", "To": "to@x.t",
                                  "SubmittedAt": "2026-11-18T00:00:00Z"}
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
def test_is_configured_postmark_token_alone(monkeypatch):
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch)
    assert mailer.is_configured() is True


def test_is_configured_blank_postmark_token_is_unconfigured(monkeypatch):
    _clear_mail_env(monkeypatch)
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "   ")
    assert mailer.is_configured() is False


# ---------------- send_email via Postmark ----------------
def test_postmark_success_200_errorcode_0(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch, SMTP_FROM="user@example.com")
    cls, client, _ = http_mock
    assert mailer.send_email("to@x.t", "Subject", "plain body",
                             "<p>html body</p>") is True
    cls.assert_called_once_with(timeout=10)
    client.post.assert_called_once()
    args, kwargs = client.post.call_args
    assert args[0] == POSTMARK_URL
    headers = kwargs["headers"]
    assert headers["Accept"] == "application/json"
    assert headers["Content-Type"] == "application/json"
    token = headers["X-Postmark-Server-Token"]
    assert token and isinstance(token, str)  # present, never compared
    payload = kwargs["json"]
    assert payload == {
        "From": "FarmMarket <user@example.com>",
        "To": "to@x.t",
        "Subject": "Subject",
        "TextBody": "plain body",
        "HtmlBody": "<p>html body</p>",
        "MessageStream": "outbound",
    }


def test_postmark_text_only_omits_html_body_key(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch, SMTP_USER="user@example.com")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    payload = client.post.call_args[1]["json"]
    assert "HtmlBody" not in payload
    assert payload["TextBody"] == "B"
    # SMTP_FROM unset -> SMTP_USER is the sender, display name FarmMarket.
    assert payload["From"] == "FarmMarket <user@example.com>"


def test_postmark_uses_smtp_from_display_name(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch, SMTP_FROM="Acme Farm <noreply@example.com>")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert (client.post.call_args[1]["json"]["From"]
            == "Acme Farm <noreply@example.com>")


def test_postmark_nonzero_error_code_returns_false(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch, SMTP_USER="user@example.com")
    _, _, response = http_mock
    response.status_code = 200
    response.text = '{"ErrorCode":300,"Message":"Invalid \'From\' address"}'
    response.json.return_value = {"ErrorCode": 300,
                                  "Message": "Invalid 'From' address"}
    assert mailer.send_email("to@x.t", "S", "B") is False


def test_postmark_non_200_returns_false(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch, SMTP_USER="user@example.com")
    _, client, response = http_mock
    for status in (401, 422, 500):
        response.status_code = status
        response.text = "postmark error"
        assert mailer.send_email("to@x.t", "S", "B") is False
    assert client.post.call_count == 3


def test_postmark_bad_json_returns_false(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch, SMTP_USER="user@example.com")
    _, _, response = http_mock
    response.status_code = 200
    response.text = "not json"
    response.json.side_effect = ValueError("bad json")
    assert mailer.send_email("to@x.t", "S", "B") is False


def test_postmark_exception_returns_false_never_raises(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch, SMTP_USER="user@example.com")
    _, client, _ = http_mock
    client.post.side_effect = httpx.ConnectError(
        "boom", request=httpx.Request("POST", POSTMARK_URL))
    assert mailer.send_email("to@x.t", "S", "B") is False


def test_postmark_no_sender_address_returns_false_without_post(monkeypatch,
                                                               http_mock):
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch)  # token set, but no SMTP_FROM/SMTP_USER
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is False
    client.post.assert_not_called()


# ---------------- precedence ----------------
def test_postmark_takes_precedence_over_sendgrid(monkeypatch, http_mock):
    """Both HTTPS transports configured: Postmark wins."""
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch, SMTP_USER="user@example.com")
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.fake-key")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    client.post.assert_called_once()
    assert client.post.call_args[0][0] == POSTMARK_URL


def test_postmark_takes_precedence_over_smtp(monkeypatch, http_mock, smtp_mock):
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch)
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    _, client, _ = http_mock
    smtp_cls, _ = smtp_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    client.post.assert_called_once()
    smtp_cls.assert_not_called()


def test_sendgrid_still_used_without_postmark_token(monkeypatch, http_mock):
    """SendGrid stays the fallback when only its key is set."""
    _clear_mail_env(monkeypatch)
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.fake-key")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    _, client, response = http_mock
    response.status_code = 202  # SendGrid's success status
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert (client.post.call_args[0][0]
            == "https://api.sendgrid.com/v3/mail/send")


# ---------------- reset / verification emails ride the same transport ------
def test_reset_email_uses_postmark(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_postmark(monkeypatch, SMTP_USER="user@example.com")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com")
    _, client, _ = http_mock
    assert mailer.send_password_reset_email("u@x.t", "tok123") is True
    payload = client.post.call_args[1]["json"]
    link = "https://app.example.com/reset-password?token=tok123"
    assert link in payload["TextBody"]
    assert "reset" in payload["Subject"].lower()
