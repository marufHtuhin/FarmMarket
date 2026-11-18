"""Phase 7-8 audit tests (2026-11-17): gaps found by inspecting the AI /
external-data, logistics and Digital Twin code, plus regression tests for
the bugs fixed in this audit. All external calls are mocked except where
noted; live-service behaviour is reported in docs/audit/p7-8-section.md.
"""
import io
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from PIL import Image

from conftest import fruit_image, register
from app import models
from app.services import gemini_assistant as GA
from app.services import rag
from app.services import sklearn_forecast as SK
from app.services import twin as T
from app.services import vision as V
from app.services.datasources import openmeteo, openweather, prices, worldbank
from app.services.datasources import sync as datasync
from app.services.matching import calculate_match


# ------------------------------------------------------------------ matching
def demand(**over):
    v = dict(product_name="Tomato", unit="kg", required_quantity=500,
             target_price=40, district="Gazipur", required_date=None)
    v.update(over)
    return SimpleNamespace(**v)


def product(**over):
    v = dict(name="Tomato", unit="kg", quantity=600, price_per_unit=35,
             district="Gazipur", status="available", available_until=None)
    v.update(over)
    return SimpleNamespace(**v)


def test_match_zero_price_does_not_crash():
    """A zero/negative price (possible: the DB column has no CHECK, only the
    API schema enforces > 0) must be 'no match', not a ZeroDivisionError 500."""
    assert calculate_match(demand(), product(price_per_unit=0)) is None
    assert calculate_match(demand(), product(price_per_unit=-5)) is None
    assert calculate_match(demand(target_price=0), product()) is None


def test_match_missing_names_or_units_do_not_crash():
    assert calculate_match(demand(product_name=None), product()) is None
    assert calculate_match(demand(), product(name=None)) is None
    assert calculate_match(demand(unit=None), product()) is None
    assert calculate_match(demand(), product(district=None)) is not None  # different district


def test_match_time_score_grades_availability_slack():
    d = date(2026, 11, 20)
    no_dates = calculate_match(demand(), product())
    assert no_dates["time_score"] == 100.0
    same_day = calculate_match(demand(required_date=d), product(available_until=d))
    assert same_day["time_score"] == 50.0
    two_weeks = calculate_match(demand(required_date=d),
                                product(available_until=d + timedelta(days=14)))
    assert two_weeks["time_score"] == 100.0
    one_week = calculate_match(demand(required_date=d),
                               product(available_until=d + timedelta(days=7)))
    assert one_week["time_score"] == 75.0
    assert same_day["score"] < one_week["score"] < two_weeks["score"]


def test_match_reasons_describe_actual_outcomes():
    full = calculate_match(demand(), product())
    assert "Full quantity available" in full["reasons"]
    assert "Price is within buyer budget" in full["reasons"]
    partial = calculate_match(demand(), product(quantity=100, price_per_unit=80,
                                                district="Dhaka"))
    assert any("Partial quantity" in r for r in partial["reasons"])
    assert any("above buyer budget" in r for r in partial["reasons"])
    assert "Different district" in partial["reasons"]
    assert partial["score"] < full["score"]


def test_match_ranking_prefers_cheaper_closer_fuller_supply():
    """Two farmers, one buyer: the better offer must rank first."""
    d = demand()
    near_cheap = calculate_match(d, product(district="Gazipur", price_per_unit=30, quantity=600))
    far_pricey = calculate_match(d, product(district="Sylhet", price_per_unit=45, quantity=200))
    assert near_cheap["score"] > far_pricey["score"]
    assert near_cheap["score"] == 100.0  # everything maxed


# ------------------------------------------------------- external adapters
def _mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_worldbank_skips_malformed_entries():
    def handler(req):
        return httpx.Response(200, json=[{"page": 1}, [
            {"date": "2024", "value": 10.5},
            {"date": "2023", "value": None},          # null: dropped
            {"date": "2022"},                          # missing value: dropped
            {"date": "not-a-year", "value": 3.0},      # bad date: dropped
            {"date": "2021", "value": "abc"},          # bad value: dropped
            "junk",                                    # not a dict: dropped
            {"date": "2020", "value": 5.0},
        ]])

    out = worldbank.fetch_indicator("BGD", "FP.CPI.TOTL.ZG", 2020, 2024,
                                    _mock_client(handler))
    assert out == [(2020, 5.0), (2024, 10.5)]


def test_worldbank_timeout_covers_measured_latency():
    """Live latency measured 2026-11-17: ~12s (population) / ~21s (inflation)
    from this network. Timeouts below that fail spuriously."""
    assert worldbank.TIMEOUT_S >= 30
    assert datasync.SYNC_TIMEOUT_S >= 30


def test_openweather_malformed_body_degrades_to_none_not_500():
    def bad_json(req):
        return httpx.Response(200, content=b"this is not json")

    assert openweather.fetch_daily_outlook(23.8, 90.4, "k", _mock_client(bad_json)) is None

    def missing_keys(req):
        return httpx.Response(200, json={"list": [
            {"dt": 1763000000},                       # no "main": skipped
            {"dt": 1763000000, "main": {"temp": 28.0}, "rain": {"3h": 1.5}, "pop": 0.4},
            {"main": {"temp": 99.0}},                 # no "dt": skipped
        ]})

    out = openweather.fetch_daily_outlook(23.8, 90.4, "k", _mock_client(missing_keys))
    assert out is not None and len(out) == 1
    assert out[0]["temp_min_c"] == 28.0 and out[0]["rain_mm"] == 1.5
    assert openweather.fetch_daily_outlook(23.8, 90.4, "k",
                                           _mock_client(lambda r: httpx.Response(
                                               200, json={"no_list": True}))) is None


def test_openmeteo_non_json_body_degrades_to_none():
    def bad(req):
        return httpx.Response(200, content=b"not json at all")

    assert openmeteo.fetch_weather(23.8, 90.4, _mock_client(bad)) is None


# ------------------------------------------------------------------ FAOSTAT
FAOSTAT_CSV = """Area,Item,Element,Months,Year,Unit,Value
Bangladesh,Tomatoes,Producer Price (LCU/tonne),January,2023,LCU,12000
Bangladesh,Tomatoes,Producer Price (LCU/tonne),February,2023,LCU,9000
Bangladesh,Tomatoes,Producer Price (LCU/tonne),Annual value,2023,LCU,10000
Bangladesh,Tomatoes,Producer Price (LCU/kg),March,2023,LCU,12
Bangladesh,"Onions, dry",Producer Price (LCU/tonne),January,2023,LCU,-5
Bangladesh,Potatoes,Producer Price (LCU/tonne),January,2023,LCU,20000
Nowhere,Tomatoes,Producer Price (LCU/tonne),January,2023,LCU,12000
"""


def test_faostat_parser_monthly_tonne_conversion_and_skips():
    from app.config import get_hub

    rows = prices.read_faostat_producer_prices(io.StringIO(FAOSTAT_CSV), [get_hub("dhaka")])
    by_key = {(r["crop"], r["observed_on"].month): r for r in rows}
    # Only monthly LCU/tonne rows survive, converted to per-kg, in hub currency.
    assert set(by_key) == {("tomato", 1), ("tomato", 2), ("potato", 1)}
    assert by_key[("tomato", 1)]["price"] == 12.0          # 12000 LCU/tonne -> 12/kg
    assert by_key[("tomato", 1)]["currency"] == "BDT"
    assert by_key[("tomato", 1)]["unit"] == "kg"
    assert by_key[("tomato", 1)]["is_synthetic"] is False
    assert "national, Bangladesh" in by_key[("tomato", 1)]["source"]
    # Annual value, LCU/kg basis, negative price and unknown area all skipped.


def test_faostat_upsert_is_idempotent(db):
    from app.config import get_hub

    rows = prices.read_faostat_producer_prices(io.StringIO(FAOSTAT_CSV), [get_hub("dhaka")])
    first = prices.upsert_prices(db, rows)
    assert first == {"inserted": 3, "skipped": 0}
    second = prices.upsert_prices(db, rows)
    assert second == {"inserted": 0, "skipped": 3}
    assert db.query(models.PriceObservation).count() == 3


# ------------------------------------------------- forecasting on real data
def test_sklearn_forecast_prefers_real_series(db):
    """40 weekly REAL rows (is_synthetic=False) drive the forecaster with
    real_only=True and no SYNTHETIC warning — forecasts are not demo-bound."""
    from app.config import get_hub
    import pandas as pd

    hub = get_hub("dhaka")
    dates = pd.date_range(end="2026-11-01", periods=40, freq="W")
    rng = np.random.default_rng(3)
    rows = [dict(hub_id=hub.id, crop="tomato", observed_on=d.date(),
                 price=round(float(60 + 5 * np.sin(i / 3) + rng.normal(0, 1)), 2),
                 currency="BDT", unit="kg", source="manual-entry", is_synthetic=False)
            for i, d in enumerate(dates)]
    prices.upsert_prices(db, rows)
    r = SK.forecast_sklearn(db, hub, "tomato", horizon=4)
    assert r["series"]["real_only"] is True
    assert r["series"]["synthetic_share"] == 0.0
    assert r["series"]["sources"] == ["manual-entry"]
    assert not any("SYNTHETIC" in w for w in r["warnings"])
    assert len(r["forecast"]) == 4


# ------------------------------------------------------------------- vision
def _png(w, h, color=(200, 40, 35)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def test_vision_varied_dimensions_and_tiny_images():
    for data in (_png(1, 1), _png(1000, 10), _png(10, 1000), _png(640, 480)):
        feats = V.extract_features(V.load_image(data))
        assert feats.shape[0] > 0 and np.isfinite(feats).all()


def test_vision_truncated_and_garbage_images_rejected():
    good = fruit_image("ripe", np.random.default_rng(0))
    with pytest.raises(V.BadImageError):
        V.load_image(good[: len(good) // 2])          # truncated PNG
    with pytest.raises(V.BadImageError):
        V.load_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # header only
    with pytest.raises(V.BadImageError):
        V.load_image(b"")                              # empty file


# ---------------------------------------------------------------- assistant
def test_assistant_bengali_template_reply_is_labelled(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    out = GA.generate_reply("টমেটো কিভাবে সংরক্ষণ করব?", "bn",
                            rag.retrieve("টমেটো সংরক্ষণ"), [])
    assert out["mode"] == "template"
    assert "টেমপ্লেট" in out["reply"]  # labelled as template, in Bangla


def test_assistant_irrelevant_question_invents_nothing(client, db, monkeypatch):
    """An off-topic question gets the honest 'no notes' reply — no invented
    agricultural advice, no prices, no fake confidence."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    GA.reset_limiter()
    farmer = register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/assistant/chat", headers=farmer,
                    json={"message": "What is the capital of France?", "language": "en"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "template"
    assert body["sources"] == []
    assert "could not find notes" in body["reply"]
    assert "42" not in body["reply"]


def test_assistant_status_without_key_is_honest(client, db, monkeypatch):
    """No key configured: status says so, test probe fails fast with a clear
    message, and neither endpoint ever returns key material."""
    from app.security import create_access_token, hash_password

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    GA.LAST_GEMINI_ERROR.clear()  # no leaked failure from an earlier test file
    admin = models.User(email="a@x.t", name="A", role="admin", district="Dhaka",
                        password_hash=hash_password("Passw0rd!"))
    db.add(admin)
    db.commit()
    h = {"Authorization": "Bearer " + create_access_token(admin.id)}
    s = client.get("/api/v1/assistant/status", headers=h)
    assert s.status_code == 200
    assert s.json() == {"key_configured": False, "model": GA.DEFAULT_MODEL,
                        "last_gemini_error": None}
    t = client.post("/api/v1/assistant/test", headers=h)
    assert t.status_code == 200
    assert t.json() == {"ok": False, "mode": "template", "latency_ms": 0,
                        "error": "GEMINI_API_KEY is not set",
                        "model": None, "connect_ms": None, "ttfb_ms": None}


# ---------------------------------------------------------------- logistics
def _dhaka_payload(**over):
    p = {"depot": {"lat": 23.8103, "lon": 90.4125},
         "stops": [{"id": "s1", "lat": 23.82, "lon": 90.42, "load_kg": 100}],
         "vehicles": [{"id": "v1", "capacity_kg": 500}]}
    p.update(over)
    return p


def test_plan_haversine_labels_straight_line(client, db):
    h = register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/logistics/plan", json=_dhaka_payload(), headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["road_provider"] == "haversine"
    assert any("straight-line" in n for n in body["notes"])
    assert body["totals"]["distance_km"] > 0


def test_optimize_osrm_failure_falls_back_to_haversine_labelled(client, db, monkeypatch):
    """OSRM requested but unreachable (closed port): /optimize must fall back
    to the haversine estimate AND say so — never present it as road data."""
    from app.services import ortools_routing as OR

    if not OR.ortools_available():
        pytest.skip("ortools not installed")
    monkeypatch.setenv("OSRM_BASE_URL", "http://127.0.0.1:9")
    h = register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/logistics/optimize",
                    json=_dhaka_payload(road_provider="osrm"), headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["distance_basis"] == "haversine_estimate"
    assert any("OSRM failed" in n and "haversine" in n for n in body["notes"])
    assert body["total_distance_km"] > 0


def test_plan_osrm_unconfigured_is_400_not_silent_fallback(client, db, monkeypatch):
    monkeypatch.delenv("OSRM_BASE_URL", raising=False)
    h = register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/logistics/plan",
                    json=_dhaka_payload(road_provider="osrm"), headers=h)
    assert r.status_code == 400
    assert "not configured" in r.json()["detail"]


# --------------------------------------------------------------- digital twin
def _farmer_batch(db):
    farmer = models.User(name="F", email="f@x.t", password_hash="x", role="farmer")
    db.add(farmer)
    db.commit()
    return farmer, T.create_batch(db, farmer.id, "tomato", "Gazipur", 500,
                                  datetime(2026, 11, 1, 6))


def test_twin_batch_codes_are_unique(db):
    farmer, _ = _farmer_batch(db)
    codes = {T.create_batch(db, farmer.id, "tomato", "Gazipur", 10).batch_code
             for _ in range(50)}
    assert len(codes) == 50
    assert all(c.startswith("FM-") for c in codes)


def test_twin_public_timeline_temp_is_summary_object(db):
    """Contract the frontend relies on: a sealed cold_chain_check timeline
    entry carries temp_c as the {min, max, avg} summary object, not a number.
    (BatchView used to expect a number, so the sensor chart never rendered.)"""
    farmer, batch = _farmer_batch(db)
    dev = T.register_device(db, batch, "truck")
    base = datetime(2026, 11, 2, 12, 0)
    for i, temp in enumerate((12.0, 13.0, 14.0)):
        ts = base + timedelta(minutes=30 * i)
        sig = T.sign_reading(dev["hmac_key"], dev["device_id"], T._iso(ts), temp, 90.0, "rh")
        T.ingest_reading(db, dev["device_id"], ts, temp, 90.0, "rh", sig,
                         now=base + timedelta(hours=10))
    assert T.seal_readings(db, batch) is not None
    pv = T.public_view(db, batch)
    seal = next(e for e in pv["timeline"] if e["event"] == "cold_chain_check")
    assert isinstance(seal["temp_c"], dict)
    assert seal["temp_c"] == {"min": 12.0, "max": 14.0, "avg": 13.0}
    assert pv["cold_chain"]["temp_c"] == {"min": 12.0, "max": 14.0, "avg": 13.0}


def test_twin_tamper_breaks_chain_end_to_end(db):
    """Full tamper test: a valid chain, then one historical event edited in
    the DB, then verification must report invalid with a problem entry."""
    farmer, batch = _farmer_batch(db)
    who = SimpleNamespace(id=farmer.id, role="farmer")
    T.add_event(db, batch, who, "packed", {"crates": 10})
    T.add_event(db, batch, who, "dispatched", {"truck": "DHK-1"})
    assert T.verify_chain(db, batch)["valid"] is True
    blk = db.query(models.LedgerBlock).filter_by(event_type="packed").one()
    blk.payload = '{"crates": 999, "actor_role": "farmer"}'
    db.commit()
    v = T.verify_chain(db, batch)
    assert v["valid"] is False
    assert any(p["block"] == 1 for p in v["problems"])
