"""Prophet-based multi-crop, multi-hub price forecasting with honest validation.

Design rules:
  * Fit on log(price) so forecasts stay positive and seasonality is multiplicative.
  * Every forecast is back-tested (rolling origin) against a naive baseline.
    Forecasts that do not beat the baseline are returned with reliable=False.
  * Too little history -> InsufficientDataError (never a made-up forecast).
"""
from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..config import CROPS, Hub, get_hub

logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
logging.getLogger("prophet").setLevel(logging.ERROR)

MIN_POINTS = {"W": 52, "MS": 24, "D": 180}
SEASON = {"W": 52, "MS": 12, "D": 365}
PANDAS_FREQ = {"W": "W", "MS": "MS", "D": "D"}
FLAT_BAND = 0.03  # +/-3 % vs recent level counts as "flat"


class InsufficientDataError(ValueError):
    pass


class ProphetNotAvailableError(RuntimeError):
    """Raised when the Prophet forecaster is requested but Prophet is not installed.

    Prophet is an optional dependency (see backend/requirements-prophet.txt);
    the scikit-learn forecaster works without it.
    """
    pass


@dataclass
class SeriesInfo:
    n_points: int
    start: str
    end: str
    freq: str
    synthetic_share: float
    sources: list[str]
    # True when the forecast trained on REAL observations only (no synthetic
    # rows). See load_series: real history is preferred once it is long
    # enough to meet the forecaster's minimum; otherwise the mixed series
    # (with its synthetic_share warning) is used.
    real_only: bool = False


def infer_freq(ds: pd.Series) -> str:
    gaps = ds.sort_values().diff().dropna().dt.days
    if gaps.empty:
        raise InsufficientDataError("Need at least two dated observations")
    med = float(gaps.median())
    if med <= 1.5:
        return "D"
    if med <= 10:
        return "W"
    return "MS"


def _regularise(raw: pd.DataFrame, min_points: int | None) -> tuple[pd.DataFrame, str]:
    """Resample one frame to a regular grid; raises InsufficientDataError when
    the series is too short or too gappy to forecast."""
    raw = raw[raw["y"] > 0]
    freq = infer_freq(raw["ds"])
    # Resample to a regular grid (mean within period); interpolate only short gaps.
    s = raw.set_index("ds")["y"].resample(PANDAS_FREQ[freq]).mean()
    n_missing = int(s.isna().sum())
    s = s.interpolate(limit=2).dropna()
    if n_missing > 0.2 * max(len(s), 1):
        raise InsufficientDataError("Series has too many gaps (>20%) to forecast reliably")
    df = s.reset_index().rename(columns={s.index.name or "ds": "ds"})
    df.columns = ["ds", "y"]
    required = MIN_POINTS[freq] if min_points is None else min_points
    if len(df) < required:
        raise InsufficientDataError(
            f"Need at least {required} {freq} observations; have {len(df)}")
    return df, freq


def load_series(db: Session, hub_id: str, crop: str,
                min_points: int | None = None) -> tuple[pd.DataFrame, SeriesInfo]:
    """Load and regularise a hub x crop price series.

    min_points overrides the Prophet minimum (MIN_POINTS[freq]) when given;
    the default None preserves the existing Prophet behaviour. The scikit-learn
    forecaster passes a smaller minimum (30).

    REAL data is preferred: when the non-synthetic (ingested/manual) rows
    alone form a series long enough to forecast, the synthetic demo rows are
    excluded (info.real_only=True, synthetic_share=0). Otherwise the full
    mixed series is used and the existing synthetic-data warning applies.
    In practice this means daily manual entries start driving the sklearn
    forecaster after ~30 days, and the Prophet forecaster after ~180 days
    (its daily minimum).
    """
    rows = (db.query(models.PriceObservation)
            .filter_by(hub_id=hub_id, crop=crop).order_by(models.PriceObservation.observed_on).all())
    if not rows:
        raise InsufficientDataError(f"No price history stored for {crop} at {hub_id}")
    raw = pd.DataFrame({"ds": [pd.Timestamp(r.observed_on) for r in rows], "y": [r.price for r in rows],
                        "synthetic": [bool(r.is_synthetic) for r in rows], "source": [r.source for r in rows]})
    raw = raw[raw["y"] > 0]
    real = raw[~raw["synthetic"]]
    used, real_only = raw, False
    if len(real) >= 2:
        try:
            df, freq = _regularise(real, min_points)
            used, real_only = real, True
        except InsufficientDataError:
            df, freq = _regularise(raw, min_points)
    else:
        df, freq = _regularise(raw, min_points)
    info = SeriesInfo(len(df), df["ds"].iloc[0].date().isoformat(), df["ds"].iloc[-1].date().isoformat(),
                      freq, float(used["synthetic"].mean()), sorted(set(used["source"])),
                      real_only=real_only)
    return df, info


def _fit(df: pd.DataFrame, freq: str):
    try:
        from prophet import Prophet  # imported lazily: heavy, optional import
    except ImportError as e:
        raise ProphetNotAvailableError(
            "Prophet is not installed; install backend/requirements-prophet.txt "
            "or use the scikit-learn forecaster (/api/v1/forecast/sklearn)") from e
    span_days = (df["ds"].iloc[-1] - df["ds"].iloc[0]).days
    m = Prophet(yearly_seasonality=span_days >= 2 * 365, weekly_seasonality=False,
                daily_seasonality=False, interval_width=0.8, changepoint_prior_scale=0.05)
    m.fit(pd.DataFrame({"ds": df["ds"], "y": np.log(df["y"].to_numpy())}))
    return m


def _predict(m, horizon: int, freq: str) -> pd.DataFrame:
    fut = m.make_future_dataframe(periods=horizon, freq=PANDAS_FREQ[freq], include_history=False)
    f = m.predict(fut)
    return pd.DataFrame({"ds": f["ds"], "yhat": np.exp(f["yhat"]),
                         "lower": np.exp(f["yhat_lower"]), "upper": np.exp(f["yhat_upper"])})


def backtest(df: pd.DataFrame, freq: str, horizon: int, n_folds: int = 3) -> dict:
    """Rolling-origin evaluation. Compares Prophet with (a) last-value naive and
    (b) seasonal-naive. Skill > 0 means Prophet beat the better of the two."""
    season = SEASON[freq]
    maes, naive, snaive, smapes, cover = [], [], [], [], []
    for k in range(n_folds):
        end = len(df) - horizon * (n_folds - 1 - k)
        train, test = df.iloc[: end - horizon], df.iloc[end - horizon: end]
        if len(train) < MIN_POINTS[freq]:
            continue
        pred = _predict(_fit(train, freq), horizon, freq)
        y, yhat = test["y"].to_numpy(), pred["yhat"].to_numpy()
        maes.append(float(np.mean(np.abs(y - yhat))))
        smapes.append(float(np.mean(2 * np.abs(y - yhat) / (np.abs(y) + np.abs(yhat))) * 100))
        naive.append(float(np.mean(np.abs(y - train["y"].iloc[-1]))))
        if len(train) > season:
            ref = train["y"].to_numpy()[-season:][:horizon]
            snaive.append(float(np.mean(np.abs(y[: len(ref)] - ref))))
        cover.append(float(np.mean((y >= pred["lower"].to_numpy()) & (y <= pred["upper"].to_numpy()))))
    if not maes:
        return {"folds": 0, "reliable": False, "reason": "not enough history to back-test"}
    model_mae = float(np.mean(maes))
    base_mae = float(min(np.mean(naive), np.mean(snaive))) if snaive else float(np.mean(naive))
    skill = 1 - model_mae / base_mae if base_mae > 0 else 0.0
    return {"folds": len(maes), "mae": round(model_mae, 3), "baseline_mae": round(base_mae, 3),
            "smape_pct": round(float(np.mean(smapes)), 2), "skill_vs_baseline": round(skill, 3),
            "interval_coverage": round(float(np.mean(cover)), 2), "reliable": bool(skill > 0.0),
            "reason": "beats naive baselines" if skill > 0 else "does not beat naive baselines"}


def signal(last_level: float, fc: pd.DataFrame) -> dict:
    change = float(fc["yhat"].mean() / last_level - 1)
    direction = "up" if change > FLAT_BAND else "down" if change < -FLAT_BAND else "flat"
    return {"direction": direction, "expected_change_pct": round(change * 100, 1)}


def fingerprint(db: Session, hub_id: str, crop: str) -> str:
    n, last, total = db.query(func.count(models.PriceObservation.id),
                              func.max(models.PriceObservation.observed_on),
                              func.sum(models.PriceObservation.price)).filter_by(hub_id=hub_id, crop=crop).one()
    return hashlib.sha256(f"{n}|{last}|{round(total or 0, 4)}".encode()).hexdigest()[:32]


def forecast_pair(db: Session, hub: Hub, crop: str, horizon: int = 8, run_backtest: bool = True) -> dict:
    df, info = load_series(db, hub.id, crop)
    model = _fit(df, info.freq)
    fc = _predict(model, horizon, info.freq)
    bt = backtest(df, info.freq, horizon) if run_backtest else {"reliable": False, "reason": "back-test skipped"}
    last_level = float(df["y"].tail(4).mean())
    tail = df.tail(52 if info.freq == "W" else 24)
    return {
        "hub": {"id": hub.id, "name": hub.name, "country": hub.country, "currency": hub.currency},
        "crop": crop, "unit": "kg", "horizon": horizon, "frequency": info.freq,
        "series": {"points": info.n_points, "start": info.start, "end": info.end,
                   "sources": info.sources, "synthetic_share": round(info.synthetic_share, 3),
                   "real_only": info.real_only},
        "history": [{"ds": d.date().isoformat(), "y": round(float(y), 2)} for d, y in zip(tail["ds"], tail["y"])],
        "forecast": [{"ds": r.ds.date().isoformat(), "yhat": round(float(r.yhat), 2),
                      "lower": round(float(r.lower), 2), "upper": round(float(r.upper), 2)}
                     for r in fc.itertuples()],
        "signal": signal(last_level, fc), "validation": bt, "reliable": bool(bt.get("reliable")),
        "warnings": ([ "Built on SYNTHETIC demo data - not a real market forecast."] if info.synthetic_share > 0 else [])
                    + ([] if bt.get("reliable") else ["Forecast did not beat naive baselines; do not rely on it."]),
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def get_or_compute(db: Session, hub_id: str, crop: str, horizon: int = 8, force: bool = False) -> dict:
    hub = get_hub(hub_id)
    if hub is None:
        raise KeyError(f"Unknown hub '{hub_id}'")
    if crop not in CROPS:
        raise KeyError(f"Unknown crop '{crop}'")
    fp = fingerprint(db, hub.id, crop)
    snap = db.query(models.ForecastSnapshot).filter_by(hub_id=hub.id, crop=crop, horizon=horizon).first()
    if snap and snap.fingerprint == fp and not force:
        return json.loads(snap.payload)
    result = forecast_pair(db, hub, crop, horizon)
    if snap:
        snap.fingerprint, snap.payload, snap.created_at = fp, json.dumps(result), datetime.utcnow()
    else:
        db.add(models.ForecastSnapshot(hub_id=hub.id, crop=crop, horizon=horizon,
                                       fingerprint=fp, payload=json.dumps(result)))
    db.commit()
    return result


def forecast_all(db: Session, hubs: list[Hub], horizon: int = 8, force: bool = False) -> list[dict]:
    """Every hub x crop. Pairs that cannot be forecast are reported, not skipped silently."""
    out = []
    for hub in hubs:
        for crop in CROPS:
            try:
                r = get_or_compute(db, hub.id, crop, horizon, force)
                out.append({"hub": hub.id, "crop": crop, "status": "ok", "reliable": r["reliable"],
                            "signal": r["signal"]})
            except InsufficientDataError as e:
                out.append({"hub": hub.id, "crop": crop, "status": "insufficient_data", "detail": str(e)})
            except ProphetNotAvailableError as e:
                out.append({"hub": hub.id, "crop": crop, "status": "prophet_not_installed", "detail": str(e)})
    return out
