"""scikit-learn price forecaster (RandomForest, no Prophet dependency).

Design (mirrors forecasting.forecast_pair's response shape):
  * Fit on log(price) so forecasts stay positive.
  * Features per step t: lags 1, 2, 4, 8, 13, 26, rolling mean/std of the
    last 4 and 13 steps, week-of-year and month sin/cos, linear trend index.
    Only rows where every lag exists are used for training.
  * Multi-step forecasts are recursive: predict one step, append the
    prediction (in price space, then re-logged) and repeat.
  * Prediction interval: 80% interval from the residual std of a small
    one-step-ahead hold-out, lower/upper = yhat * exp(-/+1.28 * sigma_log).
  * Every forecast is back-tested (one rolling-origin fold) against a
    last-value naive baseline. Forecasts that do not beat it are returned
    with reliable=False.
  * Too little history -> forecasting.InsufficientDataError (never a
    made-up forecast). Results are computed fresh on every call: they are
    deliberately NOT written to ForecastSnapshot, whose (hub, crop, horizon)
    key is shared with the Prophet forecaster.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sqlalchemy.orm import Session

from ..config import Hub, get_hub
from . import forecasting as F

MODEL_NAME = "sklearn-random-forest"
LAGS = (1, 2, 4, 8, 13, 26)
ROLL_WINDOWS = (4, 13)
MIN_POINTS_SKLEARN = 30
MIN_TRAIN_ROWS = 5
DEFAULT_SIGMA_LOG = 0.05  # fallback log-space residual std when no hold-out is usable
Z_80 = 1.28  # ~80% two-sided normal interval


def _calendar(d: pd.Timestamp) -> tuple[float, float, float, float]:
    week = float(pd.Timestamp(d).isocalendar().week)
    month = float(pd.Timestamp(d).month)
    return (float(np.sin(2 * np.pi * week / 52.0)), float(np.cos(2 * np.pi * week / 52.0)),
            float(np.sin(2 * np.pi * month / 12.0)), float(np.cos(2 * np.pi * month / 12.0)))


def _feature_row(y_log: np.ndarray, d: pd.Timestamp, t: int) -> np.ndarray:
    """Feature vector for step t, using only values strictly before t.

    Requires t >= max(LAGS) so every lag and rolling window exists.
    """
    feats: list[float] = [float(y_log[t - lag]) for lag in LAGS]
    for w in ROLL_WINDOWS:
        window = y_log[t - w:t]
        feats.append(float(np.mean(window)))
        feats.append(float(np.std(window)))
    feats.extend(_calendar(d))
    feats.append(float(t))  # linear trend index
    return np.asarray(feats, dtype=float)


def _build_frame(y_log: np.ndarray, ds: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Training frame: only rows where all lags exist (t >= max(LAGS))."""
    rows, targets = [], []
    for t in range(max(LAGS), len(y_log)):
        rows.append(_feature_row(y_log, ds.iloc[t], t))
        targets.append(float(y_log[t]))
    if not rows:
        return np.empty((0, 0)), np.empty(0)
    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)


def _fit_model(X: np.ndarray, y: np.ndarray) -> RandomForestRegressor:
    model = RandomForestRegressor(n_estimators=200, random_state=0, n_jobs=-1)
    model.fit(X, y)
    return model


def _future_dates(last_ds: pd.Timestamp, freq: str, horizon: int) -> pd.DatetimeIndex:
    return pd.date_range(start=pd.Timestamp(last_ds), periods=horizon + 1,
                         freq=F.PANDAS_FREQ[freq])[1:]


def _recursive_forecast(model: RandomForestRegressor, y_log: np.ndarray,
                        last_ds: pd.Timestamp, freq: str, horizon: int) -> pd.DataFrame:
    """Predict one step at a time, feeding each prediction back as history."""
    hist = [float(v) for v in y_log]
    preds: list[float] = []
    dates = _future_dates(last_ds, freq, horizon)
    for d in dates:
        x = _feature_row(np.asarray(hist, dtype=float), d, len(hist))
        log_pred = float(model.predict(x.reshape(1, -1))[0])
        price = float(np.exp(log_pred))
        preds.append(price)
        hist.append(float(np.log(price)))  # append in price space, then re-log
    return pd.DataFrame({"ds": dates, "yhat": np.asarray(preds, dtype=float)})


def _one_step_residuals(model: RandomForestRegressor, y_log: np.ndarray,
                        ds: pd.Series, start: int) -> list[float]:
    """One-step-ahead log residuals from `start` onwards, using true lags."""
    residuals = []
    for t in range(start, len(y_log)):
        x = _feature_row(y_log, ds.iloc[t], t)
        residuals.append(float(y_log[t] - model.predict(x.reshape(1, -1))[0]))
    return residuals


def _holdout_sigma(df: pd.DataFrame, freq: str,
                   full_model: RandomForestRegressor | None = None) -> float:
    """Log-space residual std from a small one-step-ahead hold-out.

    Holds out the last min(8, len//5) points. Prefer a model trained without
    the hold-out; fall back to the full model (true lags) when the remaining
    history is too short to train on, and to a fixed default when no usable
    residuals exist at all.
    """
    n = len(df)
    holdout = min(8, n // 5)
    if holdout < 2:
        return DEFAULT_SIGMA_LOG
    y_log = np.log(df["y"].to_numpy(dtype=float))
    ds = df["ds"]
    sigma: float | None = None
    train_n = n - holdout
    if train_n > max(LAGS) + MIN_TRAIN_ROWS:
        X_tr, y_tr = _build_frame(y_log[:train_n], ds.iloc[:train_n])
        if len(X_tr) >= MIN_TRAIN_ROWS:
            sub = _fit_model(X_tr, y_tr)
            residuals = _one_step_residuals(sub, y_log, ds, train_n)
            if residuals:
                sigma = float(np.std(residuals))
    if (sigma is None or not np.isfinite(sigma) or sigma <= 0) and full_model is not None:
        residuals = _one_step_residuals(full_model, y_log, ds, n - holdout)
        if residuals:
            sigma = float(np.std(residuals))
    if sigma is None or not np.isfinite(sigma) or sigma <= 0:
        return DEFAULT_SIGMA_LOG
    return sigma


def _backtest(df: pd.DataFrame, freq: str, horizon: int) -> dict:
    """One rolling-origin fold: train on all but the last `horizon` points,
    recursive-forecast them, and compare MAE with a last-value naive baseline.
    """
    n = len(df)
    train_n = n - horizon
    if train_n <= max(LAGS) + MIN_TRAIN_ROWS:
        return {"folds": 0, "reliable": False, "reason": "not enough history to back-test"}
    train, test = df.iloc[:train_n], df.iloc[train_n:]
    y_log_train = np.log(train["y"].to_numpy(dtype=float))
    X_tr, y_tr = _build_frame(y_log_train, train["ds"])
    if len(X_tr) < MIN_TRAIN_ROWS:
        return {"folds": 0, "reliable": False, "reason": "not enough history to back-test"}
    pred = _recursive_forecast(_fit_model(X_tr, y_tr), y_log_train,
                               train["ds"].iloc[-1], freq, horizon)
    y = test["y"].to_numpy(dtype=float)
    yhat = pred["yhat"].to_numpy(dtype=float)
    mae = float(np.mean(np.abs(y - yhat)))
    baseline_mae = float(np.mean(np.abs(y - float(train["y"].iloc[-1]))))
    smape = float(np.mean(2 * np.abs(y - yhat) / (np.abs(y) + np.abs(yhat))) * 100)
    skill = 1 - mae / baseline_mae if baseline_mae > 0 else 0.0
    return {"folds": 1, "mae": round(mae, 3), "baseline_mae": round(baseline_mae, 3),
            "smape_pct": round(smape, 2), "skill_vs_baseline": round(skill, 3),
            "reliable": bool(skill > 0.0),
            "reason": "beats naive baseline" if skill > 0 else "does not beat naive baseline"}


def forecast_sklearn(db: Session, hub: Hub | str, crop: str, horizon: int = 8) -> dict:
    """RandomForest price forecast for one hub x crop, same response shape as
    forecasting.forecast_pair (plus a "model" key). Computed fresh each call;
    never cached in ForecastSnapshot (shared with Prophet)."""
    if isinstance(hub, str):
        resolved = get_hub(hub)
        if resolved is None:
            raise KeyError(f"Unknown hub '{hub}'")
        hub = resolved
    df, info = F.load_series(db, hub.id, crop, min_points=MIN_POINTS_SKLEARN)
    y_log = np.log(df["y"].to_numpy(dtype=float))
    X, y = _build_frame(y_log, df["ds"])
    if len(X) < MIN_TRAIN_ROWS:
        raise F.InsufficientDataError(
            f"Need at least {MIN_POINTS_SKLEARN} {info.freq} observations with "
            f"{max(LAGS)} lags available; have {len(df)}")
    model = _fit_model(X, y)
    fc = _recursive_forecast(model, y_log, df["ds"].iloc[-1], info.freq, horizon)
    sigma = _holdout_sigma(df, info.freq, model)
    fc["lower"] = np.maximum(fc["yhat"] * np.exp(-Z_80 * sigma), 0.01)
    fc["upper"] = fc["yhat"] * np.exp(Z_80 * sigma)
    bt = _backtest(df, info.freq, horizon)
    last_level = float(df["y"].tail(4).mean())
    tail = df.tail(52 if info.freq == "W" else 24)
    forecast_rows = []
    for r in fc.itertuples():
        yhat = round(float(r.yhat), 2)
        # Keep the interval ordered after rounding.
        lower = min(round(float(r.lower), 2), yhat)
        upper = max(round(float(r.upper), 2), yhat)
        forecast_rows.append({"ds": r.ds.date().isoformat(), "yhat": yhat,
                              "lower": lower, "upper": upper})
    return {
        "model": MODEL_NAME,
        "hub": {"id": hub.id, "name": hub.name, "country": hub.country, "currency": hub.currency},
        "crop": crop, "unit": "kg", "horizon": horizon, "frequency": info.freq,
        "series": {"points": info.n_points, "start": info.start, "end": info.end,
                   "sources": info.sources, "synthetic_share": round(info.synthetic_share, 3),
                   "real_only": info.real_only},
        "history": [{"ds": d.date().isoformat(), "y": round(float(v), 2)}
                    for d, v in zip(tail["ds"], tail["y"])],
        "forecast": forecast_rows,
        "signal": F.signal(last_level, fc), "validation": bt, "reliable": bool(bt.get("reliable")),
        "warnings": (["Built on SYNTHETIC demo data - not a real market forecast."]
                     if info.synthetic_share > 0 else [])
                    + ([] if bt.get("reliable")
                       else ["Forecast did not beat naive baselines; do not rely on it."])
                    + ["scikit-learn demo model: recursive RandomForest on lag + calendar "
                       "features; decision support only, not a guarantee."],
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
