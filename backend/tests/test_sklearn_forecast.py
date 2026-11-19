"""Tests for the scikit-learn RandomForest forecaster (no Prophet needed)."""
import pytest

from app import models
from app.config import active_hubs, get_hub
from app.routers import forecast as forecast_router
from app.services import forecasting as F
from app.services import sklearn_forecast as SK
from app.services.datasources import prices, synthetic


def _load_synth(db, hubs=None, **kw):
    prices.upsert_prices(db, synthetic.synthetic_rows(hubs, **kw))


@pytest.fixture(autouse=True)
def _fresh_forecast_cache():
    # The endpoint cache is module-level and outlives each test's temp DB;
    # clear it before and after every test (same pattern as the weather
    # cache in test_weather.py).
    forecast_router.clear_forecast_cache()
    yield
    forecast_router.clear_forecast_cache()


def test_forecast_sklearn_shape_and_provenance(db):
    _load_synth(db, [get_hub("dhaka")], years=1)
    r = SK.forecast_sklearn(db, get_hub("dhaka"), "tomato", horizon=6)
    assert r["model"] == "sklearn-random-forest"
    assert r["frequency"] == "W" and r["horizon"] == 6
    assert r["hub"]["id"] == "dhaka" and r["crop"] == "tomato" and r["unit"] == "kg"
    assert len(r["forecast"]) == 6
    assert all(p["lower"] <= p["yhat"] <= p["upper"] and p["yhat"] > 0 for p in r["forecast"])
    assert r["series"]["synthetic_share"] == 1.0
    assert r["series"]["points"] >= 30
    assert any("SYNTHETIC" in w for w in r["warnings"])
    assert any("scikit-learn" in w for w in r["warnings"])
    assert r["signal"]["direction"] in ("up", "down", "flat")
    assert "expected_change_pct" in r["signal"]
    assert r["validation"]["folds"] == 1
    assert "skill_vs_baseline" in r["validation"]
    assert r["reliable"] == r["validation"]["reliable"]
    # sklearn results must NOT be cached in ForecastSnapshot (shared with Prophet)
    assert db.query(models.ForecastSnapshot).count() == 0


def test_forecast_sklearn_insufficient_history_is_refused(db):
    rows = synthetic.synthetic_rows([get_hub("dhaka")], years=1)
    tomato = [r for r in rows if r["crop"] == "tomato"][:10]
    prices.upsert_prices(db, tomato)
    with pytest.raises(F.InsufficientDataError):
        SK.forecast_sklearn(db, get_hub("dhaka"), "tomato", 4)


def test_forecast_sklearn_no_data_is_refused(db):
    with pytest.raises(F.InsufficientDataError):
        SK.forecast_sklearn(db, get_hub("dhaka"), "tomato", 4)


def test_sklearn_endpoint(db, client):
    _load_synth(db, [get_hub("dhaka")], years=1)
    r = client.get("/api/v1/forecast/sklearn", params={"hub": "dhaka", "crop": "tomato", "horizon": 4})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == "sklearn-random-forest"
    assert len(body["forecast"]) == 4
    assert all(p["lower"] <= p["yhat"] <= p["upper"] and p["yhat"] > 0 for p in body["forecast"])
    assert client.get("/api/v1/forecast/sklearn",
                      params={"hub": "atlantis", "crop": "tomato"}).status_code == 404
    assert client.get("/api/v1/forecast/sklearn",
                      params={"hub": "dhaka", "crop": "kryptonite"}).status_code == 404


def test_sklearn_endpoint_insufficient_data_is_422(db, client):
    r = client.get("/api/v1/forecast/sklearn", params={"hub": "dhaka", "crop": "tomato"})
    assert r.status_code == 422


def test_hubs_endpoint_returns_coordinates(client):
    r = client.get("/api/v1/forecast/hubs")
    assert r.status_code == 200, r.text
    hubs = r.json()["hubs"]
    assert [h["id"] for h in hubs] == [h.id for h in active_hubs()]
    for h in hubs:
        assert isinstance(h["lat"], float) and isinstance(h["lon"], float)
        assert -90 <= h["lat"] <= 90 and -180 <= h["lon"] <= 180


# --- 1-hour endpoint cache + full history window (19 Nov 2026 live QA) ---

def test_sklearn_endpoint_caches_per_hub_crop_horizon(client, db, monkeypatch):
    """A repeat request for the same hub x crop x horizon is served from
    the in-memory cache (no second 30-60s RandomForest fit); a different
    horizon is a different key; clearing the cache forces a refit."""
    _load_synth(db, [get_hub("dhaka")], years=1)
    calls: list[tuple] = []
    orig = SK.forecast_sklearn

    def counting(db_, hub, crop, horizon=8):
        calls.append((hub.id, crop, horizon))
        return orig(db_, hub, crop, horizon)

    monkeypatch.setattr("app.routers.forecast.SK.forecast_sklearn", counting)
    params = {"hub": "dhaka", "crop": "tomato", "horizon": 4}
    r1 = client.get("/api/v1/forecast/sklearn", params=params)
    r2 = client.get("/api/v1/forecast/sklearn", params=params)
    assert r1.status_code == r2.status_code == 200, r1.text
    assert r1.json() == r2.json()  # byte-identical: served from cache
    assert len(calls) == 1  # the second call did not refit
    r3 = client.get("/api/v1/forecast/sklearn",
                    params={**params, "horizon": 6})
    assert r3.status_code == 200 and len(calls) == 2
    forecast_router.clear_forecast_cache()
    r4 = client.get("/api/v1/forecast/sklearn", params=params)
    assert r4.status_code == 200 and len(calls) == 3


def test_sklearn_history_matches_trend_end_date(client, db):
    """The forecast chart's history ends on the same date as the trend
    chart's series (live QA: the forecast chart appeared to end ~Aug 2026
    while the trend chart showed history through 15 Nov 2026), and covers
    the same full window — not a 52-point tail."""
    _load_synth(db, [get_hub("dhaka")], years=2)
    fc = client.get("/api/v1/forecast/sklearn",
                    params={"hub": "dhaka", "crop": "tomato",
                            "horizon": 8}).json()
    trend = client.get("/api/v1/prices/history",
                       params={"hub": "dhaka", "crop": "tomato"}).json()
    assert fc["history"], "forecast history must not be empty"
    assert fc["history"][-1]["ds"] == trend["points"][-1]["observed_on"]
    assert fc["history"][-1]["ds"] == fc["series"]["end"]
    assert len(fc["history"]) == trend["count"] == fc["series"]["points"]
