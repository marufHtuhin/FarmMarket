"""Phase 10 + 12 audit regression tests (security + performance).

Every test here pins a finding from the P10/P12 audit: an X-Forwarded-For
rate-limit bypass, a transporter seeing every order, unrelated transporters
recording Digital Twin events, an unbounded upload read, unbounded text
fields, an un-rate-limited password-reset endpoint, LIKE wildcard search,
API docs in production, and N+1 list queries.
"""
import io
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import event

from app import models
from app.database import engine
from app.main import _client_ip, docs_enabled
from app.security import create_access_token, hash_password
from app.services.rate_limit import forgot_limiter, login_limiter
from tests.conftest import register


# ---------------------------------------------------------------- helpers
def _fake_request(xff=None, host="203.0.113.9"):
    headers = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def _admin_headers(db):
    admin = models.User(name="Admin", email="admin@audit.t",
                        password_hash=hash_password("Passw0rd!"), role="admin")
    db.add(admin)
    db.commit()
    return {"Authorization": "Bearer " + create_access_token(admin.id)}


def _product(client, farmer, name="Tomato"):
    r = client.post("/api/v1/products", headers=farmer,
                    json={"name": name, "quantity": 100, "unit": "kg",
                          "price_per_unit": 30, "district": "Gazipur"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _jpeg_bytes(pad_to=None):
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (200, 40, 35)).save(buf, format="JPEG")
    data = buf.getvalue()
    if pad_to and len(data) < pad_to:
        data += b"\x00" * (pad_to - len(data))
    return data


# ---------------------------------------------------------------- P10: X-Forwarded-For
def test_client_ip_ignores_xff_without_trust_proxy(monkeypatch):
    """Without TRUST_PROXY a forged X-Forwarded-For must not change the key
    the rate limiter uses — otherwise rotating the header defeats it."""
    monkeypatch.delenv("TRUST_PROXY", raising=False)
    assert _client_ip(_fake_request("10.0.0.1")) == "203.0.113.9"
    assert _client_ip(_fake_request("10.0.0.1, 10.0.0.2")) == "203.0.113.9"


def test_client_ip_uses_last_hop_with_trust_proxy(monkeypatch):
    """With TRUST_PROXY the trusted proxy appends the real peer last, so
    the last entry is the only trustworthy one; a spoofed first entry is
    ignored."""
    monkeypatch.setenv("TRUST_PROXY", "true")
    assert _client_ip(_fake_request("10.9.9.9, 198.51.100.7")) == "198.51.100.7"
    assert _client_ip(_fake_request("198.51.100.7")) == "198.51.100.7"
    assert _client_ip(_fake_request(None)) == "203.0.113.9"


def test_login_rate_limit_not_bypassed_by_rotating_xff(client, monkeypatch):
    """Rotating X-Forwarded-For must not reset the login bucket: without
    TRUST_PROXY every attempt keys on the same TCP peer."""
    monkeypatch.delenv("TRUST_PROXY", raising=False)
    monkeypatch.setattr(login_limiter, "limit", 2)
    for i in range(2):
        r = client.post("/api/v1/auth/login",
                        json={"email": "nobody@audit.t", "password": "wrongpass"},
                        headers={"X-Forwarded-For": f"10.0.0.{i}"})
        assert r.status_code == 401, r.text
    r = client.post("/api/v1/auth/login",
                    json={"email": "nobody@audit.t", "password": "wrongpass"},
                    headers={"X-Forwarded-For": "10.0.0.99"})
    assert r.status_code == 429, r.text


# ---------------------------------------------------------------- P10: orders/my scoping
def test_orders_my_transporter_sees_only_assigned(client, db):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    t1 = register(client, "t1@x.t", "transporter")
    t2 = register(client, "t2@x.t", "transporter")
    pid = _product(client, farmer)
    oid = client.post("/api/v1/orders", headers=buyer,
                      json={"product_id": pid, "quantity": 1}).json()["order_id"]
    # Delivery assignment requires an accepted order (audit fix B2).
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=farmer,
                        json={"status": "accepted"}).status_code == 200
    # Unassigned transporters see nothing (previously: every order).
    assert client.get("/api/v1/orders/my", headers=t1).json() == []
    assert client.get("/api/v1/orders/my", headers=t2).json() == []
    # Assign to t1: only t1 sees it; admin still sees all.
    tid = db.query(models.User).filter_by(email="t1@x.t").first().id
    assert client.patch(f"/api/v1/orders/{oid}/assign", headers=farmer,
                        json={"transporter_id": tid}).status_code == 200
    assert [o["id"] for o in client.get("/api/v1/orders/my", headers=t1).json()] == [oid]
    assert client.get("/api/v1/orders/my", headers=t2).json() == []
    admin = _admin_headers(db)
    assert [o["id"] for o in client.get("/api/v1/orders/my", headers=admin).json()] == [oid]


# ---------------------------------------------------------------- P10: twin transporter events
def test_twin_events_restricted_for_transporters(client, db):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    t1 = register(client, "t1@x.t", "transporter")
    t2 = register(client, "t2@x.t", "transporter")
    pid = _product(client, farmer)
    oid = client.post("/api/v1/orders", headers=buyer,
                      json={"product_id": pid, "quantity": 1}).json()["order_id"]
    # Delivery assignment requires an accepted order (audit fix B2).
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=farmer,
                        json={"status": "accepted"}).status_code == 200
    code = client.post("/api/v1/twin/batches", headers=farmer, json={
        "crop": "tomato", "origin_district": "Gazipur", "quantity_kg": 10,
        "order_id": oid}).json()["batch_code"]
    url = f"/api/v1/twin/batches/{code}/events"
    # No transporter assigned yet: neither may record events.
    assert client.post(url, headers=t1, json={"event_type": "delivered"}).status_code == 403
    # Assign t1: t1 may, t2 still may not.
    tid = db.query(models.User).filter_by(email="t1@x.t").first().id
    assert client.patch(f"/api/v1/orders/{oid}/assign", headers=farmer,
                        json={"transporter_id": tid}).status_code == 200
    assert client.post(url, headers=t1,
                       json={"event_type": "in_transit_checkpoint"}).status_code == 200
    assert client.post(url, headers=t2, json={"event_type": "delivered"}).status_code == 403
    # Admin (trusted role) may still record events.
    assert client.post(url, headers=_admin_headers(db),
                       json={"event_type": "inspected"}).status_code == 200
    # A batch with no linked order admits no transporter at all.
    code2 = client.post("/api/v1/twin/batches", headers=farmer, json={
        "crop": "tomato", "origin_district": "Gazipur", "quantity_kg": 5}).json()["batch_code"]
    assert client.post(f"/api/v1/twin/batches/{code2}/events", headers=t1,
                       json={"event_type": "delivered"}).status_code == 403


# ---------------------------------------------------------------- P10: uploads + schemas
def test_upload_rejects_oversized_image(client):
    farmer = register(client, "f@x.t", "farmer")
    pid = _product(client, farmer)
    big = _jpeg_bytes(pad_to=5 * 1024 * 1024 + 1)
    r = client.post(f"/api/v1/products/{pid}/images", headers=farmer,
                    files=[("files", ("big.jpg", big, "image/jpeg"))])
    assert r.status_code == 400 and "5MB" in r.text
    small = _jpeg_bytes()
    r = client.post(f"/api/v1/products/{pid}/images", headers=farmer,
                    files=[("files", ("ok.jpg", small, "image/jpeg"))])
    assert r.status_code == 200, r.text


def test_unbounded_text_fields_rejected(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    base = {"name": "Tomato", "quantity": 1, "unit": "kg",
            "price_per_unit": 1, "district": "Dhaka"}
    assert client.post("/api/v1/products", headers=farmer,
                       json={**base, "name": "x" * 100_000}).status_code == 422
    assert client.post("/api/v1/products", headers=farmer,
                       json={**base, "description": "y" * 500_000}).status_code == 422
    pid = _product(client, farmer)
    assert client.post("/api/v1/offers", headers=buyer,
                       json={"product_id": pid, "quantity": 1, "offered_price": 1,
                             "message": "z" * 2001}).status_code == 422
    assert client.post("/api/v1/demands", headers=buyer,
                       json={"product_name": "n" * 151, "required_quantity": 1,
                             "unit": "kg", "target_price": 1,
                             "district": "Dhaka"}).status_code == 422


# ---------------------------------------------------------------- P10: forgot-password rate limit
def test_forgot_password_rate_limited(client, monkeypatch):
    monkeypatch.setattr(forgot_limiter, "limit", 2)
    for _ in range(2):
        assert client.post("/api/v1/auth/forgot-password",
                           json={"email": "nobody@audit.t"}).status_code == 200
    assert client.post("/api/v1/auth/forgot-password",
                       json={"email": "nobody@audit.t"}).status_code == 429


# ---------------------------------------------------------------- P10: LIKE wildcards
def test_search_wildcards_are_literal(client):
    farmer = register(client, "f@x.t", "farmer")
    _product(client, farmer, name="Tomato")
    assert len(client.get("/api/v1/products", params={"search": "%"}).json()) == 0
    assert len(client.get("/api/v1/products", params={"search": "_"}).json()) == 0
    assert len(client.get("/api/v1/products", params={"search": "Tom"}).json()) == 1
    assert len(client.get("/api/v1/products", params={"search": "tom"}).json()) == 1


# ---------------------------------------------------------------- P10: docs gating
def test_docs_disabled_in_production_only():
    assert docs_enabled("production") is False
    assert docs_enabled("development") is True
    assert docs_enabled("staging") is True


# ---------------------------------------------------------------- P12: N+1 query counts
def _count_statements(fn):
    seen = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return len(seen)


def test_products_list_has_no_n_plus_1(client, db):
    """20 products from 5 distinct farmers: 2 statements (products +
    one eager farmer load), not 1 + 5 lazy loads."""
    farmers = [register(client, f"f{i}@x.t", "farmer") for i in range(5)]
    for i in range(20):
        _product(client, farmers[i % 5], name=f"Crop{i}")
    n = _count_statements(lambda: client.get("/api/v1/products"))
    assert n <= 3, f"products list issued {n} statements"


def test_transporters_list_has_no_n_plus_1(client, db):
    for i in range(3):
        h = register(client, f"t{i}@x.t", "transporter")
        client.post("/api/v1/vehicles", headers=h,
                    json={"vehicle_type": "Truck", "capacity_kg": 1000})
    n = _count_statements(lambda: client.get("/api/v1/transporters"))
    assert n <= 3, f"transporters list issued {n} statements"


def test_conversation_list_has_no_n_plus_1(client, db):
    """5 conversations: a fixed handful of statements, not 2 per
    conversation for unread counts + last messages."""
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    fid = db.query(models.User).filter_by(email="f@x.t").first().id
    pids = [_product(client, farmer, name=f"Crop{i}") for i in range(5)]
    for pid in pids:
        r = client.post("/api/v1/conversations", headers=buyer,
                        json={"other_user_id": fid, "listing_id": pid})
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        assert client.post(f"/api/v1/conversations/{cid}/messages", headers=buyer,
                           json={"body": "hello"}).status_code == 200
    r = client.get("/api/v1/conversations", headers=buyer)
    assert r.status_code == 200 and len(r.json()) == 5
    assert all(c["unread_count"] == 0 for c in r.json())
    assert all(c["last_message"] and c["last_message"]["body"] == "hello"
               for c in r.json())
    n = _count_statements(lambda: client.get("/api/v1/conversations", headers=buyer))
    assert n <= 9, f"conversation list issued {n} statements"
