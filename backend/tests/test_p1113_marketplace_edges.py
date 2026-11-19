"""Phase 11 (audit/p11-13): marketplace edge cases — product ownership +
validation + filters + empty lists, demand scoping + validation, match
scoping + empty datasets, the order state machine (invalid transitions,
stock release on reject/cancel incl. sold->available), dashboard empty
states, and price filters."""
import pytest

from conftest import register
from app import models


def add_product(client, headers, name="Tomato", quantity=100, price=30,
                district="Gazipur"):
    r = client.post("/api/v1/products", headers=headers,
                    json={"name": name, "quantity": quantity, "unit": "kg",
                          "price_per_unit": price, "district": district})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def place_order(client, headers, pid, quantity=10):
    r = client.post("/api/v1/orders", headers=headers,
                    json={"product_id": pid, "quantity": quantity})
    assert r.status_code == 200, r.text
    return r.json()["order_id"]


def product_quantity(client, pid):
    return client.get(f"/api/v1/products/{pid}").json()["quantity"]


# ---------------- products: empty + filters ----------------
def test_products_empty_list(client):
    assert client.get("/api/v1/products").json() == []


def test_products_search_and_district_filters(client):
    farmer = register(client, "f@x.t", "farmer")
    add_product(client, farmer, name="Tomato", district="Gazipur")
    add_product(client, farmer, name="Potato", district="Rangpur")
    add_product(client, farmer, name="Tomato", district="Rangpur")
    assert len(client.get("/api/v1/products").json()) == 3
    assert len(client.get("/api/v1/products",
                          params={"search": "tom"}).json()) == 2
    assert len(client.get("/api/v1/products",
                          params={"district": "rangpur"}).json()) == 2
    rows = client.get("/api/v1/products",
                      params={"search": "tomato", "district": "gazipur"}).json()
    assert len(rows) == 1 and rows[0]["district"] == "Gazipur"
    assert client.get("/api/v1/products",
                      params={"search": "mango"}).json() == []


def test_products_list_excludes_removed(client):
    farmer = register(client, "f@x.t", "farmer")
    pid = add_product(client, farmer)
    assert len(client.get("/api/v1/products").json()) == 1
    assert client.delete(f"/api/v1/products/{pid}", headers=farmer).status_code == 200
    assert client.get("/api/v1/products").json() == []


# ---------------- products: roles + ownership + validation ----------------
def test_product_create_requires_farmer(client):
    buyer = register(client, "b@x.t", "buyer")
    r = client.post("/api/v1/products", headers=buyer,
                    json={"name": "Tomato", "quantity": 10, "unit": "kg",
                          "price_per_unit": 30, "district": "Gazipur"})
    assert r.status_code == 403
    r = client.post("/api/v1/products",
                    json={"name": "Tomato", "quantity": 10, "unit": "kg",
                          "price_per_unit": 30, "district": "Gazipur"})
    assert r.status_code == 401


@pytest.mark.parametrize("field,value", [
    ("quantity", 0), ("quantity", -5), ("quantity", -0.5),
    ("price_per_unit", 0), ("price_per_unit", -1),
])
def test_product_create_rejects_non_positive_numbers(client, field, value):
    farmer = register(client, "f@x.t", "farmer")
    body = {"name": "Tomato", "quantity": 10, "unit": "kg",
            "price_per_unit": 30, "district": "Gazipur"}
    body[field] = value
    assert client.post("/api/v1/products", headers=farmer,
                       json=body).status_code == 422


def test_product_create_rejects_bad_unit_and_missing_district(client):
    farmer = register(client, "f@x.t", "farmer")
    assert client.post("/api/v1/products", headers=farmer,
                       json={"name": "Tomato", "quantity": 10, "unit": "sack",
                             "price_per_unit": 30,
                             "district": "Gazipur"}).status_code == 422
    assert client.post("/api/v1/products", headers=farmer,
                       json={"name": "Tomato", "quantity": 10, "unit": "kg",
                             "price_per_unit": 30}).status_code == 422


def test_product_edit_delete_ownership_and_404(client):
    farmer = register(client, "f@x.t", "farmer")
    other = register(client, "f2@x.t", "farmer")
    pid = add_product(client, farmer)
    body = {"name": "Tomato", "quantity": 50, "unit": "kg",
            "price_per_unit": 31, "district": "Gazipur"}
    assert client.put(f"/api/v1/products/{pid}", headers=other,
                      json=body).status_code == 403
    assert client.delete(f"/api/v1/products/{pid}",
                         headers=other).status_code == 403
    assert client.put("/api/v1/products/999999", headers=farmer,
                      json=body).status_code == 404
    assert client.delete("/api/v1/products/999999",
                         headers=farmer).status_code == 404
    # The owner can still edit after the forbidden attempts.
    assert client.put(f"/api/v1/products/{pid}", headers=farmer,
                      json=body).status_code == 200
    assert product_quantity(client, pid) == 50


def test_product_edit_validation_422(client):
    farmer = register(client, "f@x.t", "farmer")
    pid = add_product(client, farmer)
    body = {"name": "Tomato", "quantity": 0, "unit": "kg",
            "price_per_unit": 30, "district": "Gazipur"}
    assert client.put(f"/api/v1/products/{pid}", headers=farmer,
                      json=body).status_code == 422


# ---------------- demands: scoping + validation ----------------
def test_demands_buyer_sees_only_own_farmer_sees_all(client):
    b1 = register(client, "b1@x.t", "buyer")
    b2 = register(client, "b2@x.t", "buyer")
    farmer = register(client, "f@x.t", "farmer")
    demand = {"product_name": "Tomato", "required_quantity": 50, "unit": "kg",
              "target_price": 35, "district": "Dhaka"}
    assert client.post("/api/v1/demands", headers=b1, json=demand).status_code == 200
    assert client.post("/api/v1/demands", headers=b2, json=demand).status_code == 200
    assert len(client.get("/api/v1/demands", headers=b1).json()) == 1
    assert len(client.get("/api/v1/demands", headers=b2).json()) == 1
    assert len(client.get("/api/v1/demands", headers=farmer).json()) == 2
    assert client.get("/api/v1/demands").status_code == 401


def test_demands_empty_list(client):
    farmer = register(client, "f@x.t", "farmer")
    assert client.get("/api/v1/demands", headers=farmer).json() == []


def test_demand_create_validation_and_role(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    base = {"product_name": "Tomato", "required_quantity": 50, "unit": "kg",
            "target_price": 35, "district": "Dhaka"}
    assert client.post("/api/v1/demands", headers=farmer,
                       json=base).status_code == 403
    assert client.post("/api/v1/demands", headers=buyer,
                       json={**base, "required_quantity": 0}).status_code == 422
    assert client.post("/api/v1/demands", headers=buyer,
                       json={**base, "target_price": -1}).status_code == 422
    assert client.post("/api/v1/demands", headers=buyer,
                       json={**base, "unit": "sack"}).status_code == 422


# ---------------- matches: empty + scoping ----------------
def test_matches_empty_dataset(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    assert client.get("/api/v1/matches", headers=farmer).json() == []
    assert client.get("/api/v1/matches", headers=buyer).json() == []


def test_matches_scoped_to_viewer(client):
    f1 = register(client, "f1@x.t", "farmer")
    f2 = register(client, "f2@x.t", "farmer")
    b1 = register(client, "b1@x.t", "buyer")
    b2 = register(client, "b2@x.t", "buyer")
    # Compatible pair: same crop/unit/district, price within range.
    add_product(client, f1, name="Tomato", quantity=600, price=35)
    add_product(client, f2, name="Tomato", quantity=600, price=35)
    demand = {"product_name": "Tomato", "required_quantity": 500, "unit": "kg",
              "target_price": 40, "district": "Gazipur"}
    client.post("/api/v1/demands", headers=b1, json=demand)
    client.post("/api/v1/demands", headers=b2, json=demand)
    # Each farmer sees only matches against their own product (2 demands).
    assert len(client.get("/api/v1/matches", headers=f1).json()) == 2
    assert len(client.get("/api/v1/matches", headers=f2).json()) == 2
    # Each buyer sees only matches against their own demand (2 products).
    assert len(client.get("/api/v1/matches", headers=b1).json()) == 2
    assert len(client.get("/api/v1/matches", headers=b2).json()) == 2
    # Scores are sorted descending and every match clears the threshold.
    scores = [m["score"] for m in client.get("/api/v1/matches", headers=f1).json()]
    assert scores == sorted(scores, reverse=True) and all(s >= 50 for s in scores)


def test_matches_include_buyer_id(client):
    """The farmer needs the buyer's id to start a conversation (19 Nov 2026:
    buyer->farmer messaging worked, but farmer->buyer had no buyer id to
    message, so the farmer had no way to reply)."""
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    buyer_id = client.get("/api/v1/auth/me", headers=buyer).json()["id"]
    add_product(client, farmer, name="Tomato", quantity=600, price=35)
    client.post("/api/v1/demands", headers=buyer,
                json={"product_name": "Tomato", "required_quantity": 500,
                      "unit": "kg", "target_price": 40, "district": "Gazipur"})
    rows = client.get("/api/v1/matches", headers=farmer).json()
    assert len(rows) == 1
    assert rows[0]["buyer_id"] == buyer_id
    # The buyer sees the same buyer_id on their own view of the match.
    rows = client.get("/api/v1/matches", headers=buyer).json()
    assert len(rows) == 1 and rows[0]["buyer_id"] == buyer_id


def test_matches_no_match_for_incompatible_product(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    add_product(client, farmer, name="Potato", quantity=600, price=35)
    client.post("/api/v1/demands", headers=buyer,
                json={"product_name": "Tomato", "required_quantity": 500,
                      "unit": "kg", "target_price": 40, "district": "Gazipur"})
    assert client.get("/api/v1/matches", headers=farmer).json() == []


# ---------------- orders: validation + state machine ----------------
def test_order_requires_buyer_role(client):
    farmer = register(client, "f@x.t", "farmer")
    pid = add_product(client, farmer)
    r = client.post("/api/v1/orders", headers=farmer,
                    json={"product_id": pid, "quantity": 1})
    assert r.status_code == 403


def test_order_unknown_or_removed_product_404(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer)
    assert client.post("/api/v1/orders", headers=buyer,
                       json={"product_id": 999999,
                             "quantity": 1}).status_code == 404
    client.delete(f"/api/v1/products/{pid}", headers=farmer)
    assert client.post("/api/v1/orders", headers=buyer,
                       json={"product_id": pid, "quantity": 1}).status_code == 404


def test_order_insufficient_stock_409_and_stock_unchanged(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer, quantity=10)
    r = client.post("/api/v1/orders", headers=buyer,
                    json={"product_id": pid, "quantity": 11})
    assert r.status_code == 409
    assert product_quantity(client, pid) == 10
    # Exact remaining stock succeeds and flips the listing to sold.
    oid = place_order(client, buyer, pid, quantity=10)
    assert client.get(f"/api/v1/products/{pid}").json()["status"] == "sold"
    assert client.get("/api/v1/products").json() == []


def test_order_quantity_validation_422(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer)
    assert client.post("/api/v1/orders", headers=buyer,
                       json={"product_id": pid, "quantity": 0}).status_code == 422
    assert client.post("/api/v1/orders", headers=buyer,
                       json={"product_id": pid,
                             "quantity": -2}).status_code == 422


def test_order_invalid_transitions_rejected(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    stranger = register(client, "s@x.t", "buyer")
    pid = add_product(client, farmer)
    oid = place_order(client, buyer, pid, quantity=10)
    # Farmer cannot complete a pending order.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=farmer,
                        json={"status": "completed"}).status_code == 400
    # Buyer cannot accept/reject their own order.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=buyer,
                        json={"status": "accepted"}).status_code == 400
    # A stranger cannot change anything.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=stranger,
                        json={"status": "cancelled"}).status_code == 403
    # Accept, then the buyer can no longer cancel and the farmer cannot
    # re-accept.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=farmer,
                        json={"status": "accepted"}).status_code == 200
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=buyer,
                        json={"status": "cancelled"}).status_code == 400
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=farmer,
                        json={"status": "accepted"}).status_code == 400
    # Complete, then nothing else is allowed.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=farmer,
                        json={"status": "completed"}).status_code == 200
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=farmer,
                        json={"status": "rejected"}).status_code == 400
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=buyer,
                        json={"status": "cancelled"}).status_code == 400
    # Unknown order.
    assert client.patch("/api/v1/orders/999999/status", headers=farmer,
                        json={"status": "accepted"}).status_code == 404


def test_order_reject_releases_stock_once(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer, quantity=100)
    oid = place_order(client, buyer, pid, quantity=40)
    assert product_quantity(client, pid) == 60
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=farmer,
                        json={"status": "rejected"}).status_code == 200
    assert product_quantity(client, pid) == 100
    # A rejected order cannot transition again, so stock is never double-released.
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=farmer,
                        json={"status": "rejected"}).status_code == 400
    assert product_quantity(client, pid) == 100


def test_order_cancel_restores_sold_listing_to_available(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer, quantity=10)
    oid = place_order(client, buyer, pid, quantity=10)
    assert client.get(f"/api/v1/products/{pid}").json()["status"] == "sold"
    assert client.patch(f"/api/v1/orders/{oid}/status", headers=buyer,
                        json={"status": "cancelled"}).status_code == 200
    detail = client.get(f"/api/v1/products/{pid}").json()
    assert detail["status"] == "available" and detail["quantity"] == 10
    assert len(client.get("/api/v1/products").json()) == 1


def test_order_detail_admin_can_view(client, db):
    from app.security import create_access_token, hash_password
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    pid = add_product(client, farmer)
    oid = place_order(client, buyer, pid, quantity=5)
    admin = models.User(email="admin@x.t", name="Admin", role="admin",
                        district="Dhaka",
                        password_hash=hash_password("Passw0rd!"))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    ah = {"Authorization": "Bearer " + create_access_token(admin.id)}
    r = client.get(f"/api/v1/orders/{oid}", headers=ah)
    assert r.status_code == 200
    assert r.json()["buyer"]["name"] and r.json()["farmer"]["name"]


def test_my_orders_empty_and_scoped(client):
    f1 = register(client, "f1@x.t", "farmer")
    f2 = register(client, "f2@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    assert client.get("/api/v1/orders/my", headers=f1).json() == []
    assert client.get("/api/v1/orders/my", headers=buyer).json() == []
    pid = add_product(client, f1)
    place_order(client, buyer, pid, quantity=5)
    assert len(client.get("/api/v1/orders/my", headers=f1).json()) == 1
    assert len(client.get("/api/v1/orders/my", headers=f2).json()) == 0
    assert len(client.get("/api/v1/orders/my", headers=buyer).json()) == 1


# ---------------- dashboard: empty states ----------------
def test_dashboard_empty_farmer_and_buyer_zeros(client):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    dash = client.get("/api/v1/dashboard", headers=farmer).json()
    assert dash == {"role": "farmer", "total_products": 0,
                    "available_quantity": 0, "active_orders": 0,
                    "total_sales": 0}
    dash = client.get("/api/v1/dashboard", headers=buyer).json()
    assert dash == {"role": "buyer", "total_orders": 0, "open_demands": 0,
                    "total_spent": 0, "recent_orders": 0}
    assert client.get("/api/v1/dashboard").status_code == 401


# ---------------- prices: filters ----------------
def test_prices_filters_and_empty(client, db):
    assert client.get("/api/v1/prices").json() == []
    db.add(models.PriceRecord(product_name="Tomato", district="Dhaka",
                              market_name="Karwan Bazar", price_per_unit=40,
                              unit="kg", source="manual"))
    db.add(models.PriceRecord(product_name="Potato", district="Rangpur",
                              market_name="Rangpur Sadar", price_per_unit=25,
                              unit="kg", source="manual"))
    db.commit()
    assert len(client.get("/api/v1/prices").json()) == 2
    rows = client.get("/api/v1/prices",
                      params={"product_name": "tom"}).json()
    assert len(rows) == 1 and rows[0]["product_name"] == "Tomato"
    rows = client.get("/api/v1/prices",
                      params={"district": "rangpur"}).json()
    assert len(rows) == 1 and rows[0]["product_name"] == "Potato"
    assert client.get("/api/v1/prices",
                      params={"product_name": "mango"}).json() == []
