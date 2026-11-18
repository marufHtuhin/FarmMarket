"""Contract-fix tests (coordinator): register refresh token, ProductIn farm_id,
transporter directory, order detail, notification read endpoints, SPA static
file serving (manifest/sw.js) vs index.html fallback."""
from pathlib import Path

import pytest

from conftest import register
from app import models
from app.security import hash_password

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
dist_exists = (DIST / "index.html").exists()


def make_farm(client, headers, name="My Farm"):
    r = client.post("/api/v1/farms", headers=headers,
                    json={"name": name, "district": "Gazipur", "upazila": "Sreepur",
                          "area_acres": 2.5})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def add_product(client, headers, **over):
    body = {"name": "Tomato", "quantity": 100, "unit": "kg",
            "price_per_unit": 30, "district": "Gazipur"}
    body.update(over)
    return client.post("/api/v1/products", headers=headers, json=body)


def place_order(client, buyer_headers, pid, quantity=10):
    r = client.post("/api/v1/orders", headers=buyer_headers,
                    json={"product_id": pid, "quantity": quantity})
    assert r.status_code == 200, r.text
    return r.json()["order_id"]


def test_register_returns_refresh_token(client):
    r = client.post("/api/v1/auth/register", json={"name": "New", "email": "n@x.t",
                    "password": "Passw0rd!", "role": "farmer", "district": "Dhaka"})
    assert r.status_code == 200, r.text
    assert r.json()["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": r.json()["refresh_token"]})
    assert r2.status_code == 200 and r2.json()["access_token"]


def test_product_create_with_own_farm(client):
    fh = register(client, "f@x.t", "farmer")
    farm_id = make_farm(client, fh)
    r = add_product(client, fh, farm_id=farm_id)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    d = client.get(f"/api/v1/products/{pid}")
    assert d.status_code == 200 and d.json()["farm"]["id"] == farm_id


def test_product_create_with_other_farmers_farm_forbidden(client):
    fh1 = register(client, "f1@x.t", "farmer")
    fh2 = register(client, "f2@x.t", "farmer")
    farm_id = make_farm(client, fh1)
    r = add_product(client, fh2, farm_id=farm_id)
    assert r.status_code == 403


def test_product_create_with_missing_farm_404(client):
    fh = register(client, "f@x.t", "farmer")
    assert add_product(client, fh, farm_id=99999).status_code == 404


def test_product_edit_farm_validation(client):
    fh1 = register(client, "f1@x.t", "farmer")
    fh2 = register(client, "f2@x.t", "farmer")
    farm1 = make_farm(client, fh1, "Farm One")
    farm2 = make_farm(client, fh2, "Farm Two")
    pid = add_product(client, fh1).json()["id"]
    body = {"name": "Tomato", "quantity": 100, "unit": "kg", "price_per_unit": 30,
            "district": "Gazipur", "farm_id": farm2}
    assert client.put(f"/api/v1/products/{pid}", headers=fh1, json=body).status_code == 403
    body["farm_id"] = farm1
    assert client.put(f"/api/v1/products/{pid}", headers=fh1, json=body).status_code == 200


def test_transporters_directory_public_no_contact_details(client):
    register(client, "t@x.t", "transporter")
    register(client, "f@x.t", "farmer")
    r = client.get("/api/v1/transporters")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1 and items[0]["name"].startswith("User t")
    assert "email" not in items[0] and "phone" not in items[0]
    assert items[0]["vehicle_count"] == 0


def test_order_detail_owner_and_stranger(client):
    fh = register(client, "f@x.t", "farmer")
    bh = register(client, "b@x.t", "buyer")
    sh = register(client, "s@x.t", "buyer")
    pid = add_product(client, fh).json()["id"]
    oid = place_order(client, bh, pid)
    d = client.get(f"/api/v1/orders/{oid}", headers=bh)
    assert d.status_code == 200 and d.json()["product_name"] == "Tomato"
    assert d.json()["farmer"]["name"].startswith("User f")
    assert client.get(f"/api/v1/orders/{oid}", headers=sh).status_code == 403
    assert client.get("/api/v1/orders/99999", headers=bh).status_code == 404
    assert client.get(f"/api/v1/orders/{oid}").status_code == 401


def test_notifications_read_and_read_all(client, db):
    fh = register(client, "f@x.t", "farmer")
    bh = register(client, "b@x.t", "buyer")
    pid = add_product(client, fh).json()["id"]
    place_order(client, bh, pid)
    notes = client.get("/api/v1/notifications", headers=fh).json()
    assert len(notes) == 1 and notes[0]["is_read"] is False
    nid = notes[0]["id"]
    assert client.patch(f"/api/v1/notifications/{nid}/read", headers=bh).status_code == 404
    r = client.patch(f"/api/v1/notifications/{nid}/read", headers=fh)
    assert r.status_code == 200
    assert client.get("/api/v1/notifications", headers=fh).json()[0]["is_read"] is True
    # A second order + read-all.
    place_order(client, bh, pid)
    r = client.post("/api/v1/notifications/read-all", headers=fh)
    assert r.status_code == 200 and r.json()["updated"] == 1
    assert all(n["is_read"] for n in client.get("/api/v1/notifications", headers=fh).json())


@pytest.mark.skipif(not dist_exists, reason="frontend/dist not built")
def test_spa_serves_dist_files_and_falls_back(client):
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200 and "FarmMarket" in m.text
    assert "text/html" not in m.headers.get("content-type", "")
    page = client.get("/marketplace")
    assert page.status_code == 200 and "FarmMarket" in page.text
    assert "text/html" in page.headers.get("content-type", "")
    assert client.get("/api/no-such-route").status_code == 404
