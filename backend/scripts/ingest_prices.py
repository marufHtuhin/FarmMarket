"""Load price history into the database.

  python scripts/ingest_prices.py --csv my_prices.csv
  python scripts/ingest_prices.py --faostat Prices_E_All_Data_NORMALIZED.csv
  python scripts/ingest_prices.py --synthetic          # DEMO ONLY, flagged is_synthetic
"""
import _bootstrap  # noqa: F401
import argparse
from app.database import Base, engine, SessionLocal
from app.config import active_hubs
from app.services.datasources import prices, synthetic

ap = argparse.ArgumentParser()
ap.add_argument("--csv"); ap.add_argument("--faostat")
ap.add_argument("--synthetic", action="store_true", help="demo data only; never a real forecast")
a = ap.parse_args()
Base.metadata.create_all(bind=engine)
db = SessionLocal()
rows = []
if a.csv: rows += prices.read_price_csv(a.csv, source_label=a.csv)
if a.faostat: rows += prices.read_faostat_producer_prices(a.faostat, active_hubs())
if a.synthetic: rows += synthetic.synthetic_rows()
if not rows:
    raise SystemExit("Nothing to load: pass --csv, --faostat or --synthetic")
print(prices.upsert_prices(db, rows))
