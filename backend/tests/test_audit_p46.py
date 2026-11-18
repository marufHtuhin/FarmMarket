"""Audit Phase 4-6 gap tests: auth/RBAC edge cases, ownership (IDOR),
order state-machine rules, and the X-Forwarded-For rate-limit fix.

These cover the cases the live audit (scripts/audit_p46_live.py) verified
against a running server but the existing pytest suite did not pin down.
Each test runs against the throwaway SQLite DB from conftest.
"""
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from conftest import register
from app import models
from app.main import _client_ip
from app.security import SECRET_KEY, create_access_token, hash_password


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password="<redacted>"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _add_product(client, headers, quantity=100, price=30):
    r = client.post("/api/v1/products", headers=headers,
                    json={"name": "Tomato", "quantity": quantity, "unit": "kg",
                          "price_per_unit": price, "district": "Gazipur"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _pending_order(client, buyer_headers, pid, quantity=10):
    r = client.post("/api/v1/orders", headers=buyer_headers,
                    json={"product_id": pid, "quantity": quantity})
    assert r.status_code == 200, r.text
    return r.json()["order_id"]


# ---------------- registration / login validation ----------------
def test_register_duplicate_email_409(client):
    register(client, "dup@x.t", "farmer")
    r = client.post("/api/v1/auth/register", json={
        "name": "Dup Again", "email": "dup@x.t",
        "password": "Passw0rd!", "role": "buyer"})
    assert r.status_code == 409, r.text


def test_register_validation_422(client):
    base = {"name": "Valid Name", "email": "v@x.t",
            "password": "Passw0rd!", "role": "farmer"}
    bad_email = {**base, "email": "not-an-email"}
    assert client.post("/api/v1/auth/register", json=bad_email).status_code == 422
    no_password = {k: v for k, v in base.items() if k != "password"}
    assert client.post("/api/v1/auth/register", json=no_password).status_code == 422
    no_role = {k: v for k, v in base.items() if k != "role"}
    assert client.post("/api/v1/auth/register", json=no_role).status_code == 422
    short_name = {**base, "name": "A"}
    assert client.post("/api/v1/auth/register", json=short_name).status_code == 422


def test_login_wrong_password_401_no_enumeration(client):
    register(client, "u@x.t", "farmer")
    wrong = client.post("/api/v1/auth/login",
                        json={"email": "u@x.t", "password": "WrongPass1!"})
    unknown = client.post("/api/v1/auth/login",
                          json={"email": "ghost@x.t", "password": "WrongPass1!"})
    assert wrong.status_code == unknown.status_code == 401
    # Same detail for both: an attacker cannot tell which emails exist.
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_password_hash_is_bcrypt_not_plaintext(client, db):
    register(client, "h@x.t", "farmer")
    row = db.query(models.User).filter_by(email="h@x.t").first()
    assert row.password_hash.startswith("$2b$")
    assert "<redacted>" not in row.password_hash


# ---------------- token validity ----------------
def test_me_expired_token_401(client, db):
    farmer = register(client, "e@x.t", "farmer")
    uid = db.query(models.User).filter_by(email="e@x.t").first().id
    expired = jwt.encode({"sub": str(uid),
                          "exp": datetime.now(timezone.utc) - timedelta(minutes=5)},
                         SECRET_KEY, algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers=_headers(expired)).status_code == 401
    # The live token from registration still works.
    assert client.get("/api/v1/auth/me", headers=farmer).status_code == 200


def test_me_garbage_and_unknown_user_token_401(client):
    assert client.get("/api/v1/auth/me",
                      headers=_headers("garbage.token.here")).status_code == 401
    ghost = create_access_token(999999)
    assert client.get("/api/v1/auth/me", headers=_headers(ghost)).status_code == 401


def test_reset_token_single_use(client):
    register(client, "r@x.t", "buyer")
    r = client.post("/api/v1/auth/forgot-password", json={"email": "r@x.t"})
    token = r.json()["reset_token"]
    ok = client.post("/api/v1/auth/reset-password",
                     json={"token": token, "new_password": "NewPass123!"})
    assert ok.status_code == 200, ok.text
    reuse = client.post("/api/v1/auth/reset-password",
                        json={"token": token, "new_password": "NewPass123!"})
    assert reuse.status_code == 400


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/orders/my"),
    ("GET", "/api/v1/dashboard"),
    ("GET", "/api/v1/demands"),
    ("GET", "/api/v1/matches"),
    ("GET", "/api/v1/notifications"),
    ("GET", "/api/v1/deliveries"),
    ("GET", "/api/v1/admin/stats"),
    ("GET", "/api/v1/farms"),
    ("GET", "/api/v1/offers/my"),
    ("GET", "/api/v1/conversations"),
    ("POST", "/api/v1/products"),
    ("POST", "/api/v1/orders"),
])
def test_unauthenticated_protected_routes_401(client, method, path):
    assert client.request(method, path).status_code == 401


# ---------------- X-Forwarded-For: last hop is the trusted one ----------------
class _FakeReq:
    def __init__(self, xff=None, host="203.0.113.9"):
        self.headers = {"x-forwarded-for": xff} if xff else {}
        self.client = type("C", (), {"host": host})()


def test_client_ip_uses_last_forwarded_hop(monkeypatch):
    # Merged behaviour (P10): XFF is honoured only with TRUST_PROXY=true.
    monkeypatch.setenv("TRUST_PROXY", "true")
    # Caddy appends the real peer IP; the first hop is client-spoofable.
    assert _client_ip(_FakeReq("1.2.3.4, 198.51.100.7")) == "198.51.100.7"
    assert _client_ip(_FakeReq("198.51.100.7")) == "198.51.100.7"
    assert _client_ip(_FakeReq()) == "203.0.113.9"


def test_login_rate_limit_keys_on_last_hop(client, monkeypatch):
    """Rotating the FIRST X-Forwarded-For hop must not dodge the limiter:
    two logins from the same real (last-hop) IP count against one bucket."""
    # Merged behaviour (P10): XFF is honoured only with TRUST_PROXY=true.
    monkeypatch.setenv("TRUST_PROXY", "true")
    from app.services import rate_limit
    from app import main as main_mod
    monkeypatch.setattr(rate_limit.login_limiter, "limit", 1)
    register(client, "rl@x.t", "farmer")
    h1 = {"X-Forwarded-For": "10.0.0.1, 198.51.100.7"}
    h2 = {"X-Forwarded-For": "10.0.0.2, 198.51.100.7"}
    body = {"email": "rl@x.t", "password": "WrongPass1!"}
    assert client.post("/api/v1/auth/login", json=body, headers=h1).status_code == 401
    # Same last hop, different spoofed first hop -> still rate limited.
    assert client.post("/api/v1/auth/login", json=body, headers=h2).status_code == 429
    monkeypatch.setattr(rate_limit.login_limiter, "limit", 10)
    assert main_mod.login_limiter.limit == 10


# ---------------- ownership (IDOR) ----------------
def test_other_farmer_cannot_edit_or_delete_listing(client):
    f1 = register(client, "f1@x.t", "farmer")
    f2 = register(client, "f2@x.t", "farmer")
    pid = _add_product(client, f1)
    body = {"name": "Tomato", "quantity": 5, "price_per_unit": 1, "district": "Gazipur"}
    assert client.put(f"/api/v1/products/{pid}", headers=f2, json=body).status_code == 403
    assert client.delete(f"/api/v1/products/{pid}", headers=f2).status_code == 403
    # Owner still can.
    assert client.put(f"/api/v1/products/{pid}", headers=f1, json=body).status_code == 200


def test_buyer_cannot_delete_listing(client):
    f = register(client, "f@x.t", "farmer")
    b = register(client, "b@x.t", "buyer")
    pid = _add_product(client, f)
    assert client.delete(f"/api/v1/products/{pid}", headers=b).status_code == 403


def test_other_farmer_cannot_accept_offer(client):
    f1 = register(client, "f1@x.t", "farmer")
    f2 = register(client, "f2@x.t", "farmer")
    b = register(client, "b@x.t", "buyer")
    pid = _add_product(client, f1)
    r = client.post("/api/v1/offers", headers=b,
                    json={"product_id": pid, "quantity": 10, "offered_price": 35})
    oid = r.json()["id"]
    assert client.patch(f"/api/v1/offers/{oid}", headers=f2,
                        json={"status": "accepted"}).status_code == 403
    assert client.patch(f"/api/v1/offers/{oid}", headers=f1,
                        json={"status": "accepted"}).status_code == 200


def test_notification_read_by_other_user_404(client):
    f = register(client, "f@x.t", "farmer")
    b = register(client, "b@x.t", "buyer")
    pid = _add_product(client, f)
    _pending_order(client, b, pid)  # notifies the farmer
    nid = client.get("/api/v1/notifications", headers=f).json()[0]["id"]
    assert client.patch(f"/api/v1/notifications/{nid}/read", headers=b).status_code == 404
    assert client.patch(f"/api/v1/notifications/{nid}/read", headers=f).status_code == 200


def test_other_transporter_cannot_delete_vehicle(client):
    t1 = register(client, "t1@x.t", "transporter")
    t2 = register(client, "t2@x.t", "transporter")
    r = client.post("/api/v1/vehicles", headers=t1,
                    json={"vehicle_type": "Truck", "capacity_kg": 1000})
    vid = r.json()["id"]
    assert client.delete(f"/api/v1/vehicles/{vid}", headers=t2).status_code in (403, 404)
    assert client.delete(f"/api/v1/vehicles/{vid}", headers=t1).status_code == 200


# ---------------- order state machine ----------------
def test_order_status_transition_rules(client):
    f = register(client, "f@x.t", "farmer")
    b = register(client, "b@x.t", "buyer")
    pid = _add_product(client, f)
    oid = _pending_order(client, b, pid)
    # Buyer cannot accept their own order.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=b,
                        json={"status": "accepted"}).status_code in (400, 403)
    # Farmer cannot complete a merely pending order.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=f,
                        json={"status": "completed"}).status_code == 400
    # Unknown status value is rejected.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=f,
                        json={"status": "shipped"}).status_code == 400
    # Accept, then buyer cannot cancel an accepted order.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=f,
                        json={"status": "accepted"}).status_code == 200
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=b,
                        json={"status": "cancelled"}).status_code == 400
    # Farmer can complete an accepted order.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=f,
                        json={"status": "completed"}).status_code == 200


def test_direct_order_insufficient_stock_and_sold_out(client):
    f = register(client, "f@x.t", "farmer")
    b = register(client, "b@x.t", "buyer")
    pid = _add_product(client, f, quantity=10)
    over = client.post("/api/v1/orders", headers=b,
                       json={"product_id": pid, "quantity": 11})
    assert over.status_code == 409, over.text
    assert client.post("/api/v1/orders", headers=b,
                       json={"product_id": pid, "quantity": 10}).status_code == 200
    assert client.get(f"/api/v1/products/{pid}").json()["status"] == "sold"
    gone = client.post("/api/v1/orders", headers=b,
                       json={"product_id": pid, "quantity": 1})
    assert gone.status_code in (404, 409)


# ---------------- delivery assignment guards (audit P5 fix) ----------------
def _accepted_order(client, farmer_headers, buyer_headers):
    pid = _add_product(client, farmer_headers)
    oid = _pending_order(client, buyer_headers, pid)
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=farmer_headers,
                        json={"status": "accepted"}).status_code == 200
    return oid


def test_assign_requires_accepted_order(client, db):
    f = register(client, "f@x.t", "farmer")
    b = register(client, "b@x.t", "buyer")
    t = register(client, "t@x.t", "transporter")
    tid = db.query(models.User).filter_by(email="t@x.t").first().id
    pid = _add_product(client, f)
    oid = _pending_order(client, b, pid)
    # Pending order: not assignable.
    assert client.patch(f"/api/v1/orders/{oid}/assign", headers=f,
                        json={"transporter_id": tid}).status_code == 400
    # Rejected order: not assignable.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=f,
                        json={"status": "rejected"}).status_code == 200
    assert client.patch(f"/api/v1/orders/{oid}/assign", headers=f,
                        json={"transporter_id": tid}).status_code == 400


def test_assign_cannot_reassign_after_pickup(client, db):
    f = register(client, "f@x.t", "farmer")
    b = register(client, "b@x.t", "buyer")
    t1 = register(client, "t1@x.t", "transporter")
    t2 = register(client, "t2@x.t", "transporter")
    tid1 = db.query(models.User).filter_by(email="t1@x.t").first().id
    tid2 = db.query(models.User).filter_by(email="t2@x.t").first().id
    oid = _accepted_order(client, f, b)
    assert client.patch(f"/api/v1/orders/{oid}/assign", headers=f,
                        json={"transporter_id": tid1}).status_code == 200
    # Re-assign while still waiting is allowed (e.g. transporter unavailable).
    assert client.patch(f"/api/v1/orders/{oid}/assign", headers=f,
                        json={"transporter_id": tid2}).status_code == 200
    assert client.patch(f"/api/v1/deliveries/{oid}", headers=t2,
                        json={"delivery_status": "picked_up"}).status_code == 200
    # Once picked up, re-assignment is refused and the state is untouched.
    assert client.patch(f"/api/v1/orders/{oid}/assign", headers=f,
                        json={"transporter_id": tid1}).status_code == 400
    mine = client.get("/api/v1/deliveries", headers=t2).json()
    assert len(mine) == 1 and mine[0]["delivery_status"] == "picked_up"


def test_farmer_cannot_complete_order_while_delivery_in_progress(client, db):
    """G4: a farmer must not mark an accepted order completed while its
    delivery is picked up or in transit — the transporter completes it by
    marking it delivered. Completing a not-yet-picked-up order stays allowed."""
    f = register(client, "f@x.t", "farmer")
    b = register(client, "b@x.t", "buyer")
    t = register(client, "t@x.t", "transporter")
    tid = db.query(models.User).filter_by(email="t@x.t").first().id
    # Assigned but not yet picked up: farmer may still complete.
    oid1 = _accepted_order(client, f, b)
    assert client.patch(f"/api/v1/orders/{oid1}/assign", headers=f,
                        json={"transporter_id": tid}).status_code == 200
    assert client.patch(f"/api/v1/orders/{oid1}/status", headers=f,
                        json={"status": "completed"}).status_code == 200
    # Picked up: completing is refused and the order stays accepted.
    oid2 = _accepted_order(client, f, b)
    assert client.patch(f"/api/v1/orders/{oid2}/assign", headers=f,
                        json={"transporter_id": tid}).status_code == 200
    assert client.patch(f"/api/v1/deliveries/{oid2}", headers=t,
                        json={"delivery_status": "picked_up"}).status_code == 200
    r = client.patch(f"/api/v1/orders/{oid2}/status", headers=f,
                     json={"status": "completed"})
    assert r.status_code == 400, r.text
    assert "in progress" in r.json()["detail"]
    # In transit: same refusal.
    assert client.patch(f"/api/v1/deliveries/{oid2}", headers=t,
                        json={"delivery_status": "in_transit"}).status_code == 200
    assert client.patch(f"/api/v1/orders/{oid2}/status", headers=f,
                        json={"status": "completed"}).status_code == 400
    # Delivered by the transporter completes the order instead.
    r = client.patch(f"/api/v1/deliveries/{oid2}", headers=t,
                     json={"delivery_status": "delivered"})
    assert r.status_code == 200 and r.json()["status"] == "completed"


def test_cancelled_order_releases_stock_once(client, db):
    f = register(client, "f@x.t", "farmer")
    b = register(client, "b@x.t", "buyer")
    pid = _add_product(client, f, quantity=10)
    oid = _pending_order(client, b, pid, quantity=4)
    assert client.get(f"/api/v1/products/{pid}").json()["quantity"] == 6
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=b,
                        json={"status": "cancelled"}).status_code == 200
    assert client.get(f"/api/v1/products/{pid}").json()["quantity"] == 10
    # A cancelled order cannot be cancelled again (no double release).
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=b,
                        json={"status": "cancelled"}).status_code == 400
    assert client.get(f"/api/v1/products/{pid}").json()["quantity"] == 10
