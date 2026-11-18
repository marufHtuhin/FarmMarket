"""GET /api/v1/prices/history: the trend-chart series (WS3).

The trend chart used to read PriceRecord (one seeded row per product, so a
one-point chart) while the 2-year weekly history sat in PriceObservation.
This endpoint serves that stored series: dated points, oldest first, one
point per market day, each with source, REAL/DEMO label and staleness.
"""
from datetime import date, datetime, timedelta

from conftest import register
from app import models
from app.config import get_hub
from app.security import create_access_token, hash_password
from app.services.datasources import prices, synthetic

TODAY = date.today()


def _admin_headers(db):
    u = models.User(email="admin@x.t", name="Admin", role="admin", district="Dhaka",
                    password_hash=hash_password("Passw0rd!"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"Authorization": "Bearer " + create_access_token(u.id)}


def _seed_history(db, hub="dhaka", crop="tomato", years=2):
    rows = synthetic.synthetic_rows([get_hub(hub)], years=years,
                                    end=TODAY.isoformat(), seed=7)
    rows = [r for r in rows if r["crop"] == crop]
    prices.upsert_prices(db, rows)
    return rows


def test_history_returns_full_series_oldest_first(client, db):
    _seed_history(db)
    r = client.get("/api/v1/prices/history", params={"hub": "dhaka", "crop": "tomato"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hub"] == "dhaka" and body["crop"] == "tomato"
    assert body["count"] == 104 == len(body["points"])
    dates = [p["observed_on"] for p in body["points"]]
    assert dates == sorted(dates)
    # Weekly series anchored on Sundays, ending the last Sunday on/before the seed date.
    assert date.fromisoformat(dates[-1]).weekday() == 6  # Sunday
    assert (TODAY - date.fromisoformat(dates[-1])).days < 7
    assert (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days >= 700


def test_history_point_shape_and_synthetic_labels(client, db):
    _seed_history(db)
    r = client.get("/api/v1/prices/history", params={"hub": "dhaka", "crop": "tomato"})
    p = r.json()["points"][0]
    assert p["source"] == "synthetic-demo"
    assert p["is_synthetic"] is True
    assert p["label"] == "demo"
    assert p["stale"] is False  # demo data is never called stale
    assert p["observed_on"] and p["ingested_at"] and p["price"] > 0
    assert p["currency"] == "BDT" and p["unit"] == "kg"
    assert p["age_hours"] is not None


def test_history_filters_by_hub_and_crop(client, db):
    # Seed both hubs in ONE generator call: separate calls with the same
    # seed would replay identical random draws per hub.
    rows = synthetic.synthetic_rows([get_hub("dhaka"), get_hub("chattogram")],
                                    years=2, end=TODAY.isoformat(), seed=7)
    prices.upsert_prices(db, rows)
    dhaka_tom = client.get("/api/v1/prices/history",
                           params={"hub": "dhaka", "crop": "tomato"}).json()
    ctg_tom = client.get("/api/v1/prices/history",
                         params={"hub": "chattogram", "crop": "tomato"}).json()
    dhaka_pot = client.get("/api/v1/prices/history",
                           params={"hub": "dhaka", "crop": "potato"}).json()
    assert dhaka_tom["count"] == ctg_tom["count"] == dhaka_pot["count"] == 104
    # Same dates, different series (different hub/crop baselines).
    assert dhaka_tom["points"][0]["observed_on"] == ctg_tom["points"][0]["observed_on"]
    assert dhaka_tom["points"][0]["price"] != ctg_tom["points"][0]["price"]
    assert dhaka_tom["points"][0]["price"] != dhaka_pot["points"][0]["price"]
    assert {p["hub"] for p in dhaka_tom["points"]} == {"dhaka"}
    assert {p["crop"] for p in dhaka_pot["points"]} == {"potato"}


def test_history_unknown_hub_or_crop_404(client, db):
    assert client.get("/api/v1/prices/history",
                      params={"hub": "nowhere", "crop": "tomato"}).status_code == 404
    assert client.get("/api/v1/prices/history",
                      params={"hub": "dhaka", "crop": "durian"}).status_code == 404


def test_history_empty_series_is_200_with_no_points(client, db):
    r = client.get("/api/v1/prices/history", params={"hub": "dhaka", "crop": "tomato"})
    assert r.status_code == 200
    assert r.json() == {"hub": "dhaka", "crop": "tomato", "points": [], "count": 0}


def test_history_requires_hub_and_crop(client, db):
    assert client.get("/api/v1/prices/history", params={"hub": "dhaka"}).status_code == 422
    assert client.get("/api/v1/prices/history").status_code == 422


def test_manual_entry_appears_as_new_point(client, db):
    _seed_history(db)
    headers = _admin_headers(db)
    # A weekday date has no synthetic point (weekly series is Sunday-anchored),
    # so the manual entry must appear as an extra point.
    day = TODAY - timedelta(days=TODAY.weekday())  # most recent Monday
    r = client.post("/api/v1/prices/manual", headers=headers,
                    json={"crop": "tomato", "hub": "dhaka", "price": 95.5,
                          "date": day.isoformat(), "note": "DAM Dhaka"})
    assert r.status_code == 201, r.text
    body = client.get("/api/v1/prices/history",
                      params={"hub": "dhaka", "crop": "tomato"}).json()
    assert body["count"] == 105
    mine = [p for p in body["points"] if p["observed_on"] == day.isoformat()]
    assert len(mine) == 1
    assert mine[0]["price"] == 95.5
    assert mine[0]["source"] == "manual" and mine[0]["label"] == "real"
    assert mine[0]["is_synthetic"] is False
    assert mine[0]["note"] == "DAM Dhaka"
    dates = [p["observed_on"] for p in body["points"]]
    assert dates == sorted(dates)


def test_manual_entry_on_synthetic_date_replaces_that_days_point(client, db):
    _seed_history(db)
    headers = _admin_headers(db)
    before = client.get("/api/v1/prices/history",
                        params={"hub": "dhaka", "crop": "tomato"}).json()
    sunday = before["points"][-1]["observed_on"]  # latest synthetic Sunday
    r = client.post("/api/v1/prices/manual", headers=headers,
                    json={"crop": "tomato", "hub": "dhaka", "price": 101.0,
                          "date": sunday})
    assert r.status_code == 201, r.text
    after = client.get("/api/v1/prices/history",
                       params={"hub": "dhaka", "crop": "tomato"}).json()
    assert after["count"] == 104  # still one point per market day
    mine = [p for p in after["points"] if p["observed_on"] == sunday]
    assert len(mine) == 1
    assert mine[0]["price"] == 101.0 and mine[0]["label"] == "real"


def test_history_is_public_no_auth_needed(client, db):
    _seed_history(db)
    assert client.get("/api/v1/prices/history",
                      params={"hub": "dhaka", "crop": "tomato"}).status_code == 200
