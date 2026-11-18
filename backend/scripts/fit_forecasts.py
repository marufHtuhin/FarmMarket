"""Fit + back-test Prophet for every hub x crop and cache the results.
  python scripts/fit_forecasts.py --horizon 8 [--force]
"""
import _bootstrap  # noqa: F401
import argparse
from app.database import Base, engine, SessionLocal
from app.config import active_hubs
from app.services import forecasting as F

ap = argparse.ArgumentParser(); ap.add_argument("--horizon", type=int, default=8); ap.add_argument("--force", action="store_true")
a = ap.parse_args()
Base.metadata.create_all(bind=engine)
db = SessionLocal()
for r in F.forecast_all(db, active_hubs(), a.horizon, a.force):
    tail = (f"reliable={r['reliable']} signal={r['signal']}" if r["status"] == "ok" else r["detail"])
    print(f"{r['hub']:>14} {r['crop']:<7} {r['status']:<18} {tail}")
