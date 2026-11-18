import io
import json
import re
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..config import CROPS, env
from ..database import get_db
from ..security import get_current_user, require_role
from ..services import twin as T

router = APIRouter(prefix="/api/v1/twin", tags=["digital-twin"])


class BatchIn(BaseModel):
    crop: str
    origin_district: str = Field(min_length=1, max_length=100)
    quantity_kg: float = Field(gt=0)
    variety: str = Field("", max_length=80)
    harvested_at: datetime | None = None
    order_id: int | None = None


class EventIn(BaseModel):
    event_type: str
    data: dict = Field(default_factory=dict)


class ReadingIn(BaseModel):
    device_id: str
    recorded_at: datetime
    temperature_c: float | None = None
    moisture_pct: float | None = None
    moisture_kind: str = "rh"
    signature: str
    # True only for readings produced by scripts/simulate_sensors.py. Simulated
    # readings are stored with is_simulated=True and labelled SIMULATED everywhere.
    simulated: bool = False
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


def _batch(db: Session, code: str) -> models.Batch:
    b = db.query(models.Batch).filter_by(batch_code=code).first()
    if not b:
        raise HTTPException(404, "Batch not found")
    return b


def _owned(db: Session, code: str, user) -> models.Batch:
    b = _batch(db, code)
    if b.farmer_id != user.id:
        raise HTTPException(403, "Not your batch")
    return b


@router.post("/batches")
def create(data: BatchIn, db: Session = Depends(get_db), user=Depends(require_role("farmer"))):
    if data.crop.lower() not in CROPS:
        raise HTTPException(400, f"Unsupported crop; choose from {sorted(CROPS)}")
    if data.order_id is not None:
        o = db.get(models.Order, data.order_id)
        if not o or o.farmer_id != user.id:
            raise HTTPException(404, "Order not found")
    b = T.create_batch(db, user.id, data.crop, data.origin_district, data.quantity_kg, data.harvested_at,
                       data.variety, data.order_id)
    return {"batch_code": b.batch_code, "public_url": f"/api/v1/twin/public/{b.batch_code}"}


@router.get("/batches/mine")
def mine(db: Session = Depends(get_db), user=Depends(require_role("farmer"))):
    rows = db.query(models.Batch).filter_by(farmer_id=user.id).order_by(models.Batch.created_at.desc()).all()
    return [{"batch_code": b.batch_code, "crop": b.crop, "quantity_kg": b.quantity_kg,
             "created_at": b.created_at} for b in rows]


@router.post("/batches/{code}/events")
def event(code: str, data: EventIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    b = _batch(db, code)
    try:
        blk = T.add_event(db, b, user, data.event_type, data.data)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except T.TwinError as e:
        raise HTTPException(400, str(e))
    return {"index": blk.idx, "block_hash": blk.block_hash}


@router.post("/batches/{code}/devices")
def device(code: str, label: str = "", db: Session = Depends(get_db), user=Depends(require_role("farmer"))):
    return T.register_device(db, _owned(db, code, user), label)


@router.post("/readings")
def reading(data: ReadingIn, db: Session = Depends(get_db)):
    """Device endpoint: authenticated by HMAC signature, not by user login."""
    try:
        r = T.ingest_reading(db, data.device_id, data.recorded_at.replace(tzinfo=None), data.temperature_c,
                             data.moisture_pct, data.moisture_kind, data.signature, data.lat, data.lon,
                             is_simulated=data.simulated)
    except PermissionError as e:
        raise HTTPException(401, str(e))
    except T.TwinError as e:
        raise HTTPException(400, str(e))
    return {"accepted": True, "reading_id": r.id}


@router.post("/batches/{code}/seal")
def seal(code: str, db: Session = Depends(get_db), user=Depends(require_role("farmer"))):
    blk = T.seal_readings(db, _owned(db, code, user), user.id)
    return {"sealed": blk is not None, "block_index": blk.idx if blk else None,
            "summary": json.loads(blk.payload)["summary"] if blk else None}


@router.post("/batches/{code}/anchor")
def anchor(code: str, db: Session = Depends(get_db), user=Depends(require_role("farmer"))):
    return T.anchor_head(db, _owned(db, code, user))


@router.get("/batches/{code}/verify")
def verify(code: str, db: Session = Depends(get_db)):
    return T.verify_chain(db, _batch(db, code))


_SAFE_HOST_RE = re.compile(r"^[A-Za-z0-9.\-\[\]:]+$")


def _forwarded_proto(request: Request) -> str | None:
    """First X-Forwarded-Proto value, if it is http/https, else None."""
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return proto if proto in ("http", "https") else None


def _referer_origin(request: Request) -> str | None:
    """Origin of the Referer header, strictly validated, else None.

    http/https only, hostname chars only (same rule as X-Forwarded-Host),
    no userinfo, ports allowed (dev). The path/query of a full-URL Referer
    are discarded — only scheme + host (+ port) are used.
    """
    ref = request.headers.get("referer", "").strip()
    if not ref:
        return None
    try:
        parts = urlsplit(ref)
        parts.port  # raises ValueError on a non-numeric port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    if "@" in parts.netloc or not parts.hostname:
        return None
    if len(parts.netloc) > 253 or not _SAFE_HOST_RE.match(parts.netloc):
        return None
    return f"{parts.scheme}://{parts.netloc}"


def _public_base_url(request: Request) -> str:
    """Base URL encoded in batch QR codes.

    Precedence: explicit PUBLIC_BASE_URL env var if set and non-empty, else
    the origin of the Referer header, else X-Forwarded-Host when a
    proxy/tunnel set it, else the host the client actually reached
    (request.base_url). There is no localhost default — a QR scanned from a
    phone must never point at the phone's own localhost.

    Why the Referer first: the browser fetches the QR <img> same-origin and
    sends a Referer header, so the browser itself reports the page's real
    address — no tunnel cooperation needed. The app's Referrer-Policy is
    strict-origin-when-cross-origin (main.py), so at least the origin is
    always present. This matters because the earlier X-Forwarded-Host fix
    did NOT solve it live: the VS Code devtunnel evidently does not set
    X-Forwarded-Host (that fix only verified the header passes through the
    vite proxy *if* set, not that the tunnel sets it). Referer is now the
    primary dynamic source; X-Forwarded-Host stays as a fallback for edges
    that do set it (Caddy sets it, so this also covers production when
    PUBLIC_BASE_URL is unset).

    Why not the Host header itself: it never survives the dev chain — the
    devtunnel relay rewrites it to localhost by default (Microsoft docs:
    "the dev tunnel relay will rewrite the http host header to be
    localhost"), and the vite dev proxy rewrites it again to 127.0.0.1:8000
    (changeOrigin). So request.base_url is always http://127.0.0.1:8000 in
    dev, and a QR built from it always encodes localhost.

    Scheme: uvicorn only ever sees plain http — the TLS is terminated by
    whatever sits in front. A Referer origin carries its own scheme. For a
    forwarded host the scheme comes from X-Forwarded-Proto when set; a
    forwarded host with no proto defaults to https (every edge we support
    — devtunnel, Caddy auto-HTTPS, Railway/Render — is https).

    Trust: these headers only affect this QR string — never auth or rate
    limiting (unlike X-Forwarded-For in _client_ip, which stays gated
    behind TRUST_PROXY). A spoofed Referer or X-Forwarded-Host yields a QR
    pointing at the attacker's own host, which they could generate with any
    free QR tool anyway; the PNG carries no provenance. Malformed values
    (anything but hostname chars, e.g. a path or @) are ignored.
    """
    base = env("PUBLIC_BASE_URL")
    if base:
        return base.rstrip("/")
    referer = _referer_origin(request)
    if referer:
        return referer
    fwd_host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    if fwd_host and len(fwd_host) <= 253 and _SAFE_HOST_RE.match(fwd_host):
        proto = _forwarded_proto(request) or "https"
        return f"{proto}://{fwd_host}"
    url = urlsplit(str(request.base_url))
    proto = _forwarded_proto(request)
    if proto:
        url = url._replace(scheme=proto)
    return urlunsplit(url).rstrip("/")


@router.get("/batches/{code}/qr")
def batch_qr(code: str, request: Request, db: Session = Depends(get_db)):
    """PNG QR code encoding the public verify URL for this batch. No login required.

    Base URL precedence: explicit PUBLIC_BASE_URL env var if set and non-empty,
    else the origin of the Referer header (the browser reports the page's real
    address when it fetches this <img> same-origin), else X-Forwarded-Host,
    else the host the client actually reached (request.base_url), with the
    scheme from X-Forwarded-Proto when a TLS-terminating proxy set it (see
    _public_base_url). There is no localhost default — a QR scanned from a
    phone must never point at the phone's own localhost.
    """
    b = _batch(db, code)
    try:
        import qrcode
    except ImportError:
        raise HTTPException(503, "qrcode is not installed. Install requirements.txt (qrcode[pil]).")
    base = _public_base_url(request)
    url = f"{base}/verify/{b.batch_code}"
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    # Never cache: the encoded host changes with PUBLIC_BASE_URL / the request
    # host, and a cached localhost QR would keep pointing phones at localhost
    # long after the config was fixed.
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/batches/{code}/alerts")
def alerts(code: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Threshold alerts from stored sensor readings. Batch farmer or admin only."""
    b = _batch(db, code)
    if user.role != "admin" and b.farmer_id != user.id:
        raise HTTPException(403, "Not your batch")
    return T.compute_alerts(db, b)


@router.get("/public/{code}")
def public(code: str, request: Request, db: Session = Depends(get_db)):
    view = T.public_view(db, _batch(db, code))
    view["qr_url"] = f"/api/v1/twin/batches/{code}/qr"
    # The exact URL the QR encodes, resolved by the same resolver — shown in
    # the UI so the user can see what the QR points at without scanning it.
    view["verify_url"] = f"{_public_base_url(request)}/verify/{code}"
    return view
