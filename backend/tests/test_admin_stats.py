"""Admin /stats contract tests (19 Nov 2026 live QA fix).

The admin dashboard rendered every counter as 0 even though the platform
had data, because the endpoint returned users_total/farmers/buyers/...
while the frontend reads total_users/total_products/total_orders/
total_revenue/users_by_role. These tests pin the frontend contract and
the recent_activity feed with seeded data.
"""
from conftest import register
from app import models
from app.security import create_access_token, hash_password


def _make_admin(db):
    u = models.User(email="admin@x.t", name="Admin", role="admin",
                    district="Dhaka", password_hash=hash_password("Passw0rd!"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"Authorization": "Bearer " + create_access_token(u.id)}


def _add_product(client, headers, name="Tomato", quantity=100, price=30):
    r = client.post("/api/v1/products", headers=headers,
                    json={"name": name, "quantity": quantity, "unit": "kg",
                          "price_per_unit": price, "district": "Gazipur"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _place_order(client, buyer_headers, pid, quantity=10):
    r = client.post("/api/v1/orders", headers=buyer_headers,
                    json={"product_id": pid, "quantity": quantity})
    assert r.status_code == 200, r.text
    return r.json()["order_id"]


def test_stats_counts_match_frontend_contract(client, db):
    """Seeded users/products/orders produce the counts the dashboard shows."""
    farmer = register(client, "f@x.t", "farmer")
    register(client, "f2@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    register(client, "t@x.t", "transporter")
    admin = _make_admin(db)
    pid1 = _add_product(client, farmer, name="Tomato", quantity=100, price=30)
    _add_product(client, farmer, name="Potato", quantity=50, price=25)
    # One pending order (10 x 30 = 300, not revenue yet) and one accepted
    # order (5 x 30 = 150, counts as revenue).
    _place_order(client, buyer, pid1, quantity=10)
    oid = _place_order(client, buyer, pid1, quantity=5)
    r = client.patch(f"/api/v1/orders/{oid}/status", headers=farmer,
                     json={"status": "accepted"})
    assert r.status_code == 200, r.text

    stats = client.get("/api/v1/admin/stats", headers=admin).json()
    assert stats["total_users"] == 5
    assert stats["users_by_role"] == {"farmer": 2, "buyer": 1,
                                      "transporter": 1, "admin": 1}
    assert stats["total_products"] == 2
    assert stats["total_orders"] == 2
    assert stats["pending_orders"] == 1
    assert stats["total_revenue"] == 150


def test_stats_recent_activity_newest_first(client, db):
    """The activity feed lists the newest users/orders/products first."""
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    admin = _make_admin(db)
    pid = _add_product(client, farmer, name="Tomato", quantity=100, price=30)
    oid = _place_order(client, buyer, pid, quantity=10)

    stats = client.get("/api/v1/admin/stats", headers=admin).json()
    feed = stats["recent_activity"]
    kinds = {item["kind"] for item in feed}
    assert {"user", "order", "product"} <= kinds
    # The order is the newest thing created, so it leads the feed.
    assert feed[0]["kind"] == "order" and feed[0]["title"] == f"#{oid}"
    assert "Tomato" in feed[0]["detail"] and "10 kg" in feed[0]["detail"]
    product_item = next(i for i in feed if i["kind"] == "product")
    assert product_item["title"] == "Tomato" and product_item["detail"] == "Gazipur"
    user_item = next(i for i in feed if i["kind"] == "user")
    assert user_item["detail"] in {"farmer", "buyer", "admin"}
    # Timestamps are non-decreasing as the feed goes down (newest first).
    stamps = [i["created_at"] for i in feed]
    assert stamps == sorted(stamps, reverse=True)
    assert len(feed) <= 8


def test_stats_requires_admin(client, db):
    farmer = register(client, "f@x.t", "farmer")
    assert client.get("/api/v1/admin/stats", headers=farmer).status_code == 403
    assert client.get("/api/v1/admin/stats").status_code == 401
