"""Synthetic price series for demos and tests ONLY.

Every row is flagged is_synthetic=True and the API surfaces that flag. Synthetic
data proves the pipeline works; it says nothing about real markets.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from ...config import CROPS, Hub, active_hubs

_BASE = {"maize": 45.0, "tomato": 80.0, "onion": 70.0, "potato": 55.0, "banana": 60.0}


def synthetic_rows(hubs: list[Hub] | None = None, years: int = 4, freq: str = "W",
                   end: str = "2026-10-26", seed: int = 7) -> list[dict]:
    rng = np.random.default_rng(seed)
    hubs = hubs or active_hubs()
    idx = pd.date_range(end=end, periods=int(years * (52 if freq == "W" else 12)), freq=freq)
    t = np.arange(len(idx))
    per_year = 52 if freq == "W" else 12
    rows = []
    for hub in hubs:
        for crop in CROPS:
            base = _BASE[crop] * rng.uniform(0.8, 1.3)
            phase = rng.uniform(0, 2 * np.pi)
            season = 0.18 * np.sin(2 * np.pi * t / per_year + phase)
            trend = 0.0006 * t * rng.uniform(0.5, 1.5)
            noise = rng.normal(0, 0.03, len(idx))
            price = base * np.exp(season + trend + noise)
            for d, p in zip(idx, price):
                rows.append(dict(hub_id=hub.id, crop=crop, observed_on=d.date(), price=round(float(p), 2),
                                 currency=hub.currency, unit="kg", source="synthetic-demo", is_synthetic=True))
    return rows
