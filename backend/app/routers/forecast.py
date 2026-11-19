from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
import json
import time

from .. import models
from ..config import CROPS, active_hubs, get_hub, hub_profile
from ..database import get_db
from ..services import forecasting as F
from ..services import sklearn_forecast as SK
from ..services.datasources import openmeteo, worldbank
import httpx
from datetime import date

router = APIRouter(prefix="/api/v1/forecast", tags=["forecast"])

# In-memory cache for the sklearn forecast: fitting a RandomForest takes
# 30-60s per hub x crop, and the /prices page refits on every load. Weekly
# price data changes at most once a day, so a 1-hour TTL is ample; repeat
# loads are instant. Keyed by (hub, crop, horizon). Errors are never
# cached (a 404/422 must not stick). Same shape as the weather cache in
# routers/weather.py. This is separate from ForecastSnapshot, which stays
# Prophet-only by design (see sklearn_forecast's module docstring).
FORECAST_CACHE_TTL_S = 3600  # 1 hour
_forecast_cache: dict[tuple[str, str, int], tuple[float, dict]] = {}


def clear_forecast_cache() -> None:
    """Drop all cached sklearn forecasts (used by tests)."""
    _forecast_cache.clear()


@router.get("/hubs")
def hubs(db: Session = Depends(get_db)):
    counts = dict(((h, c), n) for h, c, n in
                  db.query(models.PriceObservation.hub_id, models.PriceObservation.crop,
                           func.count(models.PriceObservation.id)).group_by(
                      models.PriceObservation.hub_id, models.PriceObservation.crop))
    return {"profile": hub_profile(),
            "hubs": [{"id": h.id, "name": h.name, "country": h.country, "currency": h.currency,
                      "lat": h.lat, "lon": h.lon,
                      "observations": {c: counts.get((h.id, c), 0) for c in CROPS}} for h in active_hubs()],
            "crops": [{"id": c.id, "name": c.name} for c in CROPS.values()]}


@router.get("/overview")
def overview(horizon: int = Query(8, ge=1, le=26), db: Session = Depends(get_db)):
    """Cached forecasts only (cheap). Refresh them with scripts/fit_forecasts.py."""
    out = []
    for s in db.query(models.ForecastSnapshot).filter_by(horizon=horizon).all():
        p = json.loads(s.payload)
        out.append({"hub": s.hub_id, "crop": s.crop, "signal": p["signal"], "reliable": p["reliable"],
                    "synthetic_share": p["series"]["synthetic_share"], "generated_at": p["generated_at"]})
    return {"horizon": horizon, "forecasts": out}


@router.get("/sklearn")
def forecast_sklearn(hub: str, crop: str, horizon: int = Query(8, ge=1, le=26),
                     db: Session = Depends(get_db)):
    """scikit-learn RandomForest forecast. Works without Prophet installed.
    Results are cached in memory for 1 hour per (hub, crop, horizon) — the
    fit takes 30-60s, so uncached repeat loads spun the "Fitting model…"
    spinner every time (found in the 19 Nov 2026 live QA). First load for
    a pair still fits the model. Never cached in ForecastSnapshot (that
    store is Prophet-only by design)."""
    h = get_hub(hub)
    if h is None:
        raise HTTPException(404, f"Unknown hub '{hub}'")
    crop = crop.lower()
    if crop not in CROPS:
        raise HTTPException(404, f"Unknown crop '{crop}'")
    key = (h.id, crop, horizon)
    hit = _forecast_cache.get(key)
    if hit and time.monotonic() - hit[0] < FORECAST_CACHE_TTL_S:
        return hit[1]
    try:
        result = SK.forecast_sklearn(db, h, crop, horizon)
    except F.InsufficientDataError as e:
        raise HTTPException(422, f"Cannot forecast: {e}")
    _forecast_cache[key] = (time.monotonic(), result)
    return result


@router.get("")
def forecast(hub: str, crop: str, horizon: int = Query(8, ge=1, le=26), refresh: bool = False,
             db: Session = Depends(get_db)):
    if get_hub(hub) is None:
        raise HTTPException(404, f"Unknown hub '{hub}'")
    if crop.lower() not in CROPS:
        raise HTTPException(404, f"Unknown crop '{crop}'")
    try:
        return F.get_or_compute(db, hub, crop.lower(), horizon, force=refresh)
    except F.InsufficientDataError as e:
        raise HTTPException(422, f"Cannot forecast: {e}")
    except F.ProphetNotAvailableError:
        raise HTTPException(503, "Prophet is not installed on this server; "
                                 "install backend/requirements-prophet.txt or use "
                                 "/api/v1/forecast/sklearn")


@router.get("/context/{hub}")
def context(hub: str):
    """Macro stability (World Bank) and 8-day weather (Open-Meteo, no key) for a hub. Either may be unavailable."""
    h = get_hub(hub)
    if h is None:
        raise HTTPException(404, f"Unknown hub '{hub}'")
    try:
        macro = worldbank.stability_summary(h.iso3, date.today().year - 10, date.today().year)
    except httpx.HTTPError:
        macro = {"iso3": h.iso3, "available": False, "note": "World Bank API unreachable"}
    wx = openmeteo.fetch_daily_outlook(h.lat, h.lon)
    return {"hub": h.id, "macro": macro,
            "weather": wx if wx else {"available": False, "note": "Open-Meteo unreachable"}}
