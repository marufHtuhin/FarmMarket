"""Tests for the Mailjet HTTPS mailer transport (mailer.py).

Mailjet is the PRIMARY transport for Render free (Render's free plan
blocks outbound SMTP ports; Postmark requires a work email at signup and
SendGrid blocked this user's account at login). Precedence is Mailjet,
then Postmark, then SendGrid, then SMTP — first configured wins. Mailjet
is configured only when BOTH the API key and the secret key are set.

No live network is used here: httpx.Client is mocked (same pattern as
test_assistant.py's _fake_httpx_client), and the fake credentials below
are not real. Tests assert Basic auth is wired (a 2-tuple of non-empty
strings) but NEVER assert the credential values themselves.
"""
import smtplib
from unittest.mock import MagicMock

import httpx
import pytest

from app.services import mailer

_FAKE_KEY = "fake-mailjet-api-key-not-a-real-credential"
_FAKE_SECRET = "fake-mailjet-api-secret-not-a-real-credential"
MAILJET_URL = "https://api.mailjet.com/v3.1/send"

SMTP_ENV = {"SMTP_HOST": "smtp.example.com", "SMTP_USER": "user@example.com",
            "SMTP_PASSWORD": "pw"}


def _set_mailjet(monkeypatch, **overrides):
    monkeypatch.setenv("MAILJET_API_KEY", _FAKE_KEY)
    monkeypatch.setenv("MAILJET_API_SECRET", _FAKE_SECRET)
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
    response.text = '{"Messages":[{"Status":"success"}]}'
    response.json.return_value = {
        "Messages": [{"Status": "success",
                      "To": [{"Email": "to@x.t", "MessageID": 1,
                              "MessageUUID": "uuid",
                              "MessageHref": "https://api.mailjet.com/v3/message/1"}]}]}
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
def test_is_configured_mailjet_key_and_secret(monkeypatch):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch)
    assert mailer.is_configured() is True


@pytest.mark.parametrize("missing", ["MAILJET_API_KEY", "MAILJET_API_SECRET"])
def test_is_configured_mailjet_needs_both(monkeypatch, missing):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch)
    monkeypatch.delenv(missing)
    assert mailer.is_configured() is False


def test_is_configured_blank_mailjet_secret_is_unconfigured(monkeypatch):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch)
    monkeypatch.setenv("MAILJET_API_SECRET", "   ")
    assert mailer.is_configured() is False


# ---------------- send_email via Mailjet ----------------
def test_mailjet_success_200_status_success(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch, SMTP_FROM="user@example.com")
    cls, client, _ = http_mock
    assert mailer.send_email("to@x.t", "Subject", "plain body",
                             "<p>html body</p>") is True
    assert cls.call_args[1]["timeout"] == 10
    auth = cls.call_args[1]["auth"]
    assert isinstance(auth, tuple) and len(auth) == 2
    assert all(isinstance(v, str) and v for v in auth)  # Basic auth wired
    client.post.assert_called_once()
    args, kwargs = client.post.call_args
    assert args[0] == MAILJET_URL
    assert kwargs["json"] == {"Messages": [{
        "From": {"Email": "user@example.com", "Name": "FarmMarket"},
        "To": [{"Email": "to@x.t"}],
        "Subject": "Subject",
        "TextPart": "plain body",
        "HTMLPart": "<p>html body</p>",
    }]}


def test_mailjet_text_only_omits_html_part_key(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch, SMTP_USER="user@example.com")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    message = client.post.call_args[1]["json"]["Messages"][0]
    assert "HTMLPart" not in message
    assert message["TextPart"] == "B"
    # SMTP_FROM unset -> SMTP_USER is the sender, name FarmMarket.
    assert message["From"] == {"Email": "user@example.com",
                               "Name": "FarmMarket"}


def test_mailjet_uses_smtp_from_display_name(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch, SMTP_FROM="Acme Farm <noreply@example.com>")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert (client.post.call_args[1]["json"]["Messages"][0]["From"]
            == {"Email": "noreply@example.com", "Name": "Acme Farm"})


def test_mailjet_status_error_returns_false(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch, SMTP_USER="user@example.com")
    _, _, response = http_mock
    response.status_code = 200
    response.text = '{"Messages":[{"Status":"error","Errors":[{"ErrorMessage":"sender not verified"}]}]}'
    response.json.return_value = {
        "Messages": [{"Status": "error",
                      "Errors": [{"ErrorMessage": "sender not verified"}]}]}
    assert mailer.send_email("to@x.t", "S", "B") is False


def test_mailjet_non_200_returns_false(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch, SMTP_USER="user@example.com")
    _, client, response = http_mock
    for status in (400, 401, 500):
        response.status_code = status
        response.text = "mailjet error"
        assert mailer.send_email("to@x.t", "S", "B") is False
    assert client.post.call_count == 3


def test_mailjet_bad_json_returns_false(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch, SMTP_USER="user@example.com")
    _, _, response = http_mock
    response.status_code = 200
    response.text = "not json"
    response.json.side_effect = ValueError("bad json")
    assert mailer.send_email("to@x.t", "S", "B") is False


def test_mailjet_empty_messages_returns_false(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch, SMTP_USER="user@example.com")
    _, _, response = http_mock
    response.status_code = 200
    response.text = '{"Messages":[]}'
    response.json.return_value = {"Messages": []}
    assert mailer.send_email("to@x.t", "S", "B") is False


def test_mailjet_exception_returns_false_never_raises(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch, SMTP_USER="user@example.com")
    _, client, _ = http_mock
    client.post.side_effect = httpx.ConnectError(
        "boom", request=httpx.Request("POST", MAILJET_URL))
    assert mailer.send_email("to@x.t", "S", "B") is False


def test_mailjet_no_sender_address_returns_false_without_post(monkeypatch,
                                                              http_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch)  # creds set, but no SMTP_FROM/SMTP_USER
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is False
    client.post.assert_not_called()


# ---------------- precedence ----------------
def test_mailjet_takes_precedence_over_postmark(monkeypatch, http_mock):
    """Mailjet creds + Postmark token both set: Mailjet wins."""
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch, SMTP_USER="user@example.com")
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "fake-postmark-token")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    client.post.assert_called_once()
    assert client.post.call_args[0][0] == MAILJET_URL


def test_mailjet_takes_precedence_over_sendgrid(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch, SMTP_USER="user@example.com")
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.fake-key")
    _, client, _ = http_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    client.post.assert_called_once()
    assert client.post.call_args[0][0] == MAILJET_URL


def test_mailjet_takes_precedence_over_smtp(monkeypatch, http_mock, smtp_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch)
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)
    _, client, _ = http_mock
    smtp_cls, _ = smtp_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    client.post.assert_called_once()
    smtp_cls.assert_not_called()


def test_postmark_still_used_without_mailjet(monkeypatch, http_mock):
    """Postmark stays the fallback when only its token is set."""
    _clear_mail_env(monkeypatch)
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "fake-postmark-token")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    _, client, response = http_mock
    response.json.return_value = {"ErrorCode": 0, "Message": "OK"}
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert (client.post.call_args[0][0]
            == "https://api.postmarkapp.com/email")


# ---------------- reset / verification emails ride the same transport ------
def test_reset_email_uses_mailjet(monkeypatch, http_mock):
    _clear_mail_env(monkeypatch)
    _set_mailjet(monkeypatch, SMTP_USER="user@example.com")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com")
    _, client, _ = http_mock
    assert mailer.send_password_reset_email("u@x.t", "tok123") is True
    message = client.post.call_args[1]["json"]["Messages"][0]
    link = "https://app.example.com/reset-password?token=tok123"
    assert link in message["TextPart"]
    assert "reset" in message["Subject"].lower()
