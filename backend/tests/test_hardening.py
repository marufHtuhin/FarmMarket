"""Production-hardening tests: security headers, CORS fail-closed,
production fail-fast, auth rate limiting, health DB check, password
policy, JWT lifetime, global exception handler, reset-mailer warning,
seed production guard."""
import logging
import time as _time

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from conftest import register
from app import schemas
from app.database import get_db
from app.main import (app as app_obj, get_cors_origins,
                      validate_production_config)
from app.security import create_access_token
from app.services import rate_limit


# ---------------- CORS: fail closed in production ----------------
def test_cors_production_wildcard_refused():
    with pytest.raises(RuntimeError, match=r"must not contain '\*'"):
        get_cors_origins(environment="production", raw_origins="*")
    with pytest.raises(RuntimeError):
        get_cors_origins(environment="production",
                         raw_origins="https://shop.example.com, *")


def test_cors_production_unset_is_same_origin_only():
    assert get_cors_origins(environment="production", raw_origins=None) == []


def test_cors_production_explicit_origins_kept():
    assert get_cors_origins(
        environment="production",
        raw_origins="https://farmmarket.example.com, https://www.farmmarket.example.com"
    ) == ["https://farmmarket.example.com", "https://www.farmmarket.example.com"]


def test_cors_dev_default_unchanged():
    assert get_cors_origins(environment="development", raw_origins=None) == [
        "http://127.0.0.1:5500", "http://localhost:5500"]
    # Wildcard is tolerated in dev (local tooling), just not in production.
    assert get_cors_origins(environment="development", raw_origins="*") == ["*"]


# ---------------- production fail-fast ----------------
def test_validate_production_config_rejects_bad_secrets():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production_config(environment="production", secret_key="",
                                   database_url="mysql://x")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production_config(environment="production", secret_key="short",
                                   database_url="mysql://x")
    for demo in ("replace-this-with-a-long-random-secret-key",
                 "demo-only-change-me-in-production"):
        with pytest.raises(RuntimeError, match="demo value"):
            validate_production_config(environment="production", secret_key=demo,
                                       database_url="mysql://x")


def test_validate_production_config_rejects_sqlite():
    with pytest.raises(RuntimeError, match="SQLite"):
        validate_production_config(environment="production",
                                   secret_key="a" * 40,
                                   database_url="sqlite:///./farmmarket.db")


def test_validate_production_config_accepts_good_config():
    # No raise: long random secret + MySQL.
    validate_production_config(environment="production", secret_key="k" * 40,
                               database_url="mysql+pymysql://u:p@h/db")


def test_validate_production_config_noop_outside_production():
    # Dev/test must never trip: empty secret + SQLite is the demo setup.
    validate_production_config(environment="development", secret_key="",
                               database_url="sqlite:///./farmmarket.db")
    validate_production_config(environment="test", secret_key="x",
                               database_url="sqlite:///./farmmarket.db")


# ---------------- security headers ----------------
def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    # microphone=(self): Krishi Bondhu voice input (Web Speech API) needs it;
    # microphone=() would silently break voice for every deployed user.
    assert r.headers["Permissions-Policy"] == (
        "camera=(), microphone=(self), geolocation=()")


# ---------------- health: DB reachability ----------------
def test_health_reports_db_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "project": "FARMMARKET", "db": "ok"}


def test_health_reports_db_unreachable_as_503(client):
    class _BrokenDb:
        def execute(self, *args, **kwargs):
            raise Exception("connection refused")

    app_obj.dependency_overrides[get_db] = lambda: _BrokenDb()
    try:
        r = client.get("/api/health")
    finally:
        app_obj.dependency_overrides.pop(get_db, None)
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "project": "FARMMARKET",
                        "db": "unreachable"}


# ---------------- auth rate limiting ----------------
def test_rate_limiter_unit(monkeypatch):
    rl = rate_limit.RateLimiter(limit=2, window_s=60)
    assert rl.allow("ip1") and rl.allow("ip1") and not rl.allow("ip1")
    assert rl.allow("ip2")  # per-key buckets
    rl.reset()
    assert rl.allow("ip1")


def test_rate_limiter_window_expiry(monkeypatch):
    now = [_time.monotonic()]

    def fake_monotonic():
        return now[0]

    monkeypatch.setattr(rate_limit.time, "monotonic", fake_monotonic)
    rl = rate_limit.RateLimiter(limit=1, window_s=60)
    assert rl.allow("ip1") and not rl.allow("ip1")
    now[0] += 61  # window passed
    assert rl.allow("ip1")


def test_login_rate_limited_429(client, monkeypatch):
    monkeypatch.setattr(rate_limit.login_limiter, "limit", 1)
    register(client, "f@x.t", "farmer")
    ok = client.post("/api/v1/auth/login",
                     json={"email": "f@x.t", "password": "Passw0rd!"})
    assert ok.status_code == 200
    r = client.post("/api/v1/auth/login",
                    json={"email": "f@x.t", "password": "Passw0rd!"})
    assert r.status_code == 429


def test_register_rate_limited_429(client, monkeypatch):
    monkeypatch.setattr(rate_limit.register_limiter, "limit", 1)
    register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/auth/register",
                    json={"name": "Second", "email": "s@x.t",
                          "password": "Passw0rd!", "role": "buyer"})
    assert r.status_code == 429


# ---------------- password policy ----------------
def test_password_min_length_8(client):
    r = client.post("/api/v1/auth/register",
                    json={"name": "Short", "email": "short@x.t",
                          "password": "Abc123!", "role": "buyer"})
    assert r.status_code == 422  # 7 chars: too short
    r = client.post("/api/v1/auth/register",
                    json={"name": "Ok", "email": "ok@x.t",
                          "password": "Abc123!x", "role": "buyer"})
    assert r.status_code == 200  # 8 chars: accepted


def test_reset_password_min_length_8():
    with pytest.raises(ValueError):
        schemas.ResetPasswordIn(token="t", new_password="Abc123!")
    assert schemas.ResetPasswordIn(token="t", new_password="Abc123!x")


# ---------------- JWT lifetime ----------------
def test_access_token_default_lifetime_is_60_minutes():
    from app import security

    assert security.EXPIRE_MINUTES == 60
    token = create_access_token(123)
    payload = jwt.decode(token, security.SECRET_KEY,
                         algorithms=[security.ALGORITHM],
                         options={"verify_exp": False})
    remaining = payload["exp"] - _time.time()
    assert 55 * 60 < remaining <= 60 * 60


# ---------------- global exception handler ----------------
def test_unhandled_exception_is_generic_500(client, monkeypatch):
    import app.main as main_module

    register(client, "f@x.t", "farmer")

    def _boom(*args, **kwargs):
        raise RuntimeError("database exploded (must not leak)")

    monkeypatch.setattr(main_module, "verify_password", _boom)
    # ServerErrorMiddleware sends the 500 response and then re-raises (so
    # uvicorn logs it); the test client must not re-raise it, or the
    # response is never observed.
    quiet_client = TestClient(app_obj, raise_server_exceptions=False)
    r = quiet_client.post("/api/v1/auth/login",
                          json={"email": "f@x.t", "password": "Passw0rd!"})
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error"}
    assert "exploded" not in r.text
    assert "Traceback" not in r.text


def test_http_exceptions_unchanged_by_global_handler(client):
    # 401 and 404 keep their existing shapes — the generic handler must not
    # swallow HTTPException.
    assert client.get("/api/v1/assistant/conversations").status_code == 401
    assert client.get("/api/v1/no-such-route").status_code == 404


# ---------------- password reset in production ----------------
def test_forgot_password_production_warns_no_mailer(client, monkeypatch, caplog):
    monkeypatch.setenv("ENVIRONMENT", "production")
    register(client, "f@x.t", "farmer")
    with caplog.at_level(logging.WARNING, logger="app.main"):
        r = client.post("/api/v1/auth/forgot-password", json={"email": "f@x.t"})
    assert r.status_code == 200
    assert "reset_token" not in r.json()  # still excluded in production
    assert "no mailer configured" in caplog.text
    assert "NOT delivered" in caplog.text


# ---------------- seed_demo production guard ----------------
def test_seed_refuses_production_without_flag(monkeypatch):
    import seed_demo

    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(SystemExit) as excinfo:
        seed_demo.main([])
    assert excinfo.value.code != 0


def test_seed_proceeds_with_allow_production_flag(monkeypatch):
    import seed_demo

    monkeypatch.setenv("ENVIRONMENT", "production")
    # Guard passed => main proceeds to DB work; prove it by breaking the
    # session factory instead of running the (slow) full seed.
    monkeypatch.setattr(seed_demo, "SessionLocal",
                        lambda: (_ for _ in ()).throw(RuntimeError("proceeded")))
    with pytest.raises(RuntimeError, match="proceeded"):
        seed_demo.main(["--allow-production"])


def test_seed_proceeds_in_development(monkeypatch):
    import seed_demo

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(seed_demo, "SessionLocal",
                        lambda: (_ for _ in ()).throw(RuntimeError("proceeded")))
    with pytest.raises(RuntimeError, match="proceeded"):
        seed_demo.main([])
