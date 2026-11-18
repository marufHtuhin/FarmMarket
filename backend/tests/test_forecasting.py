import importlib.util
import io
import numpy as np
import pandas as pd
import pytest

from app import models
from app.config import get_hub, active_hubs, hub_profile
from app.services import forecasting as F
from app.services.datasources import prices, synthetic

needs_prophet = pytest.mark.skipif(
    not importlib.util.find_spec("prophet"), reason="prophet not installed")


def _load_synth(db, hubs=None, **kw):
    prices.upsert_prices(db, synthetic.synthetic_rows(hubs, **kw))


@needs_prophet
def test_forecast_pair_shape_and_provenance(db):
    _load_synth(db, [get_hub("nairobi")])
    r = F.forecast_pair(db, get_hub("nairobi"), "maize", horizon=6)
    assert len(r["forecast"]) == 6 and r["frequency"] == "W"
    assert all(p["lower"] <= p["yhat"] <= p["upper"] and p["yhat"] > 0 for p in r["forecast"])
    assert r["series"]["synthetic_share"] == 1.0
    assert any("SYNTHETIC" in w for w in r["warnings"])
    assert r["validation"]["folds"] >= 1 and "skill_vs_baseline" in r["validation"]


def test_insufficient_history_is_refused(db):
    rows = synthetic.synthetic_rows([get_hub("lagos")], years=1)[:20]
    prices.upsert_prices(db, [r for r in rows if r["crop"] == rows[0]["crop"]])
    with pytest.raises(F.InsufficientDataError):
        F.forecast_pair(db, get_hub("lagos"), rows[0]["crop"], 4)
    with pytest.raises(F.InsufficientDataError):
        F.forecast_pair(db, get_hub("accra"), "maize", 4)  # nothing stored at all


def test_backtest_flags_forecast_that_loses_to_naive(db, monkeypatch):
    _load_synth(db, [get_hub("kampala")])
    df, info = F.load_series(db, "kampala", "maize")
    monkeypatch.setattr(F, "_fit", lambda d, f: None)
    monkeypatch.setattr(F, "_predict", lambda m, h, f: pd.DataFrame(
        {"ds": pd.date_range("2030-01-01", periods=h, freq="W"), "yhat": [1e6] * h, "lower": [0] * h, "upper": [2e6] * h}))
    bt = F.backtest(df, info.freq, 8)
    assert bt["reliable"] is False and bt["skill_vs_baseline"] < 0


@needs_prophet
def test_snapshot_cache_invalidates_when_data_changes(db):
    _load_synth(db, [get_hub("accra")])
    a = F.get_or_compute(db, "accra", "onion", 4)
    assert db.query(models.ForecastSnapshot).count() == 1
    assert F.get_or_compute(db, "accra", "onion", 4)["generated_at"] == a["generated_at"]
    db.add(models.PriceObservation(hub_id="accra", crop="onion", observed_on=pd.Timestamp("2027-01-04").date(),
                                   price=99.0, source="manual"))
    db.commit()
    snap = db.query(models.ForecastSnapshot).filter_by(crop="onion").one()
    assert snap.fingerprint != F.fingerprint(db, "accra", "onion")  # stale -> will be recomputed


def test_csv_import_skips_bad_rows():
    csv = io.StringIO("hub_id,crop,date,price,unit\nnairobi,maize,2026-01-05,52.5,kg\n"
                      "atlantis,maize,2026-01-05,50,kg\nnairobi,kryptonite,2026-01-05,50,kg\n"
                      "nairobi,maize,2026-01-12,-3,kg\nnairobi,maize,notadate,40,kg\n")
    rows = prices.read_price_csv(csv)
    assert len(rows) == 1 and rows[0]["price"] == 52.5 and rows[0]["currency"] == "KES"
    with pytest.raises(ValueError):
        prices.read_price_csv(io.StringIO("a,b\n1,2\n"))


def test_faostat_parser_converts_tonne_to_kg_and_is_national():
    csv = io.StringIO(
        "Area,Item,Element,Months,Year,Unit,Value\n"
        "Kenya,Maize (corn),Producer Price (LCU/tonne),January,2020,LCU,30000\n"
        "Kenya,Maize (corn),Producer Price (LCU/tonne),Annual value,2020,LCU,31000\n"
        "Kenya,Tomatoes,Producer Price (LCU/tonne),March,2020,LCU,45000\n"
        "Kenya,Maize (corn),Production,January,2020,tonnes,999\n"
        "Ghana,Maize (corn),Producer Price (LCU/tonne),January,2020,LCU,2000\n")
    rows = prices.read_faostat_producer_prices(csv, [get_hub("nairobi")])
    assert {(r["crop"], r["price"]) for r in rows} == {("maize", 30.0), ("tomato", 45.0)}
    assert "national" in rows[0]["source"]


def test_upsert_is_idempotent(db):
    rows = synthetic.synthetic_rows([get_hub("nairobi")], years=1)
    assert prices.upsert_prices(db, rows)["inserted"] == len(rows)
    assert prices.upsert_prices(db, rows)["inserted"] == 0


def test_five_bangladesh_hubs_by_default(monkeypatch):
    monkeypatch.delenv("HUB_PROFILE", raising=False)
    assert hub_profile() == "bangladesh"
    assert [h.id for h in active_hubs()] == ["dhaka", "chattogram", "rajshahi", "khulna", "sylhet"]


def test_subsaharan_hubs_selectable_via_env(monkeypatch):
    monkeypatch.setenv("HUB_PROFILE", "sub_saharan")
    assert hub_profile() == "sub_saharan"
    assert [h.id for h in active_hubs()] == ["nairobi", "kampala", "dar_es_salaam", "lagos", "accra"]
