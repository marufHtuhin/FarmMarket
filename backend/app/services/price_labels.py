"""REAL vs DEMO labelling and staleness for prices.

Every price FarmMarket shows carries a source, a timestamp, a label and a
staleness flag — never a faked freshness:

  * label "demo" — synthetic / illustrative data (PriceObservation.is_synthetic,
    or a PriceRecord whose source says demo/synthetic). Demo data is never
    called "stale": it is already flagged as not real.
  * label "real" — an ingested or manually entered observation.
  * stale — a REAL price whose observed/recorded time is more than
    STALE_AFTER_HOURS old, or a real price with no timestamp at all (freshness
    cannot be verified, so it is not claimed).

A date-only observation is treated as the start of that day (UTC) for age
purposes: a price observed two calendar days ago is therefore stale.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

STALE_AFTER_HOURS = 48
STALE_AFTER = timedelta(hours=STALE_AFTER_HOURS)


def price_label(is_synthetic: bool) -> str:
    """Label for a PriceObservation, from its is_synthetic flag."""
    return "demo" if is_synthetic else "real"


def record_label(source: str | None) -> str:
    """Label for a PriceRecord, which has no is_synthetic column.

    Seeded demo records carry source "Illustrative demo data - ..."; any
    other source is treated as real. New PriceRecord writers must keep the
    demo wording on demo rows (see seed_demo.py PRICE_SOURCE).
    """
    s = (source or "").lower()
    return "demo" if ("demo" in s or "synthetic" in s) else "real"


def _as_utc(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def age_hours(value: date | datetime | None, now: datetime | None = None) -> float | None:
    """Age of a timestamp in hours, or None when there is no timestamp."""
    ts = _as_utc(value)
    if ts is None:
        return None
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return max((ref - ts).total_seconds() / 3600.0, 0.0)


def is_stale(value: date | datetime | None, is_synthetic: bool,
             now: datetime | None = None) -> bool:
    """True when a REAL price is older than STALE_AFTER_HOURS.

    Demo prices are never stale (the DEMO label already says they are not
    live). A real price with no timestamp counts as stale: without a time
    we cannot claim it is fresh.
    """
    if is_synthetic:
        return False
    age = age_hours(value, now)
    if age is None:
        return True
    return age > STALE_AFTER_HOURS
