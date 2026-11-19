"""Phase 11 (audit/p11-13): admin user-list pagination — the only paginated
list endpoint in the API — plus boundary validation and the verify-404
case."""
from conftest import register
from app import models
from app.security import create_access_token, hash_password


def make_admin(client, db):
    admin = models.User(email="admin@x.t", name="Admin", role="admin",
                        district="Dhaka",
                        password_hash=hash_password("Passw0rd!"))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return {"Authorization": "Bearer " + create_access_token(admin.id)}


def seed_users(db, n, role="farmer"):
    for i in range(n):
        db.add(models.User(email=f"u{i:02d}@x.t", name=f"User {i:02d}",
                           role=role, district="Dhaka",
                           password_hash=hash_password("Passw0rd!")))
    db.commit()


def test_admin_users_pagination_pages(client, db):
    ah = make_admin(client, db)
    seed_users(db, 5)
    page1 = client.get("/api/v1/admin/users", headers=ah,
                       params={"page": 1, "page_size": 2}).json()
    assert page1["total"] == 6  # 5 seeded + the admin
    assert page1["page"] == 1 and page1["page_size"] == 2
    assert len(page1["items"]) == 2
    page2 = client.get("/api/v1/admin/users", headers=ah,
                       params={"page": 2, "page_size": 2}).json()
    assert len(page2["items"]) == 2
    page3 = client.get("/api/v1/admin/users", headers=ah,
                       params={"page": 3, "page_size": 2}).json()
    assert len(page3["items"]) == 2
    # Pages are disjoint and together cover everyone.
    ids = ([u["id"] for u in page1["items"]] + [u["id"] for u in page2["items"]]
           + [u["id"] for u in page3["items"]])
    assert len(set(ids)) == 6


def test_admin_users_pagination_past_end_is_empty(client, db):
    ah = make_admin(client, db)
    seed_users(db, 2)
    page = client.get("/api/v1/admin/users", headers=ah,
                      params={"page": 99, "page_size": 20}).json()
    assert page["total"] == 3 and page["items"] == []


def test_admin_users_pagination_defaults(client, db):
    ah = make_admin(client, db)
    seed_users(db, 3)
    page = client.get("/api/v1/admin/users", headers=ah).json()
    assert page["page"] == 1 and page["page_size"] == 20
    assert page["total"] == 4 and len(page["items"]) == 4


def test_admin_users_pagination_bounds_422(client, db):
    ah = make_admin(client, db)
    assert client.get("/api/v1/admin/users", headers=ah,
                      params={"page": 0}).status_code == 422
    assert client.get("/api/v1/admin/users", headers=ah,
                      params={"page": -1}).status_code == 422
    assert client.get("/api/v1/admin/users", headers=ah,
                      params={"page_size": 0}).status_code == 422
    assert client.get("/api/v1/admin/users", headers=ah,
                      params={"page_size": 101}).status_code == 422
    assert client.get("/api/v1/admin/users", headers=ah,
                      params={"page_size": 100}).status_code == 200


def test_admin_users_role_and_search_combine(client, db):
    ah = make_admin(client, db)
    seed_users(db, 3, role="farmer")
    for i in range(2):
        db.add(models.User(email=f"b{i}@x.t", name=f"Buyer {i}",
                           role="buyer", district="Dhaka",
                           password_hash=hash_password("Passw0rd!")))
    db.commit()
    page = client.get("/api/v1/admin/users", headers=ah,
                      params={"role": "buyer"}).json()
    assert page["total"] == 2
    page = client.get("/api/v1/admin/users", headers=ah,
                      params={"role": "farmer", "search": "u01"}).json()
    assert page["total"] == 1
    assert page["items"][0]["email"] == "u01@x.t"
    # Search matching nothing returns an empty page, not an error.
    page = client.get("/api/v1/admin/users", headers=ah,
                      params={"search": "nobody-here"}).json()
    assert page["total"] == 0 and page["items"] == []


def test_admin_verify_unknown_user_404(client, db):
    ah = make_admin(client, db)
    r = client.patch("/api/v1/admin/users/999999/verify", headers=ah,
                     json={"is_verified": True})
    assert r.status_code == 404


def test_admin_audit_logs_empty_when_nothing_logged(client, db):
    # The admin is created directly in the DB (no register call), so no
    # audit rows exist yet.
    ah = make_admin(client, db)
    assert client.get("/api/v1/admin/audit-logs", headers=ah).json() == []


def test_admin_stats_empty_platform_zeros(client, db):
    ah = make_admin(client, db)
    stats = client.get("/api/v1/admin/stats", headers=ah).json()
    # Field names match the frontend AdminStats contract (a mismatch here
    # used to render every admin counter as 0 — 19 Nov 2026 live QA).
    assert stats["total_users"] == 1
    assert stats["users_by_role"] == {"admin": 1}
    assert stats["total_products"] == 0 and stats["total_orders"] == 0
    assert stats["pending_orders"] == 0 and stats["total_revenue"] == 0
    # Only the admin user exists, so the activity feed has just that entry.
    assert len(stats["recent_activity"]) == 1
    assert stats["recent_activity"][0]["kind"] == "user"
