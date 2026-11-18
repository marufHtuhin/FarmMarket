"""Admin-only Gemini diagnostic endpoint: GET /api/v1/assistant/status.

Lives in its own file (not test_assistant.py) by coordinator instruction:
test_assistant.py is owned by the parent agent's REST-transport work.

The endpoint is built on gemini_assistant.LAST_GEMINI_ERROR /
get_last_gemini_error() (parent commit 0c3c552). These tests set
LAST_GEMINI_ERROR directly to prove surfacing, including timeouts.
"""
import pytest

from conftest import register
from app import models
from app.security import create_access_token, hash_password
from app.services import gemini_assistant as GA


@pytest.fixture(autouse=True)
def _clean_last_error():
    GA.LAST_GEMINI_ERROR.clear()
    yield
    GA.LAST_GEMINI_ERROR.clear()


def _admin_headers(db):
    """Admin users cannot self-register; create one directly in the DB."""
    u = models.User(email="admin@x.t", name="Admin", role="admin",
                    district="Dhaka", password_hash=hash_password("Passw0rd!"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"Authorization": "Bearer " + create_access_token(u.id)}


def test_status_admin_200_no_key_no_error(client, db, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    r = client.get("/api/v1/assistant/status", headers=_admin_headers(db))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["key_configured"] is False
    assert body["model"] == "gemini-3.8-flash"
    assert body["last_gemini_error"] is None


def test_status_key_configured_and_model_override(client, db, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-never-returned")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    r = client.get("/api/v1/assistant/status", headers=_admin_headers(db))
    assert r.status_code == 200
    body = r.json()
    assert body["key_configured"] is True
    assert body["model"] == "gemini-test-model"
    # The key itself must never appear in the response, in whole or in part.
    assert "test-key-never-returned" not in r.text


def test_status_non_admin_403(client, db):
    farmer = register(client, "f@x.t", "farmer")
    assert client.get("/api/v1/assistant/status", headers=farmer).status_code == 403


def test_status_unauthenticated_401(client):
    assert client.get("/api/v1/assistant/status").status_code == 401


def test_status_surfaces_last_error_including_timeout(client, db):
    # A timeout is an error like any other: it must show up with its type,
    # message and timestamp (this is the exact failure the user hit live).
    GA.LAST_GEMINI_ERROR.update({
        "type": "TimeoutError",
        "message": "Gemini call exceeded 20s",
        "at": "2026-11-16T22:20:00+00:00",
    })
    r = client.get("/api/v1/assistant/status", headers=_admin_headers(db))
    assert r.status_code == 200
    err = r.json()["last_gemini_error"]
    assert err["type"] == "TimeoutError"
    assert "20s" in err["message"]
    assert err["at"] == "2026-11-16T22:20:00+00:00"


def test_status_surfaces_api_error(client, db):
    GA.LAST_GEMINI_ERROR.update({
        "type": "RuntimeError",
        "message": "Gemini API error 404: model not found",
        "at": "2026-11-16T22:21:00+00:00",
    })
    r = client.get("/api/v1/assistant/status", headers=_admin_headers(db))
    assert r.status_code == 200
    assert r.json()["last_gemini_error"]["type"] == "RuntimeError"
