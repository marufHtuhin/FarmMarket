"""Email verification on registration (WS-B).

Covers: verify-email happy path / invalid / expired / used, resend
(invalidation, rate limit, already-verified), register resilience when
the mailer is absent/unconfigured/failing, dev-vs-prod token exposure,
login staying allowed for unverified users, and the Alembic migration
(fresh DB + pre-existing users).

The mailer (services/mailer.py) is real, but these tests stub it by
inserting a fake module into sys.modules (the production code
lazy-imports it inside the endpoint, so the stub is picked up) and
setting it as an attribute on the services package, so no real SMTP
traffic is ever attempted. Both are cleaned up by monkeypatch teardown.
"""
import os
import sqlite3
import subprocess
import sys
import types
from datetime import timedelta
from pathlib import Path

import pytest

from app import models
from app.config import utcnow
from app.security import hash_token
from tests.conftest import register

BACKEND_DIR = Path(__file__).resolve().parent.parent
PREV_HEAD = "a1b2c3d4e5f6"  # alembic head before this batch's migration


@pytest.fixture
def stub_mailer(monkeypatch):
    """Fake app.services.mailer exposing the WS-A contract."""
    fake = types.ModuleType("app.services.mailer")
    fake.sent = []
    fake.is_configured = lambda: True
    fake.public_base_url = lambda request=None: "http://testserver"
    fake.send_email = lambda to, subject, text_body, html_body=None: True
    fake.send_password_reset_email = lambda to, token, request=None: True

    def _send_verification(to, token, request=None):
        fake.sent.append((to, token))
        return True

    fake.send_verification_email = _send_verification
    monkeypatch.setitem(sys.modules, "app.services.mailer", fake)
    import app.services as services_pkg

    monkeypatch.setattr(services_pkg, "mailer", fake, raising=False)
    return fake


@pytest.fixture
def failing_mailer(stub_mailer, monkeypatch):
    """Mailer is configured but every send raises (SMTP down)."""
    def _boom(to, token, request=None):
        raise RuntimeError("SMTP connection refused")

    stub_mailer.send_verification_email = _boom
    return stub_mailer


@pytest.fixture
def unconfigured_mailer(stub_mailer):
    stub_mailer.is_configured = lambda: False
    return stub_mailer


def _user(db, email):
    db.expire_all()
    return db.query(models.User).filter_by(email=email).first()


def _tokens(db, user_id):
    db.expire_all()
    return db.query(models.EmailVerificationToken).filter_by(user_id=user_id).all()


def _register_dev(client, email="verify@x.t"):
    """Register in dev mode; returns (headers, register response json)."""
    r = client.post("/api/v1/auth/register", json={
        "name": "Verify User", "email": email, "password": "Passw0rd!",
        "role": "farmer", "district": "Gazipur"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}, r.json()


# --- verify-email ------------------------------------------------------------

def test_verify_email_happy_path(client, db, stub_mailer):
    headers, resp = _register_dev(client)
    # Dev + configured mailer: the token is NOT in the response — the
    # inbox is the only delivery. The test reads it from the sent mail.
    assert "verification_token" not in resp
    assert len(stub_mailer.sent) == 1
    token = stub_mailer.sent[0][1]
    assert stub_mailer.sent == [("verify@x.t", token)]
    assert _user(db, "verify@x.t").email_verified is False

    r = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    assert r.json() == {"verified": True}
    assert _user(db, "verify@x.t").email_verified is True
    assert _tokens(db, _user(db, "verify@x.t").id)[0].used is True

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email_verified"] is True


def test_verify_email_invalid_token(client):
    r = client.post("/api/v1/auth/verify-email",
                    json={"token": "not-a-real-token"})
    assert r.status_code == 400


def test_verify_email_expired_token(client, db):
    register(client, "exp@x.t", "farmer")
    user = _user(db, "exp@x.t")
    db.add(models.EmailVerificationToken(
        user_id=user.id, token_hash=hash_token("expired-token"),
        expires_at=utcnow() - timedelta(minutes=1)))
    db.commit()
    r = client.post("/api/v1/auth/verify-email",
                    json={"token": "expired-token"})
    assert r.status_code == 400
    assert _user(db, "exp@x.t").email_verified is False


def test_verify_email_used_token_rejected(client):
    _, resp = _register_dev(client)
    token = resp["verification_token"]
    assert client.post("/api/v1/auth/verify-email",
                       json={"token": token}).status_code == 200
    # Second use of the same token must fail.
    r = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 400


def test_me_reports_email_verified_false_for_new_user(client):
    headers, _ = _register_dev(client)
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email_verified"] is False


# --- resend-verification -----------------------------------------------------

def test_resend_invalidates_old_token_and_issues_fresh(client, db, stub_mailer):
    headers, resp = _register_dev(client)
    assert "verification_token" not in resp  # configured mailer => inbox only
    old_token = stub_mailer.sent[0][1]
    assert len(stub_mailer.sent) == 1

    r = client.post("/api/v1/auth/resend-verification", headers=headers)
    assert r.status_code == 200, r.text
    assert len(stub_mailer.sent) == 2
    new_token = stub_mailer.sent[1][1]
    assert new_token != old_token

    # Old token is dead; the fresh one works.
    assert client.post("/api/v1/auth/verify-email",
                       json={"token": old_token}).status_code == 400
    assert client.post("/api/v1/auth/verify-email",
                       json={"token": new_token}).status_code == 200
    assert _user(db, "verify@x.t").email_verified is True


def test_resend_rate_limit_enforced(client, monkeypatch):
    from app.services.rate_limit import resend_limiter

    monkeypatch.setattr(resend_limiter, "limit", 2)
    headers, _ = _register_dev(client)
    assert client.post("/api/v1/auth/resend-verification",
                       headers=headers).status_code == 200
    assert client.post("/api/v1/auth/resend-verification",
                       headers=headers).status_code == 200
    r = client.post("/api/v1/auth/resend-verification", headers=headers)
    assert r.status_code == 429


def test_resend_requires_auth(client):
    assert client.post("/api/v1/auth/resend-verification").status_code == 401


def test_resend_when_already_verified_returns_success(client, db, stub_mailer):
    headers, resp = _register_dev(client)
    token = stub_mailer.sent[0][1]  # configured mailer: token via email only
    assert client.post("/api/v1/auth/verify-email",
                       json={"token": token}).status_code == 200
    sent_before = len(stub_mailer.sent)
    r = client.post("/api/v1/auth/resend-verification", headers=headers)
    assert r.status_code == 200
    assert "already verified" in r.json()["message"].lower()
    # No new token issued, no email sent.
    assert len(stub_mailer.sent) == sent_before
    assert len(_tokens(db, _user(db, "verify@x.t").id)) == 1


# --- register resilience -----------------------------------------------------

def test_register_without_mailer_module_succeeds(client, db, monkeypatch):
    """Mailer module unimportable (simulated absence): registration still
    creates the user and the token; the dev response carries the token."""
    # Simulate a missing mailer module: None in sys.modules makes the
    # import raise ImportError, and the package attribute must go too or
    # `from .services import mailer` falls back to it.
    monkeypatch.setitem(sys.modules, "app.services.mailer", None)
    monkeypatch.delattr("app.services.mailer", raising=False)
    headers, resp = _register_dev(client, "nomailer@x.t")
    assert "verification_token" in resp
    user = _user(db, "nomailer@x.t")
    assert user is not None
    assert len(_tokens(db, user.id)) == 1
    # The dev token actually verifies the account (no mailer needed).
    assert client.post("/api/v1/auth/verify-email",
                       json={"token": resp["verification_token"]}).status_code == 200


def test_register_with_unconfigured_mailer_succeeds(client, db, unconfigured_mailer):
    _, resp = _register_dev(client, "unconf@x.t")
    assert "verification_token" in resp
    assert unconfigured_mailer.sent == []
    user = _user(db, "unconf@x.t")
    assert user is not None
    assert len(_tokens(db, user.id)) == 1


def test_register_dev_with_configured_mailer_hides_token(client, db, stub_mailer):
    """Dev + mailer configured: the confirmation email is queued but the
    token is NOT in the response — the inbox is the only delivery,
    exactly like production (mirrors the forgot-password rule)."""
    _, resp = _register_dev(client, "conf@x.t")
    assert "verification_token" not in resp
    assert len(stub_mailer.sent) == 1
    assert stub_mailer.sent[0][0] == "conf@x.t"
    user = _user(db, "conf@x.t")
    assert user is not None
    assert len(_tokens(db, user.id)) == 1


def test_register_with_failing_mailer_succeeds(client, db, failing_mailer):
    """SMTP down mid-send: the background task swallows the failure and
    registration still returns 200 with a usable account. The mailer IS
    configured, so the token is NOT in the response — the user can
    request a resend once SMTP is back."""
    _, resp = _register_dev(client, "failmail@x.t")
    assert "verification_token" not in resp
    user = _user(db, "failmail@x.t")
    assert user is not None
    assert len(_tokens(db, user.id)) == 1


def test_register_token_never_in_production_response(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    r = client.post("/api/v1/auth/register", json={
        "name": "Prod User", "email": "prod@x.t", "password": "Passw0rd!",
        "role": "buyer", "district": "Dhaka"})
    assert r.status_code == 200, r.text
    assert "verification_token" not in r.json()
    assert "reset_token" not in r.json()


def test_login_allowed_for_unverified_user(client):
    _register_dev(client, "unverified@x.t")
    r = client.post("/api/v1/auth/login",
                    json={"email": "unverified@x.t", "password": "Passw0rd!"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email_verified"] is False


# --- migration ---------------------------------------------------------------

def _alembic(*args, db_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=180)


def test_migration_applies_on_fresh_db(tmp_path):
    db_path = tmp_path / "fresh.db"
    r = _alembic("upgrade", "head", db_path=db_path)
    assert r.returncode == 0, r.stderr
    con = sqlite3.connect(db_path)
    tables = {row[0] for row in
              con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "email_verification_tokens" in tables
    cols = {row[1] for row in con.execute("PRAGMA table_info(users)")}
    assert "email_verified" in cols
    assert con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0] == "f07c52b75221"
    con.close()


def test_migration_upgrades_db_with_existing_users(tmp_path):
    """Pre-migration DB (at the old head) with users: upgrade head must
    succeed and existing rows must default to email_verified=False."""
    db_path = tmp_path / "existing.db"
    r = _alembic("upgrade", PREV_HEAD, db_path=db_path)
    assert r.returncode == 0, r.stderr
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO users (name, email, phone, password_hash, role, "
        "district, upazila, business_name, is_verified, country_code, "
        "created_at) VALUES (?, ?, '', 'x', 'farmer', '', '', '', 0, 'BD', "
        "'2026-11-18 00:00:00')", ("Old User", "old@x.t"))
    con.commit()
    con.close()

    r = _alembic("upgrade", "head", db_path=db_path)
    assert r.returncode == 0, r.stderr
    con = sqlite3.connect(db_path)
    row = con.execute(
        "SELECT email_verified FROM users WHERE email='old@x.t'").fetchone()
    assert row is not None and row[0] == 0
    con.close()
