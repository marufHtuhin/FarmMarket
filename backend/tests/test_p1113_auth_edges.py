"""Phase 11 (audit/p11-13): auth edge cases that the existing suite did not
cover — duplicate registration, validation boundaries, wrong/expired/
malformed tokens, refresh-token expiry, reset-token expiry + invalidation,
and refresh-token revocation on password reset."""
from datetime import datetime, timedelta

import pytest
from jose import jwt

from conftest import register
from app import models
from app.security import SECRET_KEY, ALGORITHM, create_access_token, hash_token


def _login(client, email, password="Passw0rd!"):
    return client.post("/api/v1/auth/login",
                       json={"email": email, "password": password})


# ---------------- registration validation ----------------
def test_register_duplicate_email_409(client):
    register(client, "dup@x.t", "farmer")
    r = client.post("/api/v1/auth/register",
                    json={"name": "Again", "email": "dup@x.t",
                          "password": "Passw0rd!", "role": "buyer"})
    assert r.status_code == 409
    assert "already registered" in r.json()["detail"]


def test_register_invalid_email_422(client):
    r = client.post("/api/v1/auth/register",
                    json={"name": "Bad", "email": "not-an-email",
                          "password": "Passw0rd!", "role": "buyer"})
    assert r.status_code == 422


def test_register_short_name_422(client):
    r = client.post("/api/v1/auth/register",
                    json={"name": "A", "email": "a@x.t",
                          "password": "Passw0rd!", "role": "buyer"})
    assert r.status_code == 422


def test_register_password_over_72_utf8_bytes_422(client):
    # 37 two-byte chars = 74 UTF-8 bytes but only 37 characters, so the
    # bcrypt byte-length validator (not the char max_length) must reject it.
    pw = "é" * 37
    assert len(pw.encode("utf-8")) == 74
    r = client.post("/api/v1/auth/register",
                    json={"name": "Bytes", "email": "bytes@x.t",
                          "password": pw, "role": "buyer"})
    assert r.status_code == 422


def test_register_unknown_role_400(client):
    r = client.post("/api/v1/auth/register",
                    json={"name": "Root", "email": "root@x.t",
                          "password": "Passw0rd!", "role": "superuser"})
    assert r.status_code == 400


def test_register_missing_password_422(client):
    r = client.post("/api/v1/auth/register",
                    json={"name": "NoPass", "email": "nopass@x.t",
                          "role": "buyer"})
    assert r.status_code == 422


# ---------------- login failures ----------------
def test_login_wrong_password_401(client):
    register(client, "f@x.t", "farmer")
    r = _login(client, "f@x.t", "WrongPass1!")
    assert r.status_code == 401
    assert "Incorrect email or password" in r.json()["detail"]


def test_login_unknown_email_401(client):
    r = _login(client, "ghost@x.t")
    assert r.status_code == 401
    # Same message as a wrong password: no user enumeration.
    assert "Incorrect email or password" in r.json()["detail"]


def test_login_invalid_email_shape_422(client):
    r = client.post("/api/v1/auth/login",
                    json={"email": "not-an-email", "password": "whatever"})
    assert r.status_code == 422


# ---------------- /auth/me token edge cases ----------------
def test_me_without_token_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_malformed_token_401(client):
    r = client.get("/api/v1/auth/me",
                   headers={"Authorization": "Bearer this.is.not.a.jwt"})
    assert r.status_code == 401


def test_me_token_signed_with_wrong_key_401(client):
    bad = jwt.encode({"sub": "1",
                      "exp": datetime.utcnow() + timedelta(minutes=60)},
                     "a-different-secret-key", algorithm=ALGORITHM)
    r = client.get("/api/v1/auth/me",
                   headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_me_expired_token_401(client):
    expired = jwt.encode({"sub": "1",
                          "exp": datetime.utcnow() - timedelta(minutes=1)},
                         SECRET_KEY, algorithm=ALGORITHM)
    r = client.get("/api/v1/auth/me",
                   headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_me_token_for_nonexistent_user_401(client):
    token = create_access_token(999999)
    r = client.get("/api/v1/auth/me",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_me_returns_profile_shape(client):
    h = register(client, "f@x.t", "farmer")
    r = client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "f@x.t" and body["role"] == "farmer"
    assert "password_hash" not in body and "password" not in body


# ---------------- refresh-token expiry ----------------
def test_refresh_expired_token_401_and_revoked(client, db):
    register(client, "f@x.t", "farmer")
    user = db.query(models.User).filter_by(email="f@x.t").first()
    db.add(models.RefreshToken(
        user_id=user.id, token_hash=hash_token("stale-refresh-token"),
        expires_at=datetime.utcnow() - timedelta(minutes=1)))
    db.commit()
    r = client.post("/api/v1/auth/refresh",
                    json={"refresh_token": "stale-refresh-token"})
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()
    # The expired record is revoked so it cannot be replayed.
    rec = db.query(models.RefreshToken).filter_by(
        token_hash=hash_token("stale-refresh-token")).first()
    assert rec.revoked is True


# ---------------- password reset edge cases ----------------
def test_reset_expired_token_400(client, db):
    register(client, "f@x.t", "farmer")
    user = db.query(models.User).filter_by(email="f@x.t").first()
    db.add(models.PasswordResetToken(
        user_id=user.id, token_hash=hash_token("stale-reset-token"),
        expires_at=datetime.utcnow() - timedelta(minutes=1)))
    db.commit()
    r = client.post("/api/v1/auth/reset-password",
                    json={"token": "stale-reset-token",
                          "new_password": "NewPass1!"})
    assert r.status_code == 400


def test_forgot_password_invalidates_earlier_token(client):
    register(client, "f@x.t", "farmer")
    first = client.post("/api/v1/auth/forgot-password",
                        json={"email": "f@x.t"}).json()["reset_token"]
    client.post("/api/v1/auth/forgot-password", json={"email": "f@x.t"})
    r = client.post("/api/v1/auth/reset-password",
                    json={"token": first, "new_password": "NewPass1!"})
    assert r.status_code == 400


def test_reset_password_revokes_refresh_tokens(client):
    register(client, "f@x.t", "farmer")
    refresh = _login(client, "f@x.t").json()["refresh_token"]
    token = client.post("/api/v1/auth/forgot-password",
                        json={"email": "f@x.t"}).json()["reset_token"]
    assert client.post("/api/v1/auth/reset-password",
                       json={"token": token,
                             "new_password": "NewPass1!"}).status_code == 200
    # The pre-reset refresh token must no longer rotate.
    assert client.post("/api/v1/auth/refresh",
                       json={"refresh_token": refresh}).status_code == 401
    # ...but the user can log in again with the new password.
    assert _login(client, "f@x.t", "NewPass1!").status_code == 200


def test_reset_password_short_new_password_422(client):
    register(client, "f@x.t", "farmer")
    token = client.post("/api/v1/auth/forgot-password",
                        json={"email": "f@x.t"}).json()["reset_token"]
    r = client.post("/api/v1/auth/reset-password",
                    json={"token": token, "new_password": "short"})
    assert r.status_code == 422
