"""Tests for the scikit-learn RandomForest forecaster (no Prophet needed)."""
import pytest

from app import models
from app.config import active_hubs, get_hub
from app.services import forecasting as F
from app.services import sklearn_forecast as SK
from app.services.datasources import prices, synthetic


def _load_synth(db, hubs=None, **kw):
    prices.upsert_prices(db, synthetic.synthetic_rows(hubs, **kw))


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
