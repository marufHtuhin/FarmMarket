"""Foundation (Phases 1-2) tests: refresh-token auth, password reset, farms,
offers, vehicles, deliveries, admin, catalogs, product detail + images."""
import numpy as np
import pytest

from conftest import register, fruit_image
from app import models
from app.security import create_access_token, hash_password


def login(client, email, password="Passw0rd!"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def make_user(db, email, role, name="Test User"):
    """Create a user directly in the DB (needed for admin: register rejects it)."""
    u = models.User(email=email, name=name, role=role, district="Dhaka",
                    password_hash=hash_password("Passw0rd!"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def auth_headers(user):
    return {"Authorization": "Bearer " + create_access_token(user.id)}


def add_product(client, headers, name="Tomato", quantity=100, price=30):
    r = client.post("/api/v1/products", headers=headers,
                    json={"name": name, "quantity": quantity, "unit": "kg",
                          "price_per_unit": price, "district": "Gazipur"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def make_offer(client, buyer_headers, pid, quantity=40, price=35):
    r = client.post("/api/v1/offers", headers=buyer_headers,
                    json={"product_id": pid, "quantity": quantity,
                          "offered_price": price, "message": "Please accept"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------------- auth: roles + refresh tokens ----------------
def test_register_transporter_ok(client):
    r = client.post("/api/v1/auth/register", json={"name": "Trucker", "email": "t@x.t",
                    "password": "Passw0rd!", "role": "transporter", "district": "Dhaka"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "transporter"


def test_register_admin_rejected(client):
    r = client.post("/api/v1/auth/register", json={"name": "Root", "email": "a@x.t",
                    "password": "Passw0rd!", "role": "admin", "district": "Dhaka"})
    assert r.status_code == 400


def test_login_returns_refresh_token(client):
    register(client, "f@x.t", "farmer")
    body = login(client, "f@x.t")
    assert body["access_token"] and body["refresh_token"] and body["token_type"] == "bearer"
    assert body["user"]["role"] == "farmer"


def test_refresh_rotates_and_old_token_fails(client):
    register(client, "f@x.t", "farmer")
    r1 = login(client, "f@x.t")["refresh_token"]
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": r1})
    assert r.status_code == 200 and r.json()["refresh_token"] != r1
    assert r.json()["access_token"]
    # The presented token was revoked by rotation.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": r1}).status_code == 401


def test_refresh_reuse_revokes_all_user_tokens(client):
    register(client, "f@x.t", "farmer")
    r1 = login(client, "f@x.t")["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": r1}).json()["refresh_token"]
    # Reusing the revoked r1 is theft: r2 must be revoked too.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": r1}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": r2}).status_code == 401


def test_refresh_unknown_token_401(client):
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": "nope"}).status_code == 401


def test_logout_revokes(client):
    register(client, "f@x.t", "farmer")
    r1 = login(client, "f@x.t")["refresh_token"]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": r1}).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": r1}).status_code == 401
    # Unknown token still returns 200.
    assert client.post("/api/v1/auth/logout", json={"refresh_token": "unknown"}).status_code == 200


# ---------------- auth: password reset ----------------
def test_forgot_and_reset_password(client):
    register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/auth/forgot-password", json={"email": "f@x.t"})
    assert r.status_code == 200 and "reset_token" in r.json()  # dev + no mailer configured includes it
    token = r.json()["reset_token"]
    assert client.post("/api/v1/auth/reset-password",
                       json={"token": token, "new_password": "NewPass1!"}).status_code == 200
    assert login(client, "f@x.t", "NewPass1!")["user"]["email"] == "f@x.t"
    assert client.post("/api/v1/auth/login",
                       json={"email": "f@x.t", "password": "Passw0rd!"}).status_code == 401
    # Token is single-use. (Password is 8+ chars: the min length is 8, so a
    # shorter password here would fail validation with 422 instead of
    # exercising the reused-token 400.)
    assert client.post("/api/v1/auth/reset-password",
                       json={"token": token, "new_password": "OtherPass1!"}).status_code == 400


def test_forgot_password_unknown_email_no_enumeration(client):
    r = client.post("/api/v1/auth/forgot-password", json={"email": "ghost@x.t"})
    assert r.status_code == 200 and "reset_token" not in r.json()


def test_reset_password_bad_token_400(client):
    assert client.post("/api/v1/auth/reset-password",
                       json={"token": "bad-token", "new_password": "NewPass1!"}).status_code == 400


# ---------------- farms ----------------
def test_farm_crud(client):
    farmer = register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/farms", headers=farmer,
                    json={"name": "My Farm", "district": "Gazipur", "upazila": "Sadar",
                          "area_acres": 2.5, "country_code": "BD"})
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    assert r.json()["area_acres"] == 2.5
    assert len(client.get("/api/v1/farms", headers=farmer).json()) == 1
    assert client.get(f"/api/v1/farms/{fid}", headers=farmer).json()["name"] == "My Farm"
    r = client.put(f"/api/v1/farms/{fid}", headers=farmer, json={"name": "Renamed Farm"})
    assert r.status_code == 200 and r.json()["name"] == "Renamed Farm"
    assert client.delete(f"/api/v1/farms/{fid}", headers=farmer).status_code == 200
    assert client.get(f"/api/v1/farms/{fid}", headers=farmer).status_code == 404


def test_farm_403_for_other_farmer_and_buyer(client):
    farmer = register(client, "f@x.t", "farmer")
    other = register(client, "f2@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    fid = client.post("/api/v1/farms", headers=farmer, json={"name": "Mine"}).json()["id"]
    assert client.get(f"/api/v1/farms/{fid}", headers=other).status_code == 403
    assert client.put(f"/api/v1/farms/{fid}", headers=other, json={"name": "Nope"}).status_code == 403
    assert client.delete(f"/api/v1/farms/{fid}", headers=other).status_code == 403
    assert client.post("/api/v1/farms", headers=buyer, json={"name": "No"}).status_code == 403
    assert client.get("/api/v1/farms", headers=buyer).status_code == 403


# ---------------- offers ----------------
def test_offer_accept_creates_order_and_reserves_stock(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer, quantity=100, price=30)
    oid = make_offer(client, buyer, pid, quantity=40, price=35)
    r = client.patch(f"/api/v1/offers/{oid}", headers=farmer, json={"status": "accepted"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted" and r.json()["order_id"]
    # Stock decremented: 100 - 40 = 60.
    assert client.get(f"/api/v1/products/{pid}").json()["quantity"] == 60
    orders = client.get("/api/v1/orders/my", headers=buyer).json()
    assert len(orders) == 1 and orders[0]["status"] == "accepted"
    assert orders[0]["unit_price"] == 35 and orders[0]["total_amount"] == 1400
    # Buyer was notified.
    assert any("accepted" in n["title"].lower()
               for n in client.get("/api/v1/notifications", headers=buyer).json())
    # Offer is no longer pending: a second accept fails.
    assert client.patch(f"/api/v1/offers/{oid}", headers=farmer,
                        json={"status": "accepted"}).status_code == 400


def test_offer_reject_and_cancel(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer)
    oid = make_offer(client, buyer, pid)
    r = client.patch(f"/api/v1/offers/{oid}", headers=farmer, json={"status": "rejected"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    # Rejected offer did not touch stock or create an order.
    assert client.get(f"/api/v1/products/{pid}").json()["quantity"] == 100
    assert client.get("/api/v1/orders/my", headers=buyer).json() == []
    oid2 = make_offer(client, buyer, pid)
    r = client.patch(f"/api/v1/offers/{oid2}", headers=buyer, json={"status": "cancelled"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    # Buyer cannot accept/reject; farmer cannot cancel.
    oid3 = make_offer(client, buyer, pid)
    assert client.patch(f"/api/v1/offers/{oid3}", headers=buyer,
                        json={"status": "accepted"}).status_code == 403
    assert client.patch(f"/api/v1/offers/{oid3}", headers=farmer,
                        json={"status": "cancelled"}).status_code == 403


def test_offer_my_lists_for_farmer_and_buyer(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer)
    make_offer(client, buyer, pid, quantity=10, price=33)
    mine_f = client.get("/api/v1/offers/my", headers=farmer).json()
    mine_b = client.get("/api/v1/offers/my", headers=buyer).json()
    assert len(mine_f) == len(mine_b) == 1
    assert mine_f[0]["product_name"] == "Tomato" and mine_f[0]["buyer_name"]
    assert mine_b[0]["farmer_name"] and mine_b[0]["offered_price"] == 33


def test_offer_accept_insufficient_stock_409(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer, quantity=100)
    oid = make_offer(client, buyer, pid, quantity=500, price=35)
    assert client.patch(f"/api/v1/offers/{oid}", headers=farmer,
                        json={"status": "accepted"}).status_code == 409
    # Offer is still pending and stock untouched.
    assert client.get("/api/v1/offers/my", headers=farmer).json()[0]["status"] == "pending"
    assert client.get(f"/api/v1/products/{pid}").json()["quantity"] == 100


def test_offer_validation(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer)
    # Only buyers can offer.
    assert client.post("/api/v1/offers", headers=farmer,
                       json={"product_id": pid, "quantity": 1, "offered_price": 1}).status_code == 403
    # Quantity must be > 0.
    assert client.post("/api/v1/offers", headers=buyer,
                       json={"product_id": pid, "quantity": 0, "offered_price": 1}).status_code == 422
    # Removed product is unavailable.
    assert client.delete(f"/api/v1/products/{pid}", headers=farmer).status_code == 200
    assert client.post("/api/v1/offers", headers=buyer,
                       json={"product_id": pid, "quantity": 1, "offered_price": 1}).status_code == 404


# ---------------- vehicles ----------------
def test_vehicle_crud(client):
    t = register(client, "t@x.t", "transporter")
    r = client.post("/api/v1/vehicles", headers=t,
                    json={"vehicle_type": "Truck", "capacity_kg": 2000,
                          "refrigerated": True, "plate_number": "DHK-1"})
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    assert r.json()["capacity_kg"] == 2000 and r.json()["refrigerated"] is True
    assert len(client.get("/api/v1/vehicles", headers=t).json()) == 1
    assert client.delete(f"/api/v1/vehicles/{vid}", headers=t).status_code == 200
    assert client.get("/api/v1/vehicles", headers=t).json() == []


def test_vehicle_403_for_non_transporter(client):
    buyer = register(client, "b@x.t", "buyer")
    assert client.post("/api/v1/vehicles", headers=buyer,
                       json={"vehicle_type": "Truck", "capacity_kg": 100}).status_code == 403
    assert client.get("/api/v1/vehicles", headers=buyer).status_code == 403


# ---------------- deliveries ----------------
def _accepted_order(client, farmer, buyer):
    pid = add_product(client, farmer, quantity=100, price=30)
    oid = client.post("/api/v1/orders", headers=buyer,
                      json={"product_id": pid, "quantity": 10}).json()["order_id"]
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=farmer,
                        json={"status": "accepted"}).status_code == 200
    return oid


def test_deliveries_full_flow(client, db):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    t = register(client, "t@x.t", "transporter")
    other_t = register(client, "t2@x.t", "transporter")
    transporter = db.query(models.User).filter_by(email="t@x.t").first()
    oid = _accepted_order(client, farmer, buyer)
    # Only the farmer (or admin) may assign.
    assert client.patch(f"/api/v1/orders/{oid}/assign", headers=buyer,
                        json={"transporter_id": transporter.id}).status_code == 403
    r = client.patch(f"/api/v1/orders/{oid}/assign", headers=farmer,
                     json={"transporter_id": transporter.id})
    assert r.status_code == 200 and r.json()["delivery_status"] == "assigned"
    mine = client.get("/api/v1/deliveries", headers=t).json()
    assert len(mine) == 1 and mine[0]["product_name"] == "Tomato"
    assert mine[0]["buyer_name"] and mine[0]["district"] == "Gazipur"
    assert client.get("/api/v1/deliveries", headers=other_t).json() == []
    # delivered is only reachable from picked_up / in_transit.
    assert client.patch(f"/api/v1/deliveries/{oid}", headers=t,
                        json={"delivery_status": "delivered"}).status_code == 400
    # Only the assigned transporter may update.
    assert client.patch(f"/api/v1/deliveries/{oid}", headers=other_t,
                        json={"delivery_status": "picked_up"}).status_code == 403
    assert client.patch(f"/api/v1/deliveries/{oid}", headers=t,
                        json={"delivery_status": "picked_up"}).status_code == 200
    assert client.patch(f"/api/v1/deliveries/{oid}", headers=t,
                        json={"delivery_status": "in_transit"}).status_code == 200
    r = client.patch(f"/api/v1/deliveries/{oid}", headers=t,
                     json={"delivery_status": "delivered", "proof_note": "Signed by buyer"})
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert client.get("/api/v1/orders/my", headers=farmer).json()[0]["status"] == "completed"


# ---------------- admin ----------------
def test_admin_endpoints_403_for_non_admin(client):
    farmer = register(client, "f@x.t", "farmer")
    assert client.get("/api/v1/admin/stats", headers=farmer).status_code == 403
    assert client.get("/api/v1/admin/users", headers=farmer).status_code == 403
    assert client.get("/api/v1/admin/audit-logs", headers=farmer).status_code == 403
    assert client.patch("/api/v1/admin/users/1/verify", headers=farmer,
                        json={"is_verified": True}).status_code == 403
    assert client.get("/api/v1/admin/stats").status_code == 401


def test_admin_stats_users_verify_and_audit_logs(client, db):
    register(client, "f@x.t", "farmer")
    register(client, "b@x.t", "buyer")
    register(client, "t@x.t", "transporter")
    admin = auth_headers(make_user(db, "admin@x.t", "admin"))
    stats = client.get("/api/v1/admin/stats", headers=admin).json()
    assert stats["users_total"] == 4 and stats["farmers"] == 1
    assert stats["buyers"] == 1 and stats["transporters"] == 1
    assert stats["products"] == 0 and stats["orders"] == 0
    page = client.get("/api/v1/admin/users", headers=admin,
                      params={"role": "farmer"}).json()
    assert page["total"] == 1 and len(page["items"]) == 1
    assert page["items"][0]["is_verified"] is False
    page = client.get("/api/v1/admin/users", headers=admin,
                      params={"search": "b@x.t"}).json()
    assert page["total"] == 1 and page["items"][0]["email"] == "b@x.t"
    farmer = db.query(models.User).filter_by(email="f@x.t").first()
    r = client.patch(f"/api/v1/admin/users/{farmer.id}/verify", headers=admin,
                     json={"is_verified": True})
    assert r.status_code == 200 and r.json()["is_verified"] is True
    logs = client.get("/api/v1/admin/audit-logs", headers=admin).json()
    assert any(l["action"] == "user_verified" for l in logs)


# ---------------- catalogs ----------------
def test_countries_returns_six(client):
    rows = client.get("/api/v1/countries").json()
    assert [c["code"] for c in rows] == ["BD", "KE", "NG", "GH", "TZ", "UG"]
    by_code = {c["code"]: c for c in rows}
    assert by_code["BD"]["currency"] == "BDT"
    assert [h["name"] for h in by_code["BD"]["hubs"]] == [
        "Dhaka", "Chattogram", "Rajshahi", "Khulna", "Sylhet"]
    assert by_code["KE"]["hubs"][0]["name"] == "Nairobi"
    assert by_code["KE"]["currency"] == "KES"
    assert by_code["NG"]["currency"] == "NGN" and by_code["GH"]["currency"] == "GHS"
    assert by_code["TZ"]["currency"] == "TZS" and by_code["UG"]["currency"] == "UGX"
    dhaka = by_code["BD"]["hubs"][0]
    assert abs(dhaka["lat"] - 23.8103) < 1e-4 and abs(dhaka["lon"] - 90.4125) < 1e-4


def test_crops_catalog_fallback_and_db(client, db):
    # Unseeded DB: static catalog fallback (11 crops).
    rows = client.get("/api/v1/crops").json()
    assert len(rows) == 11
    tomato = next(c for c in rows if c["id"] == "tomato")
    assert tomato["local_names"]["bn"] == "টমেটো" and tomato["local_names"]["en"] == "Tomato"
    assert tomato["unit"] == "kg"
    assert {c["id"] for c in rows} == {"tomato", "potato", "onion", "rice", "banana",
                                       "mango", "brinjal", "chili", "cauliflower", "jute", "maize"}
    # Seeded DB: served from the crops tables.
    db.add(models.Crop(id="tomato", name="Tomato", default_unit="kg"))
    db.add(models.CropLocalName(crop_id="tomato", language="bn", name="টমেটো"))
    db.add(models.Crop(id="maize", name="Maize", default_unit="kg"))
    db.commit()
    rows = client.get("/api/v1/crops").json()
    assert len(rows) == 2
    assert rows[0]["id"] == "tomato" and rows[0]["local_names"]["bn"] == "টমেটো"


# ---------------- product detail + images ----------------
def test_product_detail_returns_farmer_images_and_farm(client, db):
    farmer = register(client, "f@x.t", "farmer")
    fid = client.post("/api/v1/farms", headers=farmer, json={"name": "My Farm"}).json()["id"]
    farmer_user = db.query(models.User).filter_by(email="f@x.t").first()
    p = models.Product(farmer_id=farmer_user.id, farm_id=fid, name="Tomato",
                       quantity=50, unit="kg", price_per_unit=30, district="Gazipur")
    db.add(p)
    db.commit()
    body = client.get(f"/api/v1/products/{p.id}").json()
    assert body["farmer"]["name"] == "User f" and body["farmer"]["is_verified"] is False
    assert body["farmer"]["district"] == "Gazipur"
    assert body["images"] == [] and body["farm"] == {"id": fid, "name": "My Farm"}
    assert body["currency"] == "BDT"
    assert client.get("/api/v1/products/999999").status_code == 404


def test_product_image_upload_and_validation(client):
    farmer = register(client, "f@x.t", "farmer")
    other = register(client, "f2@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer)
    img = fruit_image("ripe", np.random.default_rng(3))
    r = client.post(f"/api/v1/products/{pid}/images", headers=farmer,
                    files=[("files", ("a.png", img, "image/png"))])
    assert r.status_code == 200, r.text
    url = r.json()["images"][0]["url"]
    assert url.startswith(f"/uploads/products/{pid}/") and url.endswith(".png")
    assert client.get(url).status_code == 200  # served by the /uploads mount
    assert len(client.get(f"/api/v1/products/{pid}").json()["images"]) == 1
    # Only the owning farmer may upload.
    assert client.post(f"/api/v1/products/{pid}/images", headers=other,
                       files=[("files", ("a.png", img, "image/png"))]).status_code == 403
    assert client.post(f"/api/v1/products/{pid}/images", headers=buyer,
                       files=[("files", ("a.png", img, "image/png"))]).status_code == 403
    # Unreadable bytes and wrong content types are rejected.
    assert client.post(f"/api/v1/products/{pid}/images", headers=farmer,
                       files=[("files", ("x.png", b"junk", "image/png"))]).status_code == 400
    assert client.post(f"/api/v1/products/{pid}/images", headers=farmer,
                       files=[("files", ("x.txt", b"hello", "text/plain"))]).status_code == 400
    # At most 5 images per product (1 already stored).
    many = [("files", (f"{i}.png", img, "image/png")) for i in range(4)]
    assert client.post(f"/api/v1/products/{pid}/images", headers=farmer, files=many).status_code == 200
    assert client.post(f"/api/v1/products/{pid}/images", headers=farmer,
                       files=[("files", ("6.png", img, "image/png"))]).status_code == 400


# ---------------- dashboard ----------------
def test_dashboard_transporter_and_admin(client, db):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    t = register(client, "t@x.t", "transporter")
    transporter = db.query(models.User).filter_by(email="t@x.t").first()
    oid = _accepted_order(client, farmer, buyer)
    client.patch(f"/api/v1/orders/{oid}/assign", headers=farmer,
                 json={"transporter_id": transporter.id})
    dash = client.get("/api/v1/dashboard", headers=t).json()
    assert dash == {"role": "transporter", "assigned_deliveries": 1,
                    "in_transit": 0, "delivered": 0}
    admin = auth_headers(make_user(db, "admin@x.t", "admin"))
    dash = client.get("/api/v1/dashboard", headers=admin).json()
    assert dash["role"] == "admin" and dash["users_total"] == 4
    assert dash["products"] == 1 and dash["orders"] == 1
    assert dash["total_sales"] == 300
    # Farmer/buyer shapes unchanged.
    assert client.get("/api/v1/dashboard", headers=farmer).json()["role"] == "farmer"
    assert client.get("/api/v1/dashboard", headers=buyer).json()["role"] == "buyer"
