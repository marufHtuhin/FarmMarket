"""Public reference catalogs: countries/hubs and crops.

Coordinates and currencies come from app/config.py. All prices stay
per-market: a hub's currency is the only currency used for that market.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..config import COUNTRY_ORDER, CROP_CATALOG, HUB_PROFILES
from ..database import get_db

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/countries")
def countries():
    """The six FarmMarket countries with their trading hubs."""
    hubs_by_iso3: dict[str, list] = {}
    for profile in HUB_PROFILES.values():
        for h in profile:
            hubs_by_iso3.setdefault(h.iso3, []).append(h)
    out = []
    for iso3, code in COUNTRY_ORDER:
        hubs = hubs_by_iso3.get(iso3, [])
        if not hubs:
            continue
        out.append({"code": code, "name": hubs[0].country, "currency": hubs[0].currency,
                    "hubs": [{"id": h.id, "name": h.name, "lat": h.lat, "lon": h.lon}
                             for h in hubs]})
    return out


@router.get("/crops")
def crops(db: Session = Depends(get_db)):
    """Crop catalog with local names. Served from the crops tables when
    seeded; falls back to the static catalog in config.py on an unseeded DB
    so the public contract always holds."""
    rows = db.query(models.Crop).all()
    if rows:
        order = {c["id"]: i for i, c in enumerate(CROP_CATALOG)}
        rows.sort(key=lambda c: order.get(c.id, len(order)))
        return [{"id": c.id, "name": c.name,
                 "local_names": {"en": c.name,
                                 **{ln.language: ln.name for ln in c.local_names}},
                 "unit": c.default_unit} for c in rows]
    return [{"id": c["id"], "name": c["name"],
             "local_names": {"en": c["name"], "bn": c["bn"]},
             "unit": c["unit"]} for c in CROP_CATALOG]
