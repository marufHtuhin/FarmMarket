"""End-to-end email-link tests: the reset/verification link in the sent
email must start with the Origin the request actually came from.

No real email is ever sent: smtplib.SMTP is mocked and the sent message
is captured. BackgroundTasks runs synchronously under TestClient, so the
mock is invoked before the test client returns.
"""
import smtplib
from unittest.mock import MagicMock

import pytest

from conftest import register
from app.services import mailer

SMTP_ENV = {"SMTP_HOST": "smtp.example.com", "SMTP_USER": "user@example.com",
            "SMTP_PASSWORD": "pw"}


@pytest.fixture()
def smtp_capture(monkeypatch):
    """Mock smtplib.SMTP; yields the list of sent EmailMessage objects."""
    sent = []
    server = MagicMock()
    server.send_message.side_effect = lambda msg: sent.append(msg)
    cls = MagicMock(return_value=server)
    server.__enter__.return_value = server
    monkeypatch.setattr(smtplib, "SMTP", cls)
    return sent


def _set_smtp(monkeypatch):
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)


def _reset_link(messages):
    """The reset-password link from the captured reset email."""
    for msg in messages:
        body = msg.get_body(preferencelist=("plain",)).get_content()
        for line in body.splitlines():
            line = line.strip()
            if "/reset-password?token=" in line:
                return line
    raise AssertionError("no reset-password link in any captured email")


def test_forgot_password_link_uses_origin(monkeypatch, client, smtp_capture):
    """Local dev case: FRONTEND_ORIGINS still starts with the stale :5500
    Live Server entry, but the request came from the vite frontend on
    :5173 — the emailed link must point at :5173, not :5500."""
    _set_smtp(monkeypatch)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("FRONTEND_ORIGINS",
                       "http://127.0.0.1:5500,http://localhost:5500,"
                       "http://127.0.0.1:5173,http://localhost:5173")
    register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/auth/forgot-password", json={"email": "f@x.t"},
                    headers={"Origin": "http://127.0.0.1:5173"})
    assert r.status_code == 200
    link = _reset_link(smtp_capture)
    assert link.startswith("http://127.0.0.1:5173/reset-password?token=")
    assert ":5500" not in link


def test_forgot_password_link_uses_devtunnel_origin(monkeypatch, client, smtp_capture):
    _set_smtp(monkeypatch)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://127.0.0.1:5500")
    register(client, "f@x.t", "farmer")
    origin = "https://farmmarket-5173.inc1.devtunnels.ms"
    r = client.post("/api/v1/auth/forgot-password", json={"email": "f@x.t"},
                    headers={"Origin": origin})
    assert r.status_code == 200
    assert _reset_link(smtp_capture).startswith(
        origin + "/reset-password?token=")


def test_forgot_password_link_public_base_url_wins_over_origin(monkeypatch, client, smtp_capture):
    _set_smtp(monkeypatch)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com")
    register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/auth/forgot-password", json={"email": "f@x.t"},
                    headers={"Origin": "http://127.0.0.1:5173"})
    assert r.status_code == 200
    assert _reset_link(smtp_capture).startswith(
        "https://app.example.com/reset-password?token=")


def test_forgot_password_link_no_origin_falls_back(monkeypatch, client, smtp_capture):
    """No Origin/Referer (e.g. a scripted request): the old fallback chain
    applies — first FRONTEND_ORIGINS entry."""
    _set_smtp(monkeypatch)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://127.0.0.1:5173")
    register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/auth/forgot-password", json={"email": "f@x.t"})
    assert r.status_code == 200
    assert _reset_link(smtp_capture).startswith(
        "http://127.0.0.1:5173/reset-password?token=")
