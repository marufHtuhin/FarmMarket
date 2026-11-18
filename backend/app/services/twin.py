"""Digital Twin: tamper-evident provenance + cold-chain ledger for produce batches.

What this IS: a per-batch hash chain (each block commits to the previous block), sensor
readings authenticated with per-device HMAC keys, readings sealed into blocks via a
Merkle root, and a verifier that detects any edit to blocks or sealed readings.

What this is NOT (yet): a public/permissioned blockchain. The chain lives in your database,
so whoever controls the DB could rewrite it *and* recompute every hash. For third-party
verifiability, anchor the batch head hash somewhere you do not control (public chain,
consortium ledger, notary service) through `AnchorProvider`. `LocalAnchor` only records
the head hash locally and says so.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy.orm import Session

from .. import models

GENESIS = "0" * 64
FUTURE_SKEW = timedelta(minutes=5)

EVENT_TYPES = {"harvested", "packed", "dispatched", "in_transit_checkpoint", "delivered", "received",
               "inspected", "sensor_seal", "sensor_simulation"}
BUYER_EVENTS = {"received", "inspected"}

# Illustrative storage ranges (deg C / % RH). Tune per variety, maturity stage and local guidance.
COLD_CHAIN_RULES = {
    "tomato": {"temp_c": (8.0, 15.0), "rh_pct": (85.0, 95.0)},
    "banana": {"temp_c": (13.0, 15.0), "rh_pct": (85.0, 95.0)},
    "potato": {"temp_c": (4.0, 10.0), "rh_pct": (85.0, 95.0)},
    "onion": {"temp_c": (0.0, 25.0), "rh_pct": (65.0, 75.0)},
    "maize": {"temp_c": (0.0, 30.0), "rh_pct": (0.0, 75.0), "product_moisture_max_pct": 14.0},
}


# ---------------------------------------------------------------- primitives
def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def block_hash(idx: int, timestamp: str, event_type: str, actor: int | None, payload: str, prev: str) -> str:
    return sha256_hex(canonical({"i": idx, "t": timestamp, "e": event_type, "a": actor, "p": payload, "h": prev}))


def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        return sha256_hex("")
    level = [sha256_hex(x) for x in leaves]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [sha256_hex(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def _secret() -> bytes:
    return os.getenv("SECRET_KEY", "dev-only-change-this-secret").encode()


def device_key(device_id: str) -> str:
    """Per-device HMAC key derived from the server secret (nothing extra to store)."""
    return hmac.new(_secret(), f"twin-device:{device_id}".encode(), hashlib.sha256).hexdigest()


def _fmt(x) -> str:
    return "" if x is None else f"{float(x):.3f}"


def reading_message(device_id: str, recorded_at: str, temperature_c, moisture_pct, moisture_kind: str) -> str:
    """Signed string, trivial for firmware to reproduce:
        device_id|YYYY-MM-DDTHH:MM:SS|temp (3 dp or empty)|moisture (3 dp or empty)|rh or product
    The signature is hex(HMAC-SHA256(device_key, message))."""
    return "|".join([device_id, recorded_at, _fmt(temperature_c), _fmt(moisture_pct), moisture_kind])


def sign_reading(key: str, device_id: str, recorded_at: str, temperature_c, moisture_pct, moisture_kind="rh") -> str:
    """Helper for device firmware / tests."""
    msg = reading_message(device_id, recorded_at, temperature_c, moisture_pct, moisture_kind)
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- anchoring
class AnchorProvider(Protocol):
    name: str
    def anchor(self, batch_code: str, head_hash: str) -> str: ...


class LocalAnchor:
    """Records the head hash only. NOT external proof - see module docstring."""
    name = "local-unanchored"
    def anchor(self, batch_code: str, head_hash: str) -> str:
        return f"local:{head_hash[:16]}"


# ---------------------------------------------------------------- batches & chain
class TwinError(ValueError):
    pass


def new_batch_code() -> str:
    return "FM-" + secrets.token_hex(6).upper()


def create_batch(db: Session, farmer_id: int, crop: str, origin_district: str, quantity_kg: float,
                 harvested_at: datetime | None = None, variety: str = "", order_id: int | None = None) -> models.Batch:
    b = models.Batch(batch_code=new_batch_code(), farmer_id=farmer_id, crop=crop.lower(), variety=variety,
                     origin_district=origin_district, quantity_kg=quantity_kg, harvested_at=harvested_at,
                     order_id=order_id)
    db.add(b)
    db.flush()
    append_block(db, b, "harvested", farmer_id, {"crop": b.crop, "variety": variety, "origin_district": origin_district,
                                                  "quantity_kg": quantity_kg,
                                                  "harvested_at": _iso(harvested_at) if harvested_at else None})
    db.commit()
    db.refresh(b)
    return b


def _last_block(db: Session, batch_id: int) -> models.LedgerBlock | None:
    return (db.query(models.LedgerBlock).filter_by(batch_id=batch_id)
            .order_by(models.LedgerBlock.idx.desc()).first())


def append_block(db: Session, batch: models.Batch, event_type: str, actor_id: int | None, payload: dict,
                 now: datetime | None = None) -> models.LedgerBlock:
    if event_type not in EVENT_TYPES:
        raise TwinError(f"Unknown event type '{event_type}'")
    last = _last_block(db, batch.id)
    idx = 0 if last is None else last.idx + 1
    prev = GENESIS if last is None else last.block_hash
    ts = _iso(now or datetime.utcnow())
    p = canonical(payload)
    blk = models.LedgerBlock(batch_id=batch.id, idx=idx, timestamp=ts, event_type=event_type, actor_user_id=actor_id,
                             payload=p, prev_hash=prev, block_hash=block_hash(idx, ts, event_type, actor_id, p, prev))
    db.add(blk)
    db.flush()
    return blk


def add_event(db: Session, batch: models.Batch, user, event_type: str, data: dict) -> models.LedgerBlock:
    if event_type == "sensor_seal":
        raise TwinError("sensor_seal blocks are created by sealing, not manually")
    allowed = BUYER_EVENTS if (user.role == "buyer") else (EVENT_TYPES - {"sensor_seal"})
    if user.role == "farmer" and batch.farmer_id != user.id:
        raise PermissionError("Not your batch")
    if user.role == "buyer":
        order = db.get(models.Order, batch.order_id) if batch.order_id else None
        if not order or order.buyer_id != user.id:
            raise PermissionError("Only the buyer of the linked order may add events")
    if user.role == "transporter":
        # A transporter may only record events on a batch whose linked order
        # is assigned to them; previously ANY transporter could record any
        # event (e.g. "delivered") on ANY batch (P10 audit finding).
        order = db.get(models.Order, batch.order_id) if batch.order_id else None
        if not order or order.transporter_id != user.id:
            raise PermissionError("Only the transporter assigned to the linked order may add events")
    if event_type not in allowed:
        raise PermissionError(f"Role '{user.role}' may not record '{event_type}'")
    blk = append_block(db, batch, event_type, user.id, {**data, "actor_role": user.role})
    db.commit()
    return blk


# ---------------------------------------------------------------- sensors
def register_device(db: Session, batch: models.Batch, label: str = "") -> dict:
    dev = models.Device(device_id="DEV-" + secrets.token_hex(5).upper(), batch_id=batch.id, label=label)
    db.add(dev)
    db.commit()
    return {"device_id": dev.device_id, "hmac_key": device_key(dev.device_id),
            "note": "Store this key on the device; it is not shown again."}


def ingest_reading(db: Session, device_id: str, recorded_at: datetime, temperature_c: float | None,
                   moisture_pct: float | None, moisture_kind: str, signature: str,
                   lat: float | None = None, lon: float | None = None, now: datetime | None = None,
                   is_simulated: bool = False) -> models.SensorReading:
    dev = db.query(models.Device).filter_by(device_id=device_id).first()
    if not dev:
        raise PermissionError("Unknown device")
    if temperature_c is None and moisture_pct is None:
        raise TwinError("Reading needs temperature and/or moisture")
    if temperature_c is not None and not -40 <= temperature_c <= 80:
        raise TwinError("Temperature outside plausible sensor range (-40..80 C)")
    if moisture_pct is not None and not 0 <= moisture_pct <= 100:
        raise TwinError("Moisture must be 0..100 %")
    if moisture_kind not in ("rh", "product"):
        raise TwinError("moisture_kind must be 'rh' or 'product'")
    if recorded_at > (now or datetime.utcnow()) + FUTURE_SKEW:
        raise TwinError("Reading timestamp is in the future")
    msg = reading_message(device_id, _iso(recorded_at), temperature_c, moisture_pct, moisture_kind)
    expect = hmac.new(device_key(device_id).encode(), msg.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, signature or ""):
        raise PermissionError("Bad reading signature")
    if db.query(models.SensorReading).filter_by(device_id=device_id, signature=signature).first():
        raise TwinError("Duplicate reading (replay rejected)")
    r = models.SensorReading(batch_id=dev.batch_id, device_id=device_id, recorded_at=recorded_at,
                             temperature_c=temperature_c, moisture_pct=moisture_pct, moisture_kind=moisture_kind,
                             lat=lat, lon=lon, signature=signature, is_simulated=is_simulated)
    db.add(r)
    db.commit()
    return r


def _leaf(r: models.SensorReading) -> str:
    return canonical({"id": r.id, "d": r.device_id, "t": _iso(r.recorded_at), "c": r.temperature_c,
                      "m": r.moisture_pct, "k": r.moisture_kind, "s": r.signature})


def analyse_readings(crop: str, readings: list[models.SensorReading]) -> dict:
    rules = COLD_CHAIN_RULES.get(crop)
    temps = [r.temperature_c for r in readings if r.temperature_c is not None]
    rhs = [r.moisture_pct for r in readings if r.moisture_pct is not None and r.moisture_kind == "rh"]
    prod = [r.moisture_pct for r in readings if r.moisture_pct is not None and r.moisture_kind == "product"]
    out = {"n_readings": len(readings),
           "simulated_readings": sum(1 for r in readings if getattr(r, "is_simulated", False)),
           "temp_c": {"min": min(temps), "max": max(temps), "avg": round(sum(temps) / len(temps), 2)} if temps else None,
           "rh_pct": {"min": min(rhs), "max": max(rhs)} if rhs else None,
           "product_moisture_pct": {"min": min(prod), "max": max(prod)} if prod else None,
           "temp_excursions": 0, "rh_excursions": 0, "minutes_out_of_temp_range": 0.0}
    if rules is None or not readings:
        out["status"] = "no_rules" if rules is None else "no_data"
        return out
    lo, hi = rules["temp_c"]
    rlo, rhi = rules["rh_pct"]
    ordered = sorted((r for r in readings if r.temperature_c is not None), key=lambda r: r.recorded_at)
    for a, b in zip(ordered, ordered[1:]):
        if not lo <= a.temperature_c <= hi:   # attribute the interval to the earlier reading's state
            out["minutes_out_of_temp_range"] += (b.recorded_at - a.recorded_at).total_seconds() / 60
    out["temp_excursions"] = sum(1 for t in temps if not lo <= t <= hi)
    out["rh_excursions"] = sum(1 for h in rhs if not rlo <= h <= rhi)
    out["minutes_out_of_temp_range"] = round(out["minutes_out_of_temp_range"], 1)
    mmax = rules.get("product_moisture_max_pct")
    prod_bad = bool(mmax and prod and max(prod) > mmax)
    out["product_moisture_exceeded"] = prod_bad
    out["status"] = "ok" if not (out["temp_excursions"] or out["rh_excursions"] or prod_bad) else "excursion"
    out["rules_note"] = "Illustrative ranges; configure per variety."
    return out


# ---------------------------------------------------------------- threshold alerts
# Generic fallbacks for crops with no entry in COLD_CHAIN_RULES above.
# ILLUSTRATIVE defaults -- configurable per batch later.
DEFAULT_TEMP_C = (0.0, 30.0)
DEFAULT_RH_PCT = (40.0, 95.0)


def alert_thresholds(crop: str) -> dict:
    """Thresholds for a crop: its COLD_CHAIN_RULES entry, else generic defaults."""
    rules = COLD_CHAIN_RULES.get((crop or "").lower())
    if rules is not None:
        return {"temperature_c": {"min": rules["temp_c"][0], "max": rules["temp_c"][1]},
                "rh_pct": {"min": rules["rh_pct"][0], "max": rules["rh_pct"][1]},
                "product_moisture_max_pct": rules.get("product_moisture_max_pct"),
                "source": f"crop_rules:{crop.lower()}",
                "note": "Illustrative thresholds; configurable per batch later."}
    return {"temperature_c": {"min": DEFAULT_TEMP_C[0], "max": DEFAULT_TEMP_C[1]},
            "rh_pct": {"min": DEFAULT_RH_PCT[0], "max": DEFAULT_RH_PCT[1]},
            "product_moisture_max_pct": None,
            "source": "generic_default",
            "note": "Illustrative thresholds; configurable per batch later."}


def _severity(metric: str, value: float, lo: float | None, hi: float | None) -> str:
    """'critical' for a large excursion, else 'warning'."""
    over = max(lo - value, value - hi) if lo is not None and hi is not None else (
        value - hi if hi is not None else 0.0)
    limit = 10.0 if metric == "temperature_c" else 20.0
    return "critical" if over > limit else "warning"


def alerts_for_readings(crop: str, readings: list[models.SensorReading]) -> dict:
    """One alert per out-of-range metric per reading (temperature + moisture)."""
    th = alert_thresholds(crop)
    tlo, thi = th["temperature_c"]["min"], th["temperature_c"]["max"]
    rlo, rhi = th["rh_pct"]["min"], th["rh_pct"]["max"]
    pmax = th["product_moisture_max_pct"]
    alerts: list[dict] = []
    for r in readings:
        if r.temperature_c is not None and not tlo <= r.temperature_c <= thi:
            alerts.append({"reading_id": r.id, "recorded_at": _iso(r.recorded_at),
                           "metric": "temperature_c", "value": r.temperature_c,
                           "threshold": {"min": tlo, "max": thi},
                           "simulated": bool(getattr(r, "is_simulated", False)),
                           "severity": _severity("temperature_c", r.temperature_c, tlo, thi)})
        if r.moisture_pct is not None:
            if r.moisture_kind == "product":
                if pmax is not None and r.moisture_pct > pmax:
                    alerts.append({"reading_id": r.id, "recorded_at": _iso(r.recorded_at),
                                   "metric": "moisture_pct", "value": r.moisture_pct,
                                   "threshold": {"max": pmax},
                                   "simulated": bool(getattr(r, "is_simulated", False)),
                                   "severity": _severity("moisture_pct", r.moisture_pct, None, pmax)})
            elif not rlo <= r.moisture_pct <= rhi:
                alerts.append({"reading_id": r.id, "recorded_at": _iso(r.recorded_at),
                               "metric": "moisture_pct", "value": r.moisture_pct,
                               "threshold": {"min": rlo, "max": rhi},
                               "simulated": bool(getattr(r, "is_simulated", False)),
                               "severity": _severity("moisture_pct", r.moisture_pct, rlo, rhi)})
    return {"alerts": alerts, "thresholds": th}


def compute_alerts(db: Session, batch: models.Batch) -> dict:
    """Threshold alerts over ALL stored readings for a batch (sealed or not)."""
    readings = (db.query(models.SensorReading).filter_by(batch_id=batch.id)
                .order_by(models.SensorReading.recorded_at).all())
    out = alerts_for_readings(batch.crop, readings)
    out["batch_code"] = batch.batch_code
    out["n_readings"] = len(readings)
    return out


def seal_readings(db: Session, batch: models.Batch, actor_id: int | None = None) -> models.LedgerBlock | None:
    """Commit all unsealed readings into the chain (Merkle root + summary). Returns None if nothing to seal."""
    pending = (db.query(models.SensorReading).filter_by(batch_id=batch.id, sealed=False)
               .order_by(models.SensorReading.id).all())
    if not pending:
        return None
    payload = {"first_reading_id": pending[0].id, "last_reading_id": pending[-1].id, "count": len(pending),
               "merkle_root": merkle_root([_leaf(r) for r in pending]),
               "summary": analyse_readings(batch.crop, pending)}
    blk = append_block(db, batch, "sensor_seal", actor_id, payload)
    for r in pending:
        r.sealed = True
    db.commit()
    return blk


# ---------------------------------------------------------------- verification
def verify_chain(db: Session, batch: models.Batch) -> dict:
    blocks = db.query(models.LedgerBlock).filter_by(batch_id=batch.id).order_by(models.LedgerBlock.idx).all()
    problems: list[dict] = []
    prev = GENESIS
    for expected_idx, b in enumerate(blocks):
        if b.idx != expected_idx:
            problems.append({"block": b.idx, "problem": "missing or out-of-order block"})
        if b.prev_hash != prev:
            problems.append({"block": b.idx, "problem": "prev_hash does not match previous block"})
        if b.block_hash != block_hash(b.idx, b.timestamp, b.event_type, b.actor_user_id, b.payload, b.prev_hash):
            problems.append({"block": b.idx, "problem": "block content does not match its hash"})
        if b.event_type == "sensor_seal":
            p = json.loads(b.payload)
            rs = (db.query(models.SensorReading).filter(models.SensorReading.batch_id == batch.id,
                  models.SensorReading.id >= p["first_reading_id"], models.SensorReading.id <= p["last_reading_id"],
                  models.SensorReading.sealed.is_(True)).order_by(models.SensorReading.id).all())
            if len(rs) != p["count"] or merkle_root([_leaf(r) for r in rs]) != p["merkle_root"]:
                problems.append({"block": b.idx, "problem": "sealed sensor readings were altered, added or removed"})
        prev = b.block_hash
    unsealed = db.query(models.SensorReading).filter_by(batch_id=batch.id, sealed=False).count()
    return {"valid": not problems, "blocks": len(blocks), "head_hash": blocks[-1].block_hash if blocks else None,
            "problems": problems, "unsealed_readings": unsealed,
            "anchored_externally": any(b.anchor_ref and not b.anchor_ref.startswith("local:") for b in blocks)}


def anchor_head(db: Session, batch: models.Batch, provider: AnchorProvider | None = None) -> dict:
    provider = provider or LocalAnchor()
    head = _last_block(db, batch.id)
    ref = provider.anchor(batch.batch_code, head.block_hash)
    head.anchor_ref = ref
    db.commit()
    return {"provider": provider.name, "reference": ref, "head_hash": head.block_hash,
            "external": not ref.startswith("local:")}


# ---------------------------------------------------------------- consumer view
def public_view(db: Session, batch: models.Batch) -> dict:
    """Consumer-facing provenance. Deliberately omits user ids, names, phone numbers and raw coordinates."""
    blocks = db.query(models.LedgerBlock).filter_by(batch_id=batch.id).order_by(models.LedgerBlock.idx).all()
    timeline = []
    for b in blocks:
        if b.event_type == "sensor_seal":
            s = json.loads(b.payload)["summary"]
            timeline.append({"time": b.timestamp, "event": "cold_chain_check", "readings": s["n_readings"],
                             "status": s.get("status"), "temp_c": s.get("temp_c")})
        else:
            timeline.append({"time": b.timestamp, "event": b.event_type})
    sealed = (db.query(models.SensorReading).filter_by(batch_id=batch.id, sealed=True)
              .order_by(models.SensorReading.recorded_at).all())
    cold = analyse_readings(batch.crop, sealed)
    v = verify_chain(db, batch)
    return {"batch_code": batch.batch_code, "crop": batch.crop, "variety": batch.variety,
            "origin_district": batch.origin_district,
            "harvested_at": _iso(batch.harvested_at) if batch.harvested_at else None,
            "timeline": timeline, "cold_chain": cold,
            "integrity": {"chain_valid": v["valid"], "blocks": v["blocks"], "head_hash": v["head_hash"],
                          "unsealed_readings": v["unsealed_readings"],
                          "externally_anchored": v["anchored_externally"],
                          "note": ("Hash-chained and signature-checked. Not yet anchored to an external ledger."
                                   if not v["anchored_externally"] else "Head hash anchored to an external ledger.")}}
