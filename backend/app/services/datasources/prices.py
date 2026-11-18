"""Price-history ingestion: generic CSV, FAOSTAT bulk CSV, and DB upsert."""
from __future__ import annotations
import calendar
import io
from datetime import date
from typing import Iterable, IO

import pandas as pd
from sqlalchemy.orm import Session

from ... import models
from ...config import CROPS, Hub, get_hub

REQUIRED_COLS = {"hub_id", "crop", "date", "price"}


def _clean_frame(df: pd.DataFrame, source: str, synthetic: bool) -> list[dict]:
    rows = []
    for r in df.itertuples(index=False):
        price = float(r.price)
        if not price > 0:      # also rejects NaN
            continue
        hub = get_hub(str(r.hub_id).strip().lower())
        crop = str(r.crop).strip().lower()
        if hub is None or crop not in CROPS:
            continue
        rows.append(dict(hub_id=hub.id, crop=crop, observed_on=pd.Timestamp(r.date).date(),
                         price=price, currency=str(getattr(r, "currency", "") or hub.currency),
                         unit=str(getattr(r, "unit", "") or "kg"),
                         source=str(getattr(r, "source", "") or source), is_synthetic=synthetic))
    return rows


def read_price_csv(src: str | IO, source_label: str = "csv-import") -> list[dict]:
    """Columns: hub_id, crop, date, price [, currency, unit, source]. Rows that are
    invalid (unknown hub/crop, non-positive price) are skipped, never guessed."""
    df = pd.read_csv(src)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "price"])
    return _clean_frame(df, source_label, synthetic=False)


def read_faostat_producer_prices(src: str | IO, hubs: Iterable[Hub]) -> list[dict]:
    """Parse the FAOSTAT *Producer Prices* bulk CSV (normalized format).

    FAOSTAT prices are national, so every hub in a country receives the same
    country-level series; the source label says so. Only monthly rows are used
    (annual values would be too sparse to forecast). Expected columns include
    Area, Item, Element, Months, Year, Unit, Value.
    """
    df = pd.read_csv(src, encoding="latin-1" if isinstance(src, str) else None)
    df.columns = [c.strip() for c in df.columns]
    need = {"Area", "Item", "Element", "Months", "Year", "Value"}
    if not need <= set(df.columns):
        raise ValueError(f"Not a FAOSTAT producer-price file; missing {sorted(need - set(df.columns))}")
    df = df[df["Element"].str.contains("Producer Price", case=False, na=False)]
    month_names = {m: i for i, m in enumerate(calendar.month_name) if m}
    df = df[df["Months"].isin(month_names)]
    out: list[dict] = []
    for hub in hubs:
        sub = df[df["Area"].str.lower() == hub.faostat_area.lower()]
        for crop in CROPS.values():
            mask = sub["Item"].str.lower().apply(lambda s: any(k in s for k in crop.faostat_keywords))
            for r in sub[mask].itertuples(index=False):
                value = pd.to_numeric(r.Value, errors="coerce")
                if not value or value <= 0:
                    continue
                # The price basis lives in Element ("Producer Price (LCU/tonne)"); Unit is just "LCU".
                basis = f"{r.Element} {getattr(r, 'Unit', '') or ''}".lower()
                if "tonne" not in basis:
                    continue   # unknown basis: skip rather than guess units
                per_kg = float(value) / 1000.0
                out.append(dict(hub_id=hub.id, crop=crop.id,
                                observed_on=date(int(r.Year), month_names[r.Months], 1),
                                price=per_kg, currency=hub.currency, unit="kg",
                                source=f"FAOSTAT producer prices (national, {hub.faostat_area})",
                                is_synthetic=False))
    return out


def upsert_prices(db: Session, rows: list[dict]) -> dict:
    """Insert new observations, skipping ones already present for the same key."""
    inserted = skipped = 0
    existing = {(o.hub_id, o.crop, o.observed_on, o.source)
                for o in db.query(models.PriceObservation.hub_id, models.PriceObservation.crop,
                                  models.PriceObservation.observed_on, models.PriceObservation.source)}
    for r in rows:
        key = (r["hub_id"], r["crop"], r["observed_on"], r["source"])
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        db.add(models.PriceObservation(**r))
        inserted += 1
    db.commit()
    return {"inserted": inserted, "skipped": skipped}
