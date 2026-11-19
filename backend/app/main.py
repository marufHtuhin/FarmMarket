import importlib
import logging
import os
import pkgutil
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text, update, case, func
from sqlalchemy.orm import selectinload
from dotenv import load_dotenv
from .config import upload_dir, utcnow
from .database import Base, engine, get_db, escape_like
from . import models, schemas
from . import routers as routers_pkg
from .security import (hash_password, verify_password, create_access_token,
                       get_current_user, require_role, hash_token,
                       issue_refresh_token, revoke_all_refresh_tokens)
from .services.audit import log_audit
from .services.matching import calculate_match
from .services import price_labels as _price_labels
from .services.rate_limit import login_limiter, register_limiter, forgot_limiter
from .services.scheduler import start_scheduler, stop_scheduler

load_dotenv()
# Uvicorn configures only its own loggers, so without this the app's
# INFO logs (e.g. assistant stream latency) would be silently dropped;
# only WARNING+ reaches stderr via the last-resort handler. basicConfig
# is a no-op when a logging config already attached a root handler.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Known demo/placeholder secrets that must never sign tokens in production.
# (security.py separately rejects its own dev default and short keys.)
DEMO_SECRET_KEYS = frozenset({
    "replace-this-with-a-long-random-secret-key",
    "demo-only-change-me-in-production",
    "dev-only-change-this-secret",
})


def validate_production_config(environment=None, secret_key=None,
                               database_url=None):
    """Fail fast in production on unsafe config. Pure function of its
    arguments (None = read from the environment) so tests can call it
    directly without importing this module under a production env.

    Raises RuntimeError when ENVIRONMENT=production and: SECRET_KEY is
    missing, shorter than 32 chars, or a known demo value; or DATABASE_URL
    is SQLite (the demo fallback must never serve production traffic).
    In any other environment it is a no-op.
    """
    env = (environment if environment is not None
           else os.getenv("ENVIRONMENT", "development")).lower()
    if env != "production":
        return
    key = secret_key if secret_key is not None else os.getenv("SECRET_KEY", "")
    if not key or len(key) < 32:
        raise RuntimeError(
            "Refusing to start in production: SECRET_KEY must be set and at "
            "least 32 characters long.")
    if key in DEMO_SECRET_KEYS:
        raise RuntimeError(
            "Refusing to start in production: SECRET_KEY is a known demo value.")
    db_url = (database_url if database_url is not None
              else os.getenv("DATABASE_URL", ""))
    if db_url.startswith("sqlite"):
        raise RuntimeError(
            "Refusing to start in production: DATABASE_URL points at SQLite; "
            "configure MySQL.")


def get_cors_origins(environment=None, raw_origins=None):
    """Compute the CORS allow-list. Pure function of its arguments (None =
    read from the environment) so tests can call it directly.

    Production fail-closed: a "*" in FRONTEND_ORIGINS refuses to start
    (credentials + wildcard is never safe), and an unset FRONTEND_ORIGINS
    yields an empty allow-list (same-origin only — the API serves the SPA
    itself in production). Development keeps the historical default.
    """
    env = (environment if environment is not None
           else os.getenv("ENVIRONMENT", "development")).lower()
    raw = (raw_origins if raw_origins is not None
           else os.getenv("FRONTEND_ORIGINS"))
    if raw is None:
        return [] if env == "production" else ["http://127.0.0.1:5500",
                                               "http://localhost:5500"]
    origins = [x.strip() for x in raw.split(",") if x.strip()]
    if env == "production" and "*" in origins:
        raise RuntimeError(
            "Refusing to start in production: FRONTEND_ORIGINS must not "
            "contain '*' (list the exact origins instead).")
    return origins


def docs_enabled(environment=None):
    """Whether the interactive API docs (/docs, /redoc, /openapi.json) are
    served. Disabled in production: the docs expose the full API surface
    and are not needed by the SPA. Pure function of its argument (None =
    read from the environment) so tests can call it directly."""
    env = (environment if environment is not None
           else os.getenv("ENVIRONMENT", "development")).lower()
    return env != "production"


validate_production_config()
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: the in-app scheduler starts here when enabled
    (SCHEDULER_ENABLED=true). The scheduler module itself refuses to start
    under pytest, so tests constructing this app never spawn background jobs."""
    start_scheduler()
    yield
    stop_scheduler()


_docs = docs_enabled()
app = FastAPI(title="FARMMARKET API", version="1.1.0",
              description="Demand-driven agricultural marketplace.",
              lifespan=lifespan,
              docs_url="/docs" if _docs else None,
              redoc_url="/redoc" if _docs else None,
              openapi_url="/openapi.json" if _docs else None)
app.add_middleware(CORSMiddleware, allow_origins=get_cors_origins(),
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Baseline security headers on every response.

    No Content-Security-Policy is set here: the SPA loads Leaflet tiles from
    *.tile.openstreetmap.org, Google Fonts, and Recharts/Tailwind inline
    styles, so a wrong CSP would break the demo UI — and a CSP cannot be
    proven safe without running the built SPA. Add one (with a Playwright
    smoke pass) as a follow-up, not blind.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # microphone=(self): Krishi Bondhu voice input uses the Web Speech API,
    # which needs microphone permission. This middleware also serves the SPA
    # HTML in production, so microphone=() would silently break voice input
    # for every deployed user (dev is unaffected — vite serves the HTML
    # there, without this header). camera stays blocked: no getUserMedia
    # anywhere (image attach is a plain file input, no capture attribute);
    # geolocation is unused.
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last-resort 500: generic detail to the client, full traceback in the
    server log. HTTPException is NOT swallowed — Starlette dispatches it to
    its own handler first, so 404/401/422 shapes are unchanged."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    """Liveness + DB reachability. 200 when the DB answers SELECT 1, else
    503 with status "degraded" so a load balancer stops sending traffic."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.warning("Health check: database unreachable")
        return JSONResponse(status_code=503,
                            content={"status": "degraded", "project": "FARMMARKET",
                                     "db": "unreachable"})
    return {"status": "ok", "project": "FARMMARKET", "db": "ok"}

# Dummy bcrypt hash for the login timing defence (see login()): hashing a
# random value once at startup is never a real credential — it only exists
# so an unknown-email login costs the same ~1s bcrypt verify as a real one.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate limiting.

    X-Forwarded-For is client-controlled text: trusting it unconditionally
    lets anyone rotate IPs and defeat the login rate limiter (verified live
    in the P10 audit). It is therefore honoured ONLY when TRUST_PROXY=true
    (the deployment runs behind a proxy that sets the header itself, e.g.
    the Caddy in docker-compose.prod.yml), and even then only the LAST hop
    is used — the one the trusted proxy appended. Caddy >= 2.5 discards a
    client-supplied X-Forwarded-For and writes a single entry, so last ==
    first there; with an appending proxy the last entry is still the real
    peer. Without TRUST_PROXY the direct TCP peer is the only trustworthy
    value, so it is used.
    """
    if os.getenv("TRUST_PROXY", "false").lower() == "true":
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _queue_verification_email(background_tasks, request, email, token):
    """Queue the registration-confirmation email via the mailer service
    (services/mailer.py).

    The import is lazy and ImportError-tolerant: if the mailer module is
    absent or unconfigured, registration still succeeds — the account is
    created and the user can request a resend later. The background task
    itself never raises: a send failure is logged, never surfaced to the
    caller (the response has already been sent by then anyway).
    Returns True when the send was queued, False otherwise.
    """
    try:
        from .services import mailer
        if not mailer.is_configured():
            raise RuntimeError("mailer not configured")
    except ImportError:
        _log_mailer_unavailable()
        return False
    except Exception:
        _log_mailer_unavailable()
        return False

    def _send():
        try:
            mailer.send_verification_email(email, token, request)
        except Exception:
            logger.warning("Verification email send failed; account still "
                           "created (user can resend from the app).",
                           exc_info=True)

    background_tasks.add_task(_send)
    return True


def _mailer_configured():
    """Whether the SMTP mailer is importable AND configured.

    Mirrors the check inside _queue_verification_email: a missing module
    or an unconfigured mailer both count as unconfigured, so the dev
    token fallback still applies when no email can be sent. Used to
    decide whether the plaintext verification/reset token may be
    returned in a dev response — when a mailer IS configured the inbox
    is the only delivery, exactly like production.
    """
    try:
        from .services import mailer
        return bool(mailer.is_configured())
    except Exception:
        return False


def _log_mailer_unavailable():
    """Warn when a verification email cannot be queued. Loud in production
    (same style as the forgot-password warning); in development the token
    is returned in the register response when no mailer is configured, so
    no mailer is expected there."""
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        logger.warning(
            "Verification email requested in production: no mailer "
            "configured; verification token generated but NOT delivered "
            "— wire an SMTP mailer (token never logged).")


@app.post("/api/v1/auth/register")
def register(data: schemas.RegisterIn, request: Request, background_tasks: BackgroundTasks, db: Session=Depends(get_db)):
    if not register_limiter.allow(_client_ip(request)):
        raise HTTPException(429, "Too many registrations from this address; please wait a minute and try again")
    if data.role not in ("farmer", "buyer", "transporter"):
        raise HTTPException(400, "Role must be farmer, buyer or transporter")
    if db.query(models.User).filter_by(email=data.email).first():
        raise HTTPException(409, "Email already registered")
    user = models.User(**{k:v for k,v in data.model_dump().items() if k != "password"},
                       password_hash=hash_password(data.password))
    db.add(user); db.commit(); db.refresh(user)
    log_audit(db, user.id, "user_registered", f"role={user.role}")
    # Email verification: issue a 24h token and queue the confirmation
    # email. Registration NEVER fails because email is down — the queue
    # helper swallows mailer errors, and the account is already created.
    token = secrets.token_urlsafe(48)
    db.add(models.EmailVerificationToken(user_id=user.id, token_hash=hash_token(token),
                                         expires_at=utcnow() + timedelta(hours=24)))
    db.commit()
    resp = {"access_token": create_access_token(user.id),
            "refresh_token": issue_refresh_token(db, user.id), "token_type":"bearer",
            "user": {"id":user.id,"name":user.name,"email":user.email,"role":user.role,
                     "district":user.district,"upazila":user.upazila,"phone":user.phone,
                     "email_verified":user.email_verified}}
    if (os.getenv("ENVIRONMENT", "development").lower() != "production"
            and not _mailer_configured()):
        # Dev-only fallback (mirrors forgot-password): the plaintext
        # token is returned ONLY when no mailer is configured, so the
        # flow stays testable without email. When a mailer IS
        # configured the inbox is the only delivery — returning the
        # token as well would let anyone verify any account with just
        # its email address. NEVER included in production.
        resp["verification_token"] = token
    _queue_verification_email(background_tasks, request, user.email, token)
    return resp

@app.post("/api/v1/auth/login")
def login(data: schemas.LoginIn, request: Request, db: Session=Depends(get_db)):
    if not login_limiter.allow(_client_ip(request)):
        raise HTTPException(429, "Too many login attempts from this address; please wait a minute and try again")
    user = db.query(models.User).filter_by(email=data.email).first()
    # Always run a bcrypt verify, even for an unknown email, so the
    # response time does not reveal whether the account exists (a dummy
    # hash is verified instead — it can never match a real password).
    ok = verify_password(data.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not user or not ok:
        log_audit(db, user.id if user else None, "login_failed", f"email={data.email}")
        raise HTTPException(401, "Incorrect email or password")
    return {"access_token":create_access_token(user.id),
            "refresh_token":issue_refresh_token(db, user.id),"token_type":"bearer",
            "user":{"id":user.id,"name":user.name,"email":user.email,"role":user.role,
                    "district":user.district,"upazila":user.upazila,"phone":user.phone,
                    "email_verified":user.email_verified}}

@app.post("/api/v1/auth/refresh")
def refresh(data: schemas.RefreshIn, db: Session=Depends(get_db)):
    """Rotate a refresh token: the presented token is revoked and a new pair
    is issued. Presenting an already-revoked token is treated as theft: all
    of the user's refresh tokens are revoked and a 401 is returned."""
    rec = db.query(models.RefreshToken).filter_by(token_hash=hash_token(data.refresh_token)).first()
    if not rec:
        raise HTTPException(401, "Invalid refresh token")
    if rec.revoked:
        revoke_all_refresh_tokens(db, rec.user_id)
        raise HTTPException(401, "Invalid refresh token")
    if rec.expires_at < utcnow():
        rec.revoked = True
        db.commit()
        raise HTTPException(401, "Refresh token expired")
    rec.revoked = True
    db.commit()
    new_refresh = issue_refresh_token(db, rec.user_id)
    return {"access_token": create_access_token(rec.user_id),
            "refresh_token": new_refresh, "token_type": "bearer"}

@app.post("/api/v1/auth/logout")
def logout(data: schemas.LogoutIn, db: Session=Depends(get_db)):
    """Revoke one refresh token. Always returns 200, even for unknown tokens."""
    rec = db.query(models.RefreshToken).filter_by(token_hash=hash_token(data.refresh_token)).first()
    if rec and not rec.revoked:
        rec.revoked = True
        db.commit()
    return {"message": "Logged out"}

@app.post("/api/v1/auth/forgot-password")
def forgot_password(data: schemas.ForgotPasswordIn, request: Request, background: BackgroundTasks, db: Session=Depends(get_db)):
    """Request a password reset. Always returns 200 (no user enumeration):
    an attacker cannot tell whether the email is registered.

    Rate-limited per IP (5/min): without it the endpoint can be used to
    flood the reset-token table and, in non-production with no mailer
    configured, to harvest reset tokens for arbitrary accounts (the
    token is returned in the response outside production ONLY when no
    mailer is configured, by design, so the flow is testable without a
    mailer — see below).

    Demo/testing behaviour: when ENVIRONMENT != production AND no mailer
    is configured, the response ALSO includes the plaintext `reset_token`
    so the flow can be exercised without an email/SMS sender. When a
    mailer IS configured the inbox is the only delivery, exactly like
    production — returning the token as well would let anyone reset any
    account with just its email address. In production the token is
    NEVER included in the response — it must be delivered out-of-band
    (email/SMS). The token is a random value, stored only as a SHA-256
    hash, valid for 1 hour.
    """
    if not forgot_limiter.allow(_client_ip(request)):
        raise HTTPException(429, "Too many password reset requests from this address; please wait a minute and try again")
    user = db.query(models.User).filter_by(email=data.email).first()
    resp = {"message": "If an account exists for this email, a reset link has been sent."}
    if user:
        token = secrets.token_urlsafe(48)
        # Invalidate any earlier unused reset tokens for this user.
        db.query(models.PasswordResetToken).filter_by(user_id=user.id, used=False).update({"used": True})
        db.add(models.PasswordResetToken(user_id=user.id, token_hash=hash_token(token),
                                         expires_at=utcnow() + timedelta(hours=1)))
        db.commit()
        from .services import mailer  # lazy import: keeps this module's import graph light
        if (os.getenv("ENVIRONMENT", "development").lower() != "production"
                and not mailer.is_configured()):
            # Dev-only fallback: the token is returned ONLY when no
            # mailer is configured. With a mailer the inbox is the only
            # delivery (see the docstring above).
            resp["reset_token"] = token
        if mailer.is_configured():
            # BackgroundTasks runs sync callables in a threadpool, so the
            # send never blocks (or fails) the response. Queued in both dev
            # and production whenever a mailer is configured.
            background.add_task(mailer.send_password_reset_email,
                                data.email, token, request)
        elif os.getenv("ENVIRONMENT", "development").lower() == "production":
            # No mailer is configured: the token is generated and stored but
            # NOT delivered to the user in production. Loud warning so this
            # is wired up (SMTP) before real users depend on password reset.
            logger.warning(
                "Password reset requested in production for a registered "
                "account: no mailer configured; reset token generated but "
                "NOT delivered — wire an SMTP mailer (token never logged).")
    return resp

@app.post("/api/v1/auth/reset-password")
def reset_password(data: schemas.ResetPasswordIn, db: Session=Depends(get_db)):
    rec = db.query(models.PasswordResetToken).filter_by(
        token_hash=hash_token(data.token), used=False).first()
    if not rec or rec.expires_at < utcnow():
        raise HTTPException(400, "Invalid or expired reset token")
    user = db.query(models.User).filter_by(id=rec.user_id).first()
    if not user:
        raise HTTPException(400, "Invalid or expired reset token")
    rec.used = True
    user.password_hash = hash_password(data.new_password)
    db.commit()
    revoke_all_refresh_tokens(db, user.id)
    return {"message": "Password has been reset"}

@app.post("/api/v1/auth/verify-email")
def verify_email(data: schemas.VerifyEmailIn, db: Session=Depends(get_db)):
    """Confirm a registration with the token from the verification email.
    Marks the account's email_verified flag and invalidates the token.
    400 on an invalid, expired or already-used token (same shape as the
    password-reset endpoint)."""
    rec = db.query(models.EmailVerificationToken).filter_by(
        token_hash=hash_token(data.token), used=False).first()
    if not rec or rec.expires_at < utcnow():
        raise HTTPException(400, "Invalid or expired verification token")
    user = db.query(models.User).filter_by(id=rec.user_id).first()
    if not user:
        raise HTTPException(400, "Invalid or expired verification token")
    rec.used = True
    user.email_verified = True
    db.commit()
    log_audit(db, user.id, "email_verified", "")
    return {"verified": True}

@app.post("/api/v1/auth/resend-verification")
def resend_verification(request: Request, background_tasks: BackgroundTasks, db: Session=Depends(get_db), user=Depends(get_current_user)):
    """Send a fresh verification email to the logged-in user. Invalidates
    any earlier unused tokens first. Rate-limited per user (5/min).
    Already-verified users get a harmless success message, not an error."""
    # Lazy import keeps this endpoint's diff localized.
    from .services.rate_limit import resend_limiter
    if not resend_limiter.allow(f"resend:{user.id}"):
        raise HTTPException(429, "Too many verification requests; please wait a minute and try again")
    if user.email_verified:
        return {"message": "Your email is already verified."}
    db.query(models.EmailVerificationToken).filter_by(user_id=user.id, used=False).update({"used": True})
    token = secrets.token_urlsafe(48)
    db.add(models.EmailVerificationToken(user_id=user.id, token_hash=hash_token(token),
                                         expires_at=utcnow() + timedelta(hours=24)))
    db.commit()
    _queue_verification_email(background_tasks, request, user.email, token)
    return {"message": "Verification email sent. Check your inbox."}

@app.get("/api/v1/auth/me")
def me(user=Depends(get_current_user)):
    return {"id":user.id,"name":user.name,"email":user.email,"role":user.role,
            "district":user.district,"upazila":user.upazila,"phone":user.phone,
            "email_verified":user.email_verified}

@app.get("/api/v1/products")
def products(search:str="", district:str="", db:Session=Depends(get_db)):
    q=db.query(models.Product).filter_by(status="available").options(selectinload(models.Product.farmer))
    if search: q=q.filter(models.Product.name.ilike(escape_like(search), escape="\\"))
    if district: q=q.filter(models.Product.district.ilike(escape_like(district), escape="\\"))
    return [{"id":p.id,"farmer_id":p.farmer_id,"farmer_name":p.farmer.name,"name":p.name,
             "quantity":p.quantity,"unit":p.unit,"price_per_unit":p.price_per_unit,
             "district":p.district,"description":p.description,"image_url":p.image_url}
            for p in q.order_by(models.Product.created_at.desc()).all()]

@app.post("/api/v1/products")
def add_product(data:schemas.ProductIn, db:Session=Depends(get_db), user=Depends(require_role("farmer"))):
    if data.farm_id is not None:
        farm=db.query(models.Farm).filter_by(id=data.farm_id).first()
        if not farm: raise HTTPException(404,"Farm not found")
        if farm.farmer_id != user.id: raise HTTPException(403,"Not your farm")
    p=models.Product(farmer_id=user.id,**data.model_dump())
    db.add(p); db.commit(); db.refresh(p)
    return {"message":"Product listed","id":p.id}

@app.put("/api/v1/products/{pid}")
def edit_product(pid:int,data:schemas.ProductIn,db:Session=Depends(get_db),user=Depends(require_role("farmer"))):
    p=db.query(models.Product).filter_by(id=pid).first()
    if not p: raise HTTPException(404,"Product not found")
    if p.farmer_id != user.id: raise HTTPException(403,"Not your product")
    if data.farm_id is not None:
        farm=db.query(models.Farm).filter_by(id=data.farm_id).first()
        if not farm: raise HTTPException(404,"Farm not found")
        if farm.farmer_id != user.id: raise HTTPException(403,"Not your farm")
    for k,v in data.model_dump().items(): setattr(p,k,v)
    db.commit()
    return {"message":"Updated"}

@app.delete("/api/v1/products/{pid}")
def remove_product(pid:int,db:Session=Depends(get_db),user=Depends(require_role("farmer"))):
    p=db.query(models.Product).filter_by(id=pid).first()
    if not p: raise HTTPException(404,"Product not found")
    if p.farmer_id != user.id: raise HTTPException(403,"Not your product")
    p.status="removed"; db.commit()
    return {"message":"Removed"}

@app.get("/api/v1/demands")
def demands(db:Session=Depends(get_db),user=Depends(get_current_user)):
    q=db.query(models.Demand).filter_by(status="open").options(selectinload(models.Demand.buyer))
    if user.role=="buyer": q=q.filter_by(buyer_id=user.id)
    return [{"id":d.id,"buyer_id":d.buyer_id,"buyer_name":d.buyer.name,
             "product_name":d.product_name,"required_quantity":d.required_quantity,
             "unit":d.unit,"target_price":d.target_price,"district":d.district,
             "required_date":d.required_date,"notes":d.notes} for d in q.all()]

@app.post("/api/v1/demands")
def add_demand(data:schemas.DemandIn,db:Session=Depends(get_db),user=Depends(require_role("buyer"))):
    d=models.Demand(buyer_id=user.id,**data.model_dump())
    db.add(d); db.commit(); db.refresh(d)
    return {"message":"Demand published","id":d.id}

@app.get("/api/v1/matches")
def matches(db:Session=Depends(get_db),user=Depends(get_current_user)):
    ds=db.query(models.Demand).filter_by(status="open").options(selectinload(models.Demand.buyer)).all()
    ps=db.query(models.Product).filter_by(status="available").options(selectinload(models.Product.farmer)).all()
    result=[]
    for d in ds:
        if user.role=="buyer" and d.buyer_id!=user.id: continue
        for p in ps:
            if user.role=="farmer" and p.farmer_id!=user.id: continue
            m=calculate_match(d,p)
            if m and m["score"]>=50:
                result.append({"demand_id":d.id,"buyer_id":d.buyer_id,"buyer_name":d.buyer.name,"product_id":p.id,
                    "product_name":p.name,"farmer_id":p.farmer_id,"farmer_name":p.farmer.name,
                    "quantity":p.quantity,"required_quantity":d.required_quantity,"unit":p.unit,
                    "farmer_price":p.price_per_unit,"target_price":d.target_price,
                    "district":p.district,**m})
    return sorted(result,key=lambda x:x["score"],reverse=True)

@app.get("/api/v1/prices")
def prices(product_name:str="",district:str="",db:Session=Depends(get_db)):
    q=db.query(models.PriceRecord)
    if product_name:q=q.filter(models.PriceRecord.product_name.ilike(escape_like(product_name), escape="\\"))
    if district:q=q.filter(models.PriceRecord.district.ilike(escape_like(district), escape="\\"))
    out=[]
    for r in q.all():
        label=_price_labels.record_label(r.source)
        out.append({"id":r.id,"product_name":r.product_name,"district":r.district,
             "market_name":r.market_name,"price_per_unit":r.price_per_unit,
             "unit":r.unit,"source":r.source,"recorded_at":r.recorded_at,
             "label":label,
             "stale":_price_labels.is_stale(r.recorded_at, label=="demo")})
    return out

@app.post("/api/v1/orders")
def place_order(data:schemas.OrderIn,db:Session=Depends(get_db),user=Depends(require_role("buyer"))):
    p=db.query(models.Product).filter_by(id=data.product_id).with_for_update().first()
    if not p or p.status!="available": raise HTTPException(404,"Product unavailable")
    if p.farmer_id==user.id: raise HTTPException(400,"Cannot buy your own product")
    # Atomic conditional stock decrement prevents two buyers from reserving
    # the same remaining quantity concurrently (including on SQLite).
    stock_update=db.execute(
        update(models.Product)
        .where(models.Product.id==p.id,
               models.Product.status=="available",
               models.Product.quantity>=data.quantity)
        .values(
            quantity=models.Product.quantity-data.quantity,
            status=case(
                (models.Product.quantity-data.quantity<=0, "sold"),
                else_="available"
            )
        )
    )
    if stock_update.rowcount != 1:
        db.rollback()
        raise HTTPException(409,"Insufficient stock; refresh the listing and try again")
    db.refresh(p)
    order=models.Order(buyer_id=user.id,farmer_id=p.farmer_id,product_id=p.id,
        quantity=data.quantity,unit_price=p.price_per_unit,
        total_amount=round(data.quantity*p.price_per_unit,2),delivery_address=data.delivery_address)
    db.add(order)
    db.add(models.Notification(user_id=p.farmer_id,title="New order",
        message=f"{user.name} ordered {data.quantity} {p.unit} of {p.name}."))
    db.commit(); db.refresh(order)
    return {"message":"Order placed","order_id":order.id,"total_amount":order.total_amount}

@app.get("/api/v1/orders/my")
def my_orders(db:Session=Depends(get_db),user=Depends(get_current_user)):
    q=db.query(models.Order).options(selectinload(models.Order.product))
    if user.role=="farmer":q=q.filter_by(farmer_id=user.id)
    elif user.role=="buyer":q=q.filter_by(buyer_id=user.id)
    elif user.role=="transporter":q=q.filter_by(transporter_id=user.id)
    # Admins see every order (platform oversight); every other role is
    # scoped above. Previously transporters fell through unfiltered and
    # could list all orders (P10 audit finding).
    rows=q.order_by(models.Order.created_at.desc()).all()
    return [{"id":o.id,"product_name":o.product.name,"quantity":o.quantity,"unit":o.product.unit,
        "unit_price":o.unit_price,"total_amount":o.total_amount,"status":o.status,
        "created_at":o.created_at} for o in rows]

@app.patch("/api/v1/orders/{oid}/status")
def order_status(oid:int,data:schemas.StatusIn,db:Session=Depends(get_db),user=Depends(get_current_user)):
    o=db.query(models.Order).filter_by(id=oid).with_for_update().first()
    if not o: raise HTTPException(404,"Order not found")

    # Explicit state machine: only pending orders may be accepted/rejected/cancelled;
    # accepted orders may be marked completed by their farmer.
    if user.role=="farmer" and o.farmer_id==user.id:
        if o.status=="pending" and data.status in ("accepted","rejected"):
            pass
        elif o.status=="accepted" and data.status=="completed":
            # G4: never complete an order while its delivery is in progress —
            # the transporter completes it by marking it delivered. Completing
            # a not-yet-picked-up order (not_assigned/assigned) stays allowed.
            if o.delivery_status in ("picked_up", "in_transit"):
                raise HTTPException(400,"Delivery is in progress; the order completes when the transporter marks it delivered")
            pass
        else:
            raise HTTPException(400,"Invalid order status transition")
    elif user.role=="buyer" and o.buyer_id==user.id:
        if o.status=="pending" and data.status=="cancelled":
            pass
        else:
            raise HTTPException(400,"Buyer can only cancel a pending order")
    else:
        raise HTTPException(403,"Not allowed")

    # Stock is reserved when an order is placed. Release it exactly once if
    # the pending order is rejected or cancelled.
    if data.status in ("rejected","cancelled"):
        product=db.query(models.Product).filter_by(id=o.product_id).with_for_update().first()
        if product:
            product.quantity=round(product.quantity+o.quantity, 4)
            if product.status=="sold":
                product.status="available"
    o.status=data.status
    recipient_id=o.buyer_id if user.role=="farmer" else o.farmer_id
    db.add(models.Notification(user_id=recipient_id,title="Order updated",
        message=f"Order #{o.id}: {data.status}"))
    db.commit()
    return {"message":"Order updated","status":o.status}

@app.get("/api/v1/transporters")
def transporters(db:Session=Depends(get_db)):
    """Public transporter directory (no contact details) so farmers can pick
    a transporter when assigning a delivery."""
    users=db.query(models.User).filter_by(role="transporter").order_by(models.User.name).all()
    # One grouped count for all transporters (P12: was one COUNT query per
    # transporter — an N+1).
    counts = dict(db.query(models.Vehicle.transporter_id, func.count(models.Vehicle.id))
                  .group_by(models.Vehicle.transporter_id).all())
    return [{"id":u.id,"name":u.name,"business_name":u.business_name,"district":u.district,
             "is_verified":u.is_verified,
             "vehicle_count":counts.get(u.id, 0)}
            for u in users]

@app.get("/api/v1/orders/{oid}")
def order_detail(oid:int, db:Session=Depends(get_db), user=Depends(get_current_user)):
    o=db.query(models.Order).filter_by(id=oid).first()
    if not o: raise HTTPException(404,"Order not found")
    if user.role != "admin" and user.id not in (o.buyer_id, o.farmer_id, o.transporter_id):
        raise HTTPException(403,"Not your order")
    buyer=db.query(models.User).filter_by(id=o.buyer_id).first()
    farmer=db.query(models.User).filter_by(id=o.farmer_id).first()
    transporter=db.query(models.User).filter_by(id=o.transporter_id).first() if o.transporter_id else None
    return {"id":o.id,"product_id":o.product_id,"product_name":o.product.name,
        "quantity":o.quantity,"unit":o.product.unit,"unit_price":o.unit_price,
        "total_amount":o.total_amount,"status":o.status,
        "delivery_status":o.delivery_status,"delivery_address":o.delivery_address,
        "offer_id":o.offer_id,"proof_note":o.proof_note,"created_at":o.created_at,
        "buyer":{"id":buyer.id,"name":buyer.name} if buyer else None,
        "farmer":{"id":farmer.id,"name":farmer.name,"district":farmer.district} if farmer else None,
        "transporter":{"id":transporter.id,"name":transporter.name} if transporter else None}

@app.patch("/api/v1/notifications/{nid}/read")
def notification_read(nid:int, db:Session=Depends(get_db), user=Depends(get_current_user)):
    n=db.query(models.Notification).filter_by(id=nid, user_id=user.id).first()
    if not n: raise HTTPException(404,"Notification not found")
    n.is_read=True; db.commit()
    return {"message":"Marked read","id":n.id}

@app.post("/api/v1/notifications/read-all")
def notifications_read_all(db:Session=Depends(get_db), user=Depends(get_current_user)):
    count=db.query(models.Notification).filter_by(user_id=user.id, is_read=False).update({"is_read":True})
    db.commit()
    return {"message":"All marked read","updated":count}

@app.get("/api/v1/notifications")
def notifications(db:Session=Depends(get_db),user=Depends(get_current_user)):
    rows=db.query(models.Notification).filter_by(user_id=user.id).order_by(models.Notification.created_at.desc()).limit(30).all()
    return [{"id":n.id,"title":n.title,"message":n.message,"is_read":n.is_read,"created_at":n.created_at} for n in rows]

@app.get("/api/v1/dashboard")
def dashboard(db:Session=Depends(get_db),user=Depends(get_current_user)):
    if user.role=="farmer":
        ps=db.query(models.Product).filter_by(farmer_id=user.id).all()
        os_=db.query(models.Order).filter_by(farmer_id=user.id).all()
        return {"role":"farmer","total_products":len(ps),
            "available_quantity":round(sum(p.quantity for p in ps if p.status=="available"),2),
            "active_orders":sum(o.status in ("pending","accepted") for o in os_),
            "total_sales":round(sum(o.total_amount for o in os_ if o.status in ("accepted","completed")),2)}
    if user.role=="transporter":
        os_=db.query(models.Order).filter_by(transporter_id=user.id).all()
        return {"role":"transporter","assigned_deliveries":len(os_),
            "in_transit":sum(o.delivery_status=="in_transit" for o in os_),
            "delivered":sum(o.delivery_status=="delivered" for o in os_)}
    if user.role=="admin":
        os_=db.query(models.Order).all()
        return {"role":"admin","users_total":db.query(models.User).count(),
            "products":db.query(models.Product).count(),"orders":len(os_),
            "total_sales":round(sum(o.total_amount for o in os_ if o.status in ("accepted","completed")),2)}
    os_=db.query(models.Order).filter_by(buyer_id=user.id).all()
    ds=db.query(models.Demand).filter_by(buyer_id=user.id,status="open").all()
    return {"role":"buyer","total_orders":len(os_),"open_demands":len(ds),
            "total_spent":round(sum(o.total_amount for o in os_),2),"recent_orders":len(os_)}

# --- Router auto-discovery -------------------------------------------------
# Every module in app/routers with a `router` attribute is included, sorted
# by module name. Later phases add routers by dropping a module in the
# package — no edit to main.py is needed.
for _info in sorted(pkgutil.iter_modules(routers_pkg.__path__), key=lambda m: m.name):
    _mod = importlib.import_module(f"{routers_pkg.__name__}.{_info.name}")
    _router = getattr(_mod, "router", None)
    if _router is not None:
        app.include_router(_router)

# --- Uploaded listing images (served at /uploads/...) ----------------------
UPLOAD_ROOT = upload_dir()
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_ROOT)), name="uploads")

# --- React SPA --------------------------------------------------------------
# Serve frontend/dist when a production build exists; otherwise run API-only.
# The catch-all is registered AFTER all API routes, so /api/*, /docs,
# /openapi.json and /uploads always win. frontend-legacy/ is never served.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.is_dir() and (DIST / "index.html").exists():
    _assets = DIST / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith(("api/", "docs", "openapi.json", "uploads")) or full_path == "api":
            raise HTTPException(404, "Not found")
        # Serve real files from dist/ (manifest, sw.js, icons, favicon) so the
        # PWA works; anything else falls back to index.html for client routing.
        candidate = (DIST / full_path).resolve()
        try:
            candidate.relative_to(DIST.resolve())
        except ValueError:
            raise HTTPException(404, "Not found")
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(DIST / "index.html"))
else:
    logger.warning("frontend/dist not found; running in API-only mode (no SPA served)")
