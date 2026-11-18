"""Tests for the SMTP mailer service + forgot-password email wiring.

No real email is ever sent here: smtplib.SMTP is mocked for the unit tests,
and the forgot-password integration tests mock mailer.send_password_reset_email
(BackgroundTasks runs synchronously under TestClient, so the mock is invoked
before the test client returns).
"""
import smtplib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from conftest import register
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


# ---------------- is_configured ----------------
@pytest.mark.parametrize("missing", [None, "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"])
def test_is_configured_matrix(monkeypatch, missing):
    _set_smtp(monkeypatch)
    if missing:
        monkeypatch.delenv(missing)
    assert mailer.is_configured() is (missing is None)


def test_is_configured_blank_host_is_unconfigured(monkeypatch):
    _set_smtp(monkeypatch, SMTP_HOST="   ")
    assert mailer.is_configured() is False


# ---------------- send_email ----------------
def test_send_email_success(monkeypatch, smtp_mock):
    _set_smtp(monkeypatch)
    cls, server = smtp_mock
    assert mailer.send_email("to@x.t", "Subject", "plain body",
                             "<p>html body</p>") is True
    cls.assert_called_once_with("smtp.example.com", 587, timeout=10)
    server.starttls.assert_called_once_with()
    server.login.assert_called_once_with("user@example.com", _TEST_PW)
    server.send_message.assert_called_once()
    msg = server.send_message.call_args[0][0]
    assert msg["To"] == "to@x.t"
    assert msg["Subject"] == "Subject"
    assert msg["From"] == "FarmMarket <user@example.com>"  # SMTP_FROM defaults to SMTP_USER, sent with display name
    assert "plain body" in msg.get_body(preferencelist=("plain",)).get_content()
    assert "html body" in msg.get_body(preferencelist=("html",)).get_content()


def test_send_email_uses_smtp_from(monkeypatch, smtp_mock):
    _set_smtp(monkeypatch, SMTP_FROM="FarmMarket <noreply@example.com>")
    _, server = smtp_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert server.send_message.call_args[0][0]["From"] == "FarmMarket <noreply@example.com>"


def test_send_email_failure_returns_false_never_raises(monkeypatch, smtp_mock):
    _set_smtp(monkeypatch)
    cls, _ = smtp_mock
    cls.side_effect = smtplib.SMTPException("connection refused")
    assert mailer.send_email("to@x.t", "S", "B") is False


def test_send_email_login_failure_returns_false(monkeypatch, smtp_mock):
    _set_smtp(monkeypatch)
    _, server = smtp_mock
    server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad auth")
    assert mailer.send_email("to@x.t", "S", "B") is False


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "FALSE"])
def test_send_email_no_tls_when_disabled(monkeypatch, smtp_mock, value):
    _set_smtp(monkeypatch, SMTP_USE_TLS=value)
    _, server = smtp_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    server.starttls.assert_not_called()


def test_send_email_tls_on_by_default(monkeypatch, smtp_mock):
    _set_smtp(monkeypatch)
    monkeypatch.delenv("SMTP_USE_TLS", raising=False)
    _, server = smtp_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    server.starttls.assert_called_once_with()


def test_send_email_custom_port_and_bad_port_fallback(monkeypatch, smtp_mock):
    _set_smtp(monkeypatch, SMTP_PORT="2525")
    cls, _ = smtp_mock
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert cls.call_args[0][1] == 2525
    monkeypatch.setenv("SMTP_PORT", "not-a-port")
    assert mailer.send_email("to@x.t", "S", "B") is True
    assert cls.call_args[0][1] == 587


# ---------------- public_base_url ----------------
def test_public_base_url_precedence(monkeypatch):
    req = SimpleNamespace(base_url="http://tunnel.example/")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com/")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://front.example.com,https://other.example.com")
    assert mailer.public_base_url(req) == "https://app.example.com"  # PUBLIC_BASE_URL wins
    monkeypatch.delenv("PUBLIC_BASE_URL")
    assert mailer.public_base_url(req) == "https://front.example.com"  # first FRONTEND_ORIGINS entry
    monkeypatch.delenv("FRONTEND_ORIGINS")
    assert mailer.public_base_url(req) == "http://tunnel.example"  # request base, slash stripped
    assert mailer.public_base_url() == "http://localhost:5173"  # fallback


def _req_with_headers(headers, base_url="http://127.0.0.1:8000/"):
    return SimpleNamespace(base_url=base_url, headers=headers)


def _clear_base_env(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)


def test_public_base_url_origin_beats_stale_frontend_origins(monkeypatch):
    """The :5500 bug: FRONTEND_ORIGINS starts with a dead Live Server port,
    but the request came from the vite frontend on :5173 — Origin wins."""
    _clear_base_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_ORIGINS",
                       "http://127.0.0.1:5500,http://localhost:5500,"
                       "http://127.0.0.1:5173,http://localhost:5173")
    req = _req_with_headers({"origin": "http://127.0.0.1:5173"})
    assert mailer.public_base_url(req) == "http://127.0.0.1:5173"


def test_public_base_url_origin_devtunnel(monkeypatch):
    _clear_base_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://127.0.0.1:5500")
    req = _req_with_headers(
        {"origin": "https://farmmarket-5173.inc1.devtunnels.ms"})
    assert mailer.public_base_url(req) == "https://farmmarket-5173.inc1.devtunnels.ms"


def test_public_base_url_env_still_wins_over_origin(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com/")
    req = _req_with_headers({"origin": "http://127.0.0.1:5173"})
    assert mailer.public_base_url(req) == "https://app.example.com"


def test_public_base_url_referer_when_no_origin(monkeypatch):
    _clear_base_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://127.0.0.1:5500")
    req = _req_with_headers(
        {"referer": "http://localhost:5173/forgot-password?x=1"})
    assert mailer.public_base_url(req) == "http://localhost:5173"  # path/query discarded


@pytest.mark.parametrize("bad_origin", [
    "javascript:alert(1)",          # non-http(s) scheme
    "http://user@evil.example",   # userinfo
    "http://evil.example:badport",  # non-numeric port
    "not a url at all",             # no scheme/host
    "ftp://files.example.com",      # non-http(s) scheme
])
def test_public_base_url_malformed_origin_ignored(monkeypatch, bad_origin):
    _clear_base_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://127.0.0.1:5173")
    req = _req_with_headers({"origin": bad_origin})
    assert mailer.public_base_url(req) == "http://127.0.0.1:5173"  # falls through


def test_public_base_url_malformed_origin_falls_to_referer(monkeypatch):
    _clear_base_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://127.0.0.1:5500")
    req = _req_with_headers({"origin": "http://user@evil.example",
                             "referer": "https://good.example.com/login"})
    assert mailer.public_base_url(req) == "https://good.example.com"


def test_public_base_url_malformed_referer_ignored(monkeypatch):
    _clear_base_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://127.0.0.1:5173")
    req = _req_with_headers({"referer": "javascript:alert(1)"})
    assert mailer.public_base_url(req) == "http://127.0.0.1:5173"


def test_public_base_url_no_headers_keeps_old_fallback_chain(monkeypatch):
    _clear_base_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://front.example.com")
    req = _req_with_headers({})
    assert mailer.public_base_url(req) == "https://front.example.com"
    monkeypatch.delenv("FRONTEND_ORIGINS")
    assert mailer.public_base_url(req) == "http://127.0.0.1:8000"  # request base
    assert mailer.public_base_url() == "http://localhost:5173"  # no request at all


# ---------------- reset / verification emails ----------------
def test_send_password_reset_email(monkeypatch):
    calls = []
    monkeypatch.setattr(mailer, "send_email",
                        lambda to, subject, text, html=None: calls.append((to, subject, text, html)) or True)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com")
    assert mailer.send_password_reset_email("u@x.t", "tok123") is True
    to, subject, text, html = calls[0]
    link = "https://app.example.com/reset-password?token=tok123"
    assert to == "u@x.t"
    assert link in text and link in html
    assert "1 hour" in text and "১ ঘণ্টা" in text
    assert "ignore this email" in text
    assert "reset" in subject.lower()


def test_send_verification_email(monkeypatch):
    calls = []
    monkeypatch.setattr(mailer, "send_email",
                        lambda to, subject, text, html=None: calls.append((to, subject, text, html)) or True)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com/")
    assert mailer.send_verification_email("u@x.t", "tok456") is True
    to, subject, text, html = calls[0]
    link = "https://app.example.com/verify-email?token=tok456"
    assert to == "u@x.t"
    assert link in text and link in html
    assert "24 hours" in text and "২৪ ঘণ্টা" in text
    assert "ignore this email" in text


# ---------------- forgot-password wiring ----------------
def _record_send(monkeypatch):
    calls = []

    def fake(to, token, request=None):
        calls.append((to, token))
        return True

    monkeypatch.setattr(mailer, "send_password_reset_email", fake)
    return calls


def test_forgot_password_sends_email_dev(client, monkeypatch):
    """Dev + mailer configured: the email IS sent, but the token is NOT
    returned — the inbox is the only delivery, exactly like production.
    Returning it as well would let anyone reset any account with just
    its email address."""
    _set_smtp(monkeypatch)
    calls = _record_send(monkeypatch)
    register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/auth/forgot-password", json={"email": "f@x.t"})
    assert r.status_code == 200
    assert "reset_token" not in r.json()  # configured mailer => inbox only
    assert len(calls) == 1 and calls[0][0] == "f@x.t" and calls[0][1]


def test_forgot_password_sends_email_production(client, monkeypatch):
    _set_smtp(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    calls = _record_send(monkeypatch)
    register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/auth/forgot-password", json={"email": "f@x.t"})
    assert r.status_code == 200
    assert "reset_token" not in r.json()  # never in production
    assert len(calls) == 1 and calls[0][0] == "f@x.t" and calls[0][1]


def test_forgot_password_unknown_email_sends_nothing(client, monkeypatch):
    _set_smtp(monkeypatch)
    calls = _record_send(monkeypatch)
    r = client.post("/api/v1/auth/forgot-password", json={"email": "ghost@x.t"})
    assert r.status_code == 200 and "reset_token" not in r.json()
    assert calls == []


def test_forgot_password_no_mailer_sends_nothing_but_still_dev_token(client, monkeypatch):
    calls = _record_send(monkeypatch)
    register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/auth/forgot-password", json={"email": "f@x.t"})
    assert r.status_code == 200 and "reset_token" in r.json()
    assert calls == []
