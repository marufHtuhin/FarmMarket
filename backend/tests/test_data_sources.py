"""External data-source registry (Phase 3) tests: admin-only list + sync.

The World Bank sync test asserts the response SHAPE (status "ok" or "error"),
not success, because the sandbox may have no network access to the API.
"""
from conftest import register
from app import models
from app.security import create_access_token, hash_password


def make_user(db, email, role):
    """Create a user directly in the DB (needed for admin: register rejects it)."""
    u = models.User(email=email, name="Test User", role=role, district="Dhaka",
                    password_hash=hash_password("Passw0rd!"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def auth_headers(user):
    return {"Authorization": "Bearer " + create_access_token(user.id)}


def _admin(client, db):
    return auth_headers(make_user(db, "admin@x.t", "admin"))


def test_list_requires_admin(client, db):
    farmer = register(client, "f@x.t", "farmer")
    assert client.get("/api/v1/admin/data-sources", headers=farmer).status_code == 403
    assert client.get("/api/v1/admin/data-sources").status_code == 401


def test_admin_list_returns_six_seeded_sources(client, db):
    admin = _admin(client, db)
    r = client.get("/api/v1/admin/data-sources", headers=admin)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 6
    by_kind = {row["kind"]: row for row in rows}
    assert set(by_kind) == {"faostat", "worldbank", "openweather",
                            "cgiar", "dam", "plantvillage"}
    for row in rows:
        assert {"id", "name", "kind", "endpoint", "countries",
                "last_sync_at", "status", "notes"} <= set(row)
    dam = by_kind["dam"]
    assert dam["endpoint"] == ""  # no public API: never invent an endpoint
    assert dam["status"] == "not_configured"
    assert dam["countries"] == ["BD"]
    faostat = by_kind["faostat"]
    assert faostat["endpoint"] == "https://www.fao.org/faostat/"
    assert faostat["countries"] == ["BD", "KE", "NG", "GH", "TZ", "UG"]
    # OpenWeatherMap is deprecated: weather uses keyless Open-Meteo and
    # OPENWEATHER_API_KEY is ignored — the catalogue must not ask for a key.
    ow = by_kind["openweather"]
    assert ow["status"] == "deprecated"
    assert "Open-Meteo" in ow["notes"] and "ignored" in ow["notes"]
    # Second read does not duplicate the seed rows.
    assert len(client.get("/api/v1/admin/data-sources", headers=admin).json()) == 6


def test_sync_requires_admin_and_existing_source(client, db):
    farmer = register(client, "f@x.t", "farmer")
    admin = _admin(client, db)
    rows = client.get("/api/v1/admin/data-sources", headers=admin).json()
    sid = rows[0]["id"]
    assert client.post(f"/api/v1/admin/data-sources/{sid}/sync",
                       headers=farmer).status_code == 403
    assert client.post(f"/api/v1/admin/data-sources/{sid}/sync").status_code == 401
    assert client.post("/api/v1/admin/data-sources/99999/sync",
                       headers=admin).status_code == 404


def test_sync_worldbank_returns_status_object(client, db):
    admin = _admin(client, db)
    rows = client.get("/api/v1/admin/data-sources", headers=admin).json()
    wb = next(r for r in rows if r["kind"] == "worldbank")
    r = client.post(f"/api/v1/admin/data-sources/{wb['id']}/sync", headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == wb["id"] and body["kind"] == "worldbank"
    assert body["status"] in ("ok", "error")  # shape, not success: network may be absent
    assert "message" in body
    # The stored status reflects the attempt.
    after = {row["kind"]: row for row in
             client.get("/api/v1/admin/data-sources", headers=admin).json()}
    assert after["worldbank"]["status"] == body["status"]


def test_sync_manual_source_reports_manual_and_keeps_last_sync(client, db):
    admin = _admin(client, db)
    rows = client.get("/api/v1/admin/data-sources", headers=admin).json()
    fao = next(r for r in rows if r["kind"] == "faostat")
    r = client.post(f"/api/v1/admin/data-sources/{fao['id']}/sync", headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "manual"
    assert "manual download" in body["message"]
    assert body["last_sync_at"] is None  # unchanged: no automatic sync happened
    after = {row["kind"]: row for row in
             client.get("/api/v1/admin/data-sources", headers=admin).json()}
    assert after["faostat"]["last_sync_at"] is None
