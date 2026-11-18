"""Manual daily price entry + REAL/DEMO labelling + staleness (Workstream E).

Covers: admin-only POST /api/v1/prices/manual (validation, source/timestamp
storage, same-day update), GET /api/v1/prices/latest labelling, the enriched
GET /api/v1/prices labels, and the forecaster's preference for real series.
"""
from datetime import date, datetime, timedelta

from conftest import register
from app import models
from app.config import get_hub
from app.security import create_access_token, hash_password
from app.services import price_labels as PL
from app.services import sklearn_forecast as SK
from app.services.datasources import prices, synthetic

TODAY = date.today()


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


def _admin(db):
    return auth_headers(make_user(db, "admin@x.t", "admin"))


def _obs(db, hub="dhaka", crop="tomato", day=TODAY, price=50.0, source="manual",
         synthetic_flag=False, note=None):
    db.add(models.PriceObservation(hub_id=hub, crop=crop, observed_on=day, price=price,
                                   currency="BDT", unit="kg", source=source,
                                   is_synthetic=synthetic_flag, note=note,
                                   ingested_at=datetime.utcnow()))
    db.commit()


# ---------------- POST /api/v1/prices/manual: auth + validation ----------------
def test_manual_requires_admin(client, db):
    farmer = register(client, "f@x.t", "farmer")
    body = {"crop": "tomato", "hub": "dhaka", "price": 55, "date": TODAY.isoformat()}
    assert client.post("/api/v1/prices/manual", json=body).status_code == 401
    assert client.post("/api/v1/prices/manual", json=body, headers=farmer).status_code == 403


def test_manual_create_stores_source_and_timestamp(client, db):
    r = client.post("/api/v1/prices/manual", headers=_admin(db),
                    json={"crop": "tomato", "hub": "dhaka", "price": 55.5,
                          "date": TODAY.isoformat(), "note": "DAM Dhaka retail report"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["updated"] is False
    assert body["source"] == "manual" and body["note"] == "DAM Dhaka retail report"
    assert body["label"] == "real" and body["is_synthetic"] is False
    assert body["stale"] is False and body["observed_on"] == TODAY.isoformat()
    assert body["ingested_at"]  # entry timestamp recorded
    row = db.query(models.PriceObservation).one()
    assert row.source == "manual" and row.is_synthetic is False
    assert row.price == 55.5 and row.ingested_at is not None


def test_manual_defaults_to_today_and_accepts_source_note_alias(client, db):
    r = client.post("/api/v1/prices/manual", headers=_admin(db),
                    json={"crop": "onion", "hub": "khulna", "price": 60,
                          "source_note": "DAM Khulna"})
    assert r.status_code == 201, r.text
    assert r.json()["observed_on"] == TODAY.isoformat()
    assert r.json()["note"] == "DAM Khulna"


def test_manual_same_day_reentry_updates_instead_of_duplicating(client, db):
    admin = _admin(db)
    payload = {"crop": "tomato", "hub": "dhaka", "price": 55, "date": TODAY.isoformat()}
    assert client.post("/api/v1/prices/manual", headers=admin, json=payload).status_code == 201
    payload["price"] = 58
    r = client.post("/api/v1/prices/manual", headers=admin, json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["updated"] is True and r.json()["price"] == 58
    assert db.query(models.PriceObservation).count() == 1


def test_manual_validation(client, db):
    admin = _admin(db)
    base = {"crop": "tomato", "hub": "dhaka", "price": 55, "date": TODAY.isoformat()}
    assert client.post("/api/v1/prices/manual", headers=admin,
                       json={**base, "crop": "kryptonite"}).status_code == 404
    assert client.post("/api/v1/prices/manual", headers=admin,
                       json={**base, "hub": "atlantis"}).status_code == 404
    assert client.post("/api/v1/prices/manual", headers=admin,
                       json={**base, "price": 0}).status_code == 422
    assert client.post("/api/v1/prices/manual", headers=admin,
                       json={**base, "price": -5}).status_code == 422
    assert client.post("/api/v1/prices/manual", headers=admin,
                       json={**base, "date": (TODAY + timedelta(days=1)).isoformat()}).status_code == 422
    assert client.post("/api/v1/prices/manual", headers=admin,
                       json={"crop": "tomato", "hub": "dhaka"}).status_code == 422
    assert db.query(models.PriceObservation).count() == 0


def test_manual_list_is_admin_only_and_newest_first(client, db):
    _obs(db, crop="tomato", day=TODAY - timedelta(days=1), price=50)
    _obs(db, crop="onion", day=TODAY, price=60)
    _obs(db, crop="potato", day=TODAY, price=30, source="synthetic-demo", synthetic_flag=True)
    assert client.get("/api/v1/prices/manual").status_code == 401
    r = client.get("/api/v1/prices/manual", headers=_admin(db))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["crop"] for i in items] == ["onion", "tomato"]  # synthetic row excluded
    assert all(i["source"] == "manual" for i in items)


# ---------------- labelling + staleness ----------------
def test_price_labels_unit():
    assert PL.price_label(True) == "demo" and PL.price_label(False) == "real"
    assert PL.record_label("Illustrative demo data - replace with verified source") == "demo"
    assert PL.record_label("synthetic-demo") == "demo"
    assert PL.record_label("DAM Dhaka") == "real"
    # Demo is never stale, however old; real is stale past 48h.
    assert PL.is_stale(TODAY - timedelta(days=365), True) is False
    assert PL.is_stale(TODAY, False) is False
    assert PL.is_stale(TODAY - timedelta(days=1), False) is False
    assert PL.is_stale(TODAY - timedelta(days=3), False) is True
    assert PL.is_stale(None, False) is True  # no timestamp: freshness not claimed


def test_latest_labels_real_demo_and_stale(client, db):
    _obs(db, crop="tomato", day=TODAY, price=55)                       # real, fresh
    _obs(db, crop="onion", day=TODAY - timedelta(days=5), price=60)    # real, stale
    _obs(db, crop="potato", day=TODAY, price=30,
         source="synthetic-demo", synthetic_flag=True)                 # demo
    r = client.get("/api/v1/prices/latest")
    assert r.status_code == 200, r.text
    by_crop = {p["crop"]: p for p in r.json()["prices"]}
    assert by_crop["tomato"]["label"] == "real" and by_crop["tomato"]["stale"] is False
    assert by_crop["onion"]["label"] == "real" and by_crop["onion"]["stale"] is True
    assert by_crop["potato"]["label"] == "demo" and by_crop["potato"]["stale"] is False
    for p in by_crop.values():
        assert p["source"] and p["observed_on"] and p["ingested_at"]
    assert client.get("/api/v1/prices/latest",
                      params={"hub": "atlantis"}).status_code == 404
    assert client.get("/api/v1/prices/latest",
                      params={"crop": "kryptonite"}).status_code == 404
    filtered = client.get("/api/v1/prices/latest", params={"crop": "onion"}).json()
    assert [p["crop"] for p in filtered["prices"]] == ["onion"]


def test_latest_picks_most_recent_day_per_pair(client, db):
    _obs(db, crop="tomato", day=TODAY - timedelta(days=9), price=40)
    _obs(db, crop="tomato", day=TODAY, price=55)
    r = client.get("/api/v1/prices/latest")
    assert r.json()["count"] == 1
    assert r.json()["prices"][0]["price"] == 55


def test_prices_endpoint_returns_label_and_stale(client, db):
    db.add(models.PriceRecord(product_name="Tomato", district="Dhaka", price_per_unit=50,
                              unit="kg", source="Illustrative demo data - replace with verified source",
                              recorded_at=datetime.utcnow() - timedelta(days=30)))
    db.add(models.PriceRecord(product_name="Onion", district="Dhaka", price_per_unit=60,
                              unit="kg", source="DAM Dhaka",
                              recorded_at=datetime.utcnow() - timedelta(days=5)))
    db.add(models.PriceRecord(product_name="Potato", district="Dhaka", price_per_unit=30,
                              unit="kg", source="DAM Dhaka", recorded_at=datetime.utcnow()))
    db.commit()
    rows = {r["product_name"]: r for r in client.get("/api/v1/prices").json()}
    assert rows["Tomato"]["label"] == "demo" and rows["Tomato"]["stale"] is False
    assert rows["Onion"]["label"] == "real" and rows["Onion"]["stale"] is True
    assert rows["Potato"]["label"] == "real" and rows["Potato"]["stale"] is False


# ---------------- forecaster prefers real series ----------------
def _real_daily(db, days, crop="tomato"):
    for i in range(days):
        _obs(db, crop=crop, day=TODAY - timedelta(days=days - 1 - i),
             price=50 + (i % 7), source="manual")


def test_sklearn_prefers_real_series_when_long_enough(db):
    prices.upsert_prices(db, synthetic.synthetic_rows([get_hub("dhaka")], years=1))
    _real_daily(db, 40)
    r = SK.forecast_sklearn(db, get_hub("dhaka"), "tomato", horizon=6)
    assert r["series"]["real_only"] is True
    assert r["series"]["synthetic_share"] == 0.0
    assert r["series"]["sources"] == ["manual"]
    assert r["frequency"] == "D"
    assert not any("SYNTHETIC" in w for w in r["warnings"])


def test_sklearn_falls_back_to_mixed_series_when_real_too_short(db):
    prices.upsert_prices(db, synthetic.synthetic_rows([get_hub("dhaka")], years=1))
    _real_daily(db, 10)
    r = SK.forecast_sklearn(db, get_hub("dhaka"), "tomato", horizon=6)
    assert r["series"]["real_only"] is False
    assert r["series"]["synthetic_share"] > 0
    assert any("SYNTHETIC" in w for w in r["warnings"])
