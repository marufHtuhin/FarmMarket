"""Real-price endpoints: admin manual entry + latest prices with provenance.

DAM (Department of Agricultural Marketing, dam.gov.bd) publishes daily prices
but has NO public API, and its report pages render their tables via JS/PDF so
no parseable structure could be verified (see docs/dam-prices.md). Real prices
therefore enter FarmMarket by hand: an admin reads the day's DAM report (or
another verified source) and records it here. Every stored price carries
source="manual", the market day, an entry timestamp and the optional note —
and every price the API returns carries its source, timestamps, a REAL/DEMO
label and a staleness flag.
"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import CROPS, get_hub
from ..database import get_db
from ..security import require_role
from ..services.audit import log_audit
from ..services import price_labels as PL

router = APIRouter(prefix="/api/v1/prices", tags=["prices"])
admin = require_role("admin")

MANUAL_SOURCE = "manual"


def observation_out(o: models.PriceObservation) -> dict:
    """One observation with full provenance: source, timestamps, label, staleness."""
    label = PL.price_label(bool(o.is_synthetic))
    return {"id": o.id, "hub": o.hub_id, "crop": o.crop,
            "price": o.price, "currency": o.currency, "unit": o.unit,
            "source": o.source, "note": o.note,
            "observed_on": o.observed_on.isoformat() if o.observed_on else None,
            "ingested_at": (o.ingested_at.isoformat() + "Z"
                            if o.ingested_at and o.ingested_at.tzinfo is None
                            else (o.ingested_at.isoformat() if o.ingested_at else None)),
            "is_synthetic": bool(o.is_synthetic), "label": label,
            "stale": PL.is_stale(o.observed_on, bool(o.is_synthetic)),
            "age_hours": (round(a, 1) if (a := PL.age_hours(o.observed_on)) is not None else None)}


@router.post("/manual", status_code=201)
def manual_price(data: schemas.ManualPriceIn, response: Response,
                 db: Session = Depends(get_db), user=Depends(admin)):
    """Admin-only: record one day's real price for a hub x crop.

    Re-entering the same hub/crop/date updates the existing manual row (with a
    fresh ingested_at) instead of duplicating it. The price is stored as a
    REAL (non-synthetic) observation, so the forecasters will prefer it once
    enough real history exists.
    """
    hub = get_hub(data.hub.strip().lower())
    if hub is None:
        raise HTTPException(404, f"Unknown hub '{data.hub}'")
    crop = data.crop.strip().lower()
    if crop not in CROPS:
        raise HTTPException(404, f"Unknown crop '{data.crop}'")
    observed = data.observed_on or date.today()
    if observed > date.today():
        raise HTTPException(422, "Price date cannot be in the future")
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, as elsewhere
    existing = (db.query(models.PriceObservation)
                .filter_by(hub_id=hub.id, crop=crop, observed_on=observed,
                           source=MANUAL_SOURCE).first())
    if existing:
        existing.price = data.price
        existing.note = (data.note or "").strip() or None
        existing.currency = hub.currency
        existing.ingested_at = now
        db.commit()
        db.refresh(existing)
        log_audit(db, user.id, "manual_price_updated",
                  f"{hub.id}/{crop}/{observed} price={data.price}")
        response.status_code = 200  # update, not a new row
        return {"updated": True, **observation_out(existing)}
    obs = models.PriceObservation(hub_id=hub.id, crop=crop, observed_on=observed,
                                  price=data.price, currency=hub.currency, unit="kg",
                                  source=MANUAL_SOURCE, is_synthetic=False,
                                  note=(data.note or "").strip() or None,
                                  ingested_at=now)
    db.add(obs)
    db.commit()
    db.refresh(obs)
    log_audit(db, user.id, "manual_price_created",
              f"{hub.id}/{crop}/{observed} price={data.price}")
    return {"updated": False, **observation_out(obs)}


@router.get("/manual")
def list_manual(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db),
                user=Depends(admin)):
    """Admin-only: the most recently entered manual prices, newest first."""
    rows = (db.query(models.PriceObservation).filter_by(source=MANUAL_SOURCE)
            .order_by(models.PriceObservation.observed_on.desc(),
                      models.PriceObservation.ingested_at.desc())
            .limit(limit).all())
    return {"items": [observation_out(o) for o in rows], "count": len(rows)}


@router.get("/history")
def price_history(hub: str, crop: str, db: Session = Depends(get_db)):
    """Full dated price series for one hub x crop, oldest first.

    This is the series behind the price-trend chart: every PriceObservation
    for the pair, one point per market day, each with its source, REAL/DEMO
    label and staleness flag. A manual (real) entry on a date that already
    has a synthetic point replaces it for that day — the real price is what
    happened; ties between same-kind rows go to the most recently entered.
    New admin entries therefore appear here as new (or corrected) points
    with no code change.

    Why not reuse /forecast/sklearn's history? That endpoint returns only
    the last 52 points, with no per-point source/label/stale, and it fits a
    RandomForest on every call. This is a cheap read of the stored series.
    """
    h = get_hub(hub.strip().lower())
    if h is None:
        raise HTTPException(404, f"Unknown hub '{hub}'")
    c = crop.strip().lower()
    if c not in CROPS:
        raise HTTPException(404, f"Unknown crop '{crop}'")
    rows = (db.query(models.PriceObservation).filter_by(hub_id=h.id, crop=c)
            .order_by(models.PriceObservation.observed_on.asc(),
                      models.PriceObservation.is_synthetic.desc(),
                      models.PriceObservation.ingested_at.asc()).all())
    by_date: dict = {}
    for o in rows:
        # Ordered so the preferred row lands last per date: real beats
        # synthetic, and among equals the latest entry wins.
        by_date[o.observed_on] = o
    points = [observation_out(o) for o in by_date.values()]
    return {"hub": h.id, "crop": c, "points": points, "count": len(points)}


@router.get("/latest")
def latest_prices(hub: str | None = None, crop: str | None = None,
                  db: Session = Depends(get_db)):
    """Latest observation per hub x crop, with source, timestamps, REAL/DEMO
    label and staleness. 'Latest' means the most recently observed market day
    (ties broken by most recently ingested)."""
    if hub is not None and get_hub(hub.strip().lower()) is None:
        raise HTTPException(404, f"Unknown hub '{hub}'")
    if crop is not None and crop.strip().lower() not in CROPS:
        raise HTTPException(404, f"Unknown crop '{crop}'")
    q = db.query(models.PriceObservation)
    if hub is not None:
        q = q.filter_by(hub_id=hub.strip().lower())
    if crop is not None:
        q = q.filter_by(crop=crop.strip().lower())
    rows = (q.order_by(models.PriceObservation.observed_on.desc(),
                       models.PriceObservation.ingested_at.desc()).all())
    seen: set[tuple[str, str]] = set()
    out = []
    for o in rows:
        key = (o.hub_id, o.crop)
        if key in seen:
            continue
        seen.add(key)
        out.append(observation_out(o))
    return {"prices": out, "count": len(out),
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds")}
