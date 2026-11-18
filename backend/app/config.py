"""Central configuration: trading hubs, crops and environment-driven settings.

Hub coordinates are city-level (not specific market stalls). Crop/temperature
ranges used elsewhere are *illustrative defaults* - tune them per variety.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def utcnow() -> datetime:
    """Naive UTC now — replacement for deprecated ``datetime.utcnow``.

    All timestamp columns in this app are naive ``DateTime`` (UTC, no
    tzinfo); this preserves the exact stored values while silencing the
    Python 3.12 deprecation of ``datetime.utcnow``. Never mix its result
    with timezone-aware datetimes (JWT expiry uses aware UTC separately
    and is never compared against DB timestamps).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class Hub:
    id: str
    name: str
    country: str
    iso3: str
    lat: float
    lon: float
    currency: str
    faostat_area: str  # FAOSTAT "Area" name used to match national producer prices


@dataclass(frozen=True)
class Crop:
    id: str
    name: str
    faostat_keywords: tuple[str, ...]  # matched case-insensitively against FAOSTAT "Item"


HUB_PROFILES: dict[str, list[Hub]] = {
    # The five sub-Saharan hubs named in the project brief.
    "sub_saharan": [
        Hub("nairobi", "Nairobi", "Kenya", "KEN", -1.2921, 36.8219, "KES", "Kenya"),
        Hub("kampala", "Kampala", "Uganda", "UGA", 0.3476, 32.5825, "UGX", "Uganda"),
        Hub("dar_es_salaam", "Dar es Salaam", "Tanzania", "TZA", -6.7924, 39.2083, "TZS",
            "United Republic of Tanzania"),
        Hub("lagos", "Lagos", "Nigeria", "NGA", 6.5244, 3.3792, "NGN", "Nigeria"),
        Hub("accra", "Accra", "Ghana", "GHA", 5.6037, -0.1870, "GHS", "Ghana"),
    ],
    # Optional profile matching the original Bangladesh MVP.
    "bangladesh": [
        Hub("dhaka", "Dhaka", "Bangladesh", "BGD", 23.8103, 90.4125, "BDT", "Bangladesh"),
        Hub("chattogram", "Chattogram", "Bangladesh", "BGD", 22.3569, 91.7832, "BDT", "Bangladesh"),
        Hub("rajshahi", "Rajshahi", "Bangladesh", "BGD", 24.3745, 88.6042, "BDT", "Bangladesh"),
        Hub("khulna", "Khulna", "Bangladesh", "BGD", 22.8456, 89.5403, "BDT", "Bangladesh"),
        Hub("sylhet", "Sylhet", "Bangladesh", "BGD", 24.8949, 91.8687, "BDT", "Bangladesh"),
    ],
}

CROPS: dict[str, Crop] = {
    c.id: c for c in [
        Crop("maize", "Maize", ("maize",)),
        Crop("tomato", "Tomato", ("tomato",)),
        Crop("onion", "Onion", ("onion",)),
        Crop("potato", "Potato", ("potato",)),
        Crop("banana", "Banana", ("banana",)),
    ]
}

# Full public crop catalog (11 crops) with Bangla local names. Seeded into
# the crops / crop_local_names tables by seed_demo.py; also the fallback for
# GET /api/v1/crops when the tables are empty (e.g. an unseeded dev DB).
# Order is the display order used by the catalog endpoint.
CROP_CATALOG: list[dict[str, str]] = [
    {"id": "tomato", "name": "Tomato", "bn": "টমেটো", "unit": "kg"},
    {"id": "potato", "name": "Potato", "bn": "আলু", "unit": "kg"},
    {"id": "onion", "name": "Onion", "bn": "পেঁয়াজ", "unit": "kg"},
    {"id": "rice", "name": "Rice", "bn": "ধান", "unit": "kg"},
    {"id": "banana", "name": "Banana", "bn": "কলা", "unit": "kg"},
    {"id": "mango", "name": "Mango", "bn": "আম", "unit": "kg"},
    {"id": "brinjal", "name": "Brinjal", "bn": "বেগুন", "unit": "kg"},
    {"id": "chili", "name": "Chili", "bn": "মরিচ", "unit": "kg"},
    {"id": "cauliflower", "name": "Cauliflower", "bn": "ফুলকপি", "unit": "kg"},
    {"id": "jute", "name": "Jute", "bn": "পাট", "unit": "kg"},
    {"id": "maize", "name": "Maize", "bn": "ভুট্টা", "unit": "kg"},
]

# Two-letter country codes for the six markets, keyed by the ISO-3 code used
# on Hub. Country names/currencies/hub coordinates come from HUB_PROFILES.
COUNTRY_ORDER: list[tuple[str, str]] = [
    ("BGD", "BD"),
    ("KEN", "KE"),
    ("NGA", "NG"),
    ("GHA", "GH"),
    ("TZA", "TZ"),
    ("UGA", "UG"),
]


def hub_profile() -> str:
    p = os.getenv("HUB_PROFILE", "bangladesh").strip().lower()
    return p if p in HUB_PROFILES else "bangladesh"


def active_hubs() -> list[Hub]:
    return HUB_PROFILES[hub_profile()]


def get_hub(hub_id: str) -> Hub | None:
    for profile in HUB_PROFILES.values():
        for h in profile:
            if h.id == hub_id:
                return h
    return None


def get_crop(crop_id: str) -> Crop | None:
    return CROPS.get(crop_id.strip().lower())


def model_dir() -> Path:
    default = Path(__file__).resolve().parents[1] / "models"
    return Path(os.getenv("MODEL_DIR", str(default)))


def upload_dir() -> Path:
    """Root for user-uploaded listing images (served at /uploads).

    UPLOAD_DIR may be absolute or relative to backend/.
    """
    raw = os.getenv("UPLOAD_DIR", "uploads")
    p = Path(raw)
    return p if p.is_absolute() else Path(__file__).resolve().parents[1] / raw


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def normalize_database_url(url: str) -> str:
    """Normalize a DATABASE_URL for SQLAlchemy + PyMySQL.

    PaaS MySQL addons (e.g. Railway) hand out bare ``mysql://`` URLs, but
    SQLAlchemy's default MySQL driver is MySQLdb, which is not installed —
    this app uses PyMySQL. Rewrite the scheme to ``mysql+pymysql://`` and
    ensure ``charset=utf8mb4`` so Bangla text stores correctly. SQLite
    and already-qualified URLs pass through unchanged (apart from the
    charset default). Used by both app/database.py and alembic/env.py so
    the app and migrations always agree on the URL.
    """
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

    url = (url or "").strip()
    if not url or url.startswith("sqlite"):
        return url
    parsed = urlparse(url)
    scheme = parsed.scheme
    if scheme == "mysql":
        scheme = "mysql+pymysql"
    if not scheme.startswith("mysql"):
        return url
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("charset", "utf8mb4")
    return urlunparse(parsed._replace(scheme=scheme, query=urlencode(query)))


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def database_ssl_args(url: str = "") -> dict:
    """TLS connect args for MySQL, e.g. TiDB Cloud Starter.

    TiDB Cloud Starter refuses non-TLS connections on its public endpoint
    (docs.pingcap.com/tidbcloud/dev-guide-sample-application-python-sqlalchemy).
    PyMySQL, via SQLAlchemy's ``mysql+pymysql`` dialect, takes
    ``ssl_verify_cert`` / ``ssl_verify_identity`` / ``ssl_ca`` as connect
    args — the same keys TiDB's own sample passes.

    Opt-in only: returns ``{}`` unless ``DB_SSL_CA`` (a CA-bundle path) is
    set, or the URL itself carries ``ssl_verify_cert=true``. ``DB_SSL_CA``
    on Render (Debian) is ``/etc/ssl/certs/ca-certificates.crt``; TiDB's
    connection dialog shows the per-OS path. Railway MySQL needs none of
    this and keeps the empty default.

    Kept as the explicit-CA fallback inside :func:`db_connect_args` —
    callers should use ``db_connect_args`` (it also auto-detects TiDB
    hosts and honours ``DB_SSL``).
    """
    from urllib.parse import parse_qsl, urlparse

    parsed = urlparse(url or "")
    if not parsed.scheme.startswith("mysql"):
        return {}
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    ca = env("DB_SSL_CA")
    if ca:
        return {"ssl_verify_cert": True, "ssl_verify_identity": True,
                "ssl_ca": ca}
    if _truthy(query.get("ssl_verify_cert", "")):
        args: dict = {"ssl_verify_cert": True,
                      "ssl_verify_identity": _truthy(
                          query.get("ssl_verify_identity", "true"))}
        if query.get("ssl_ca"):
            args["ssl_ca"] = query["ssl_ca"]
        return args
    return {}


def _falsy(value: str) -> bool:
    return value.strip().lower() in ("0", "false", "no", "off")


def db_connect_args(database_url: str | None = None) -> dict:
    """Connect args for ``create_engine`` / Alembic, with TiDB TLS.

    The single entry point for DB connect args — used by app/database.py
    and alembic/env.py so the app and migrations always connect the same
    way. Rules:

    * SQLite → ``{"check_same_thread": False}`` (unchanged behaviour).
    * MySQL on a ``*.tidbcloud.com`` host → verified TLS automatically:
      ``{"ssl": {"ca": certifi.where()}}``. TiDB Cloud Starter/Essential
      refuses non-TLS connections, and its certificates come from Let's
      Encrypt (publicly trusted), so the certifi CA bundle verifies them
      with no extra config — the user just pastes the TiDB URL.
      PyMySQL builds the SSL context with ``CERT_REQUIRED`` + hostname
      check when ``"ca"`` is set (``_create_ssl_ctx``).
    * ``DB_SSL`` truthy (``1``/``true``/``yes``/``on``) → verified TLS
      for any MySQL host. ``DB_SSL`` falsy (``0``/``false``/``no``/``off``)
      forces TLS OFF, even for a TiDB host.
    * An explicit ``DB_SSL_CA`` path (or ``ssl_verify_cert`` in the URL)
      still wins via :func:`database_ssl_args` — the older opt-in path.
    * Anything else → ``{}`` (e.g. Railway MySQL needs no TLS).

    ``database_url=None`` reads ``DATABASE_URL`` from the environment.
    """
    from urllib.parse import urlparse

    url = (database_url if database_url is not None
           else os.getenv("DATABASE_URL", ""))
    url = (url or "").strip()
    if not url or url.startswith("sqlite"):
        return {"check_same_thread": False}
    parsed = urlparse(url)
    if not parsed.scheme.startswith("mysql"):
        return {}
    # An explicit DB_SSL=false disables TLS entirely, even for TiDB.
    if _falsy(env("DB_SSL")):
        return {}
    # Explicit CA path (or ssl_* URL params) still takes precedence.
    explicit = database_ssl_args(url)
    if explicit:
        return explicit
    host = (parsed.hostname or "").lower()
    if host.endswith(".tidbcloud.com") or _truthy(env("DB_SSL")):
        import certifi

        return {"ssl": {"ca": certifi.where()}}
    return {}


def database_pool_recycle(url: str = "") -> int | None:
    """Pool recycle seconds, or ``None`` to keep SQLAlchemy's default.

    TiDB Cloud Starter closes idle connections after 5 minutes, so pooled
    connections go stale; TiDB's docs recommend ``pool_recycle=300``.
    Only set when TLS is on (the TiDB path); Railway MySQL is unaffected.
    """
    args = db_connect_args(url)
    if "ssl" in args or "ssl_verify_cert" in args:
        return 300
    return None
