import importlib.util
import io
import numpy as np
import pytest
from datetime import datetime, timedelta

from conftest import register, fruit_image
from app.services import twin as T, vision as V
from app.services.datasources import prices, synthetic
from app.config import get_hub


def test_existing_marketplace_still_works(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/v1/products").status_code == 200


# ---------------- forecast
def test_forecast_endpoints(client, db):
    prices.upsert_prices(db, synthetic.synthetic_rows([get_hub("dhaka")]))
    h = client.get("/api/v1/forecast/hubs").json()
    assert h["profile"] == "bangladesh"
    assert [x["id"] for x in h["hubs"]] == ["dhaka", "chattogram", "rajshahi", "khulna", "sylhet"]
    r = client.get("/api/v1/forecast/sklearn", params={"hub": "dhaka", "crop": "tomato", "horizon": 6})
    assert r.status_code == 200 and len(r.json()["forecast"]) == 6 and r.json()["series"]["synthetic_share"] == 1.0
    assert r.json()["model"] == "sklearn-random-forest"
    assert client.get("/api/v1/forecast/sklearn", params={"hub": "chattogram", "crop": "maize"}).status_code == 422   # no data
    assert client.get("/api/v1/forecast/sklearn", params={"hub": "mars", "crop": "maize"}).status_code == 404
    assert client.get("/api/v1/forecast/sklearn", params={"hub": "dhaka", "crop": "maize", "horizon": 500}).status_code == 422
    # Prophet endpoint: 200 when Prophet is installed, explicit 503 when not.
    r = client.get("/api/v1/forecast", params={"hub": "dhaka", "crop": "tomato", "horizon": 6})
    if importlib.util.find_spec("prophet"):
        assert r.status_code == 200 and len(r.json()["forecast"]) == 6
        assert client.get("/api/v1/forecast/overview", params={"horizon": 6}).json()["forecasts"][0]["hub"] == "dhaka"
    else:
        assert r.status_code == 503
    assert client.get("/api/v1/forecast", params={"hub": "chattogram", "crop": "maize"}).status_code == 422   # no data
    assert client.get("/api/v1/forecast", params={"hub": "mars", "crop": "maize"}).status_code == 404


# ---------------- vision
@pytest.fixture()
def trained_models(tmp_path, monkeypatch):
    rng = np.random.default_rng(0)
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    V.train_classifier([(fruit_image(k, rng), k) for k in V.RIPENESS_CLASSES for _ in range(40)], "ripeness", tmp_path)
    V.train_classifier([(fruit_image("ripe", rng), "Tomato___healthy") for _ in range(50)]
                       + [(fruit_image("ripe", rng, True), "Tomato___Early_blight") for _ in range(50)], "disease", tmp_path)
    return tmp_path


def test_vision_requires_farmer_and_models(client):
    img = ("a.png", fruit_image("ripe", np.random.default_rng(1)), "image/png")
    assert client.post("/api/v1/vision/assess", files={"image": img}).status_code == 401
    buyer = register(client, "b@x.t", "buyer")
    assert client.post("/api/v1/vision/assess", files={"image": img}, headers=buyer).status_code == 403
    farmer = register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/vision/assess", files={"image": img}, headers=farmer)
    assert r.status_code in (503,)       # no models trained -> explicit refusal, not a guess


def test_vision_grade_pricing_flow(client, trained_models):
    farmer = register(client, "f@x.t", "farmer")
    pid = client.post("/api/v1/products", headers=farmer, json={"name": "Tomato", "quantity": 100, "unit": "kg",
                      "price_per_unit": 30, "district": "Gazipur"}).json()["id"]
    img = ("a.png", fruit_image("ripe", np.random.default_rng(9)), "image/png")
    r = client.post("/api/v1/vision/assess", files={"image": img}, headers=farmer,
                    data={"crop": "tomato", "reference_price": "40", "product_id": str(pid)})
    body = r.json()
    assert r.status_code == 200 and body["grade"] == "A" and body["suggested_price"] == 40.0
    assert body["price_applied"] is False
    assert client.get("/api/v1/products").json()[0]["price_per_unit"] == 30          # not changed without opt-in
    r = client.post("/api/v1/vision/assess", files={"image": img}, headers=farmer,
                    data={"crop": "tomato", "reference_price": "50", "product_id": str(pid), "apply_price": "true"})
    assert r.json()["price_applied"] and client.get("/api/v1/products").json()[0]["price_per_unit"] == 50.0
    other = register(client, "f2@x.t", "farmer")
    assert client.post("/api/v1/vision/assess", files={"image": img}, headers=other,
                       data={"product_id": str(pid)}).status_code == 404                # not their product
    assert client.post("/api/v1/vision/assess", headers=farmer, files={"image": ("x.png", b"junk", "image/png")}).status_code == 400
    assert client.get("/api/v1/vision/status").json()["models"]["ripeness"] is not None


# ---------------- advisor
def test_advisor_template_mode_and_validation(client, db, monkeypatch):
    from app.services.datasources import openmeteo
    # Weather is keyless Open-Meteo now: mock the adapter down so this
    # test never touches the live network (advice does not need weather).
    monkeypatch.setattr(openmeteo, "fetch_daily_outlook",
                        lambda *a, **k: None)
    h = register(client, "f@x.t", "farmer")
    assert client.post("/api/v1/advisor/advice", json={"crop": "maize"}).status_code == 401
    assert len(client.get("/api/v1/advisor/languages").json()) >= 8
    r = client.post("/api/v1/advisor/advice", headers=h, json={"crop": "maize", "language": "sw", "report": "FAO says supply tightening."})
    assert r.status_code == 200 and r.json()["mode"] == "template" and r.json()["requires_human_review"] is True
    assert client.post("/api/v1/advisor/advice", headers=h, json={"crop": "maize", "language": "xx"}).status_code == 400
    assert client.post("/api/v1/advisor/advice", headers=h, json={"crop": "diamonds"}).status_code == 404
    prices.upsert_prices(db, synthetic.synthetic_rows([get_hub("accra")]))
    r = client.post("/api/v1/advisor/advice", headers=h, json={"crop": "maize", "language": "en", "hub_id": "accra"})
    assert r.status_code == 200 and "Prices for maize" in r.json()["summary"]


# ---------------- logistics
PLAN = {"depot": {"lat": -1.2921, "lon": 36.8219}, "mode": "delivery",
        "stops": [{"id": "a", "lat": -1.30, "lon": 36.85, "load_kg": 100, "max_transit_min": 120},
                  {"id": "b", "lat": -1.25, "lon": 36.80, "load_kg": 150},
                  {"id": "c", "lat": -1.33, "lon": 36.90, "load_kg": 80, "window_start_min": 0, "window_end_min": 200}],
        "vehicles": [{"id": "v1", "capacity_kg": 400}], "carbon_tradeoff": [0, 10]}


def test_logistics_plan(client):
    h = register(client, "b@x.t", "buyer")
    assert client.post("/api/v1/logistics/plan", json=PLAN).status_code == 401
    r = client.post("/api/v1/logistics/plan", headers=h, json=PLAN)
    assert r.status_code == 200
    body = r.json()
    assert sorted(s["stop_id"] for rt in body["routes"] for s in rt["stops"]) == ["a", "b", "c"]
    assert len(body["carbon_tradeoff"]) == 2 and any("straight-line" in n for n in body["notes"])
    too_big = {**PLAN, "stops": [{**PLAN["stops"][0], "load_kg": 5000}]}
    assert client.post("/api/v1/logistics/plan", headers=h, json=too_big).status_code == 422
    assert client.post("/api/v1/logistics/plan", headers=h, json={**PLAN, "road_provider": "osrm"}).status_code == 400
    assert client.post("/api/v1/logistics/plan", headers=h, json={**PLAN, "stops": []}).status_code == 422


# ---------------- digital twin
def test_twin_full_flow_and_permissions(client):
    farmer = register(client, "f@x.t", "farmer")
    other = register(client, "f2@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    assert client.post("/api/v1/twin/batches", headers=buyer, json={}).status_code == 403
    code = client.post("/api/v1/twin/batches", headers=farmer, json={
        "crop": "tomato", "origin_district": "Gazipur", "quantity_kg": 300}).json()["batch_code"]
    dev = client.post(f"/api/v1/twin/batches/{code}/devices", headers=farmer, params={"label": "crate"}).json()
    assert client.post(f"/api/v1/twin/batches/{code}/devices", headers=other).status_code == 403
    base = datetime.utcnow() - timedelta(hours=3)
    for i, temp in enumerate([11, 12, 18]):
        ts = base + timedelta(minutes=20 * i)
        sig = T.sign_reading(dev["hmac_key"], dev["device_id"], T._iso(ts), temp, 90, "rh")
        r = client.post("/api/v1/twin/readings", json={"device_id": dev["device_id"], "recorded_at": ts.isoformat(),
                                                       "temperature_c": temp, "moisture_pct": 90, "signature": sig})
        assert r.status_code == 200, r.text
    assert client.post("/api/v1/twin/readings", json={"device_id": dev["device_id"], "recorded_at": base.isoformat(),
                       "temperature_c": 1, "moisture_pct": 90, "signature": "bad"}).status_code == 401
    assert client.post(f"/api/v1/twin/batches/{code}/seal", headers=other).status_code == 403
    seal = client.post(f"/api/v1/twin/batches/{code}/seal", headers=farmer).json()
    assert seal["sealed"] and seal["summary"]["status"] == "excursion"
    assert client.post(f"/api/v1/twin/batches/{code}/events", headers=farmer, json={"event_type": "dispatched", "data": {"to": "Dhaka"}}).status_code == 200
    assert client.post(f"/api/v1/twin/batches/{code}/events", headers=buyer, json={"event_type": "received"}).status_code == 403
    pub = client.get(f"/api/v1/twin/public/{code}")                    # consumers need no login
    assert pub.status_code == 200 and pub.json()["integrity"]["chain_valid"] and len(pub.json()["timeline"]) == 3
    assert client.get(f"/api/v1/twin/batches/{code}/verify").json()["valid"]
    assert client.get("/api/v1/twin/public/FM-DOESNOTEXIST").status_code == 404
    assert client.post(f"/api/v1/twin/batches/{code}/anchor", headers=farmer).json()["external"] is False


def test_buyer_of_linked_order_can_record_receipt(client):
    farmer = register(client, "f@x.t", "farmer"); buyer = register(client, "b@x.t", "buyer")
    pid = client.post("/api/v1/products", headers=farmer, json={"name": "Tomato", "quantity": 100, "unit": "kg",
                      "price_per_unit": 30, "district": "Gazipur"}).json()["id"]
    oid = client.post("/api/v1/orders", headers=buyer, json={"product_id": pid, "quantity": 10}).json()["order_id"]
    code = client.post("/api/v1/twin/batches", headers=farmer, json={"crop": "tomato", "origin_district": "Gazipur",
                       "quantity_kg": 10, "order_id": oid}).json()["batch_code"]
    ok = client.post(f"/api/v1/twin/batches/{code}/events", headers=buyer, json={"event_type": "received", "data": {"note": "ok"}})
    assert ok.status_code == 200
    assert client.post(f"/api/v1/twin/batches/{code}/events", headers=buyer, json={"event_type": "harvested"}).status_code == 403
    stranger = register(client, "b2@x.t", "buyer")
    assert client.post(f"/api/v1/twin/batches/{code}/events", headers=stranger, json={"event_type": "received"}).status_code == 403
