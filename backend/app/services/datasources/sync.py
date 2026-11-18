"""External data-source registry + sync logic (Phase 3).

Shared by the admin endpoint (routers/data_sources.py) and the in-app
scheduler (services/scheduler.py) so both sync paths behave identically.

Only World Bank has an automatic sync (a real bounded API call). Every other
source honestly reports that it needs manual download — no endpoint is ever
invented for a source that has none.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from ... import models
from . import worldbank

ALL_MARKETS = ["BD", "KE", "NG", "GH", "TZ", "UG"]

SEED_SOURCES: list[dict] = [
    {"name": "FAOSTAT", "kind": "faostat",
     "endpoint": "https://www.fao.org/faostat/",
     "countries": ALL_MARKETS, "status": "manual",
     "notes": "Bulk CSV download; no live price API. National producer prices only."},
    {"name": "World Bank Open Data", "kind": "worldbank",
     "endpoint": "https://data.worldbank.org/",
     "countries": ALL_MARKETS, "status": "available",
     "notes": "API v2 indicator fetch implemented in services/datasources/worldbank.py."},
    {"name": "OpenWeatherMap", "kind": "openweather",
     "endpoint": "https://openweathermap.org/api",
     "countries": ALL_MARKETS, "status": "deprecated",
     "notes": ("Deprecated 2026-11-17: weather uses keyless Open-Meteo; "
               "OPENWEATHER_API_KEY is ignored.")},
    {"name": "CGIAR Big Data", "kind": "cgiar",
     "endpoint": "https://bigdata.cgiar.org/",
     "countries": ALL_MARKETS, "status": "manual",
     "notes": "No integrated API; datasets loadable via CSV."},
    {"name": "Bangladesh DAM", "kind": "dam",
     "endpoint": "",
     "countries": ["BD"], "status": "not_configured",
     "notes": ("No public API found/used. Do not invent an endpoint; official "
               "market-price publications must be ingested manually.")},
    {"name": "PlantVillage", "kind": "plantvillage",
     "endpoint": "",
     "countries": [], "status": "manual",
     "notes": "Dataset download for disease-model training; disease labels only, no ripeness labels."},
]

# One stable, always-published indicator used as a bounded connectivity probe.
WORLDBANK_PROBE_INDICATOR = "SP.POP.TOTL"  # Total population
WORLDBANK_PROBE_COUNTRY = "BGD"
# The World Bank API measured ~12s for this exact probe from this network
# (2026-11-17); a 10s timeout failed it spuriously. 30s matches the adapter.
SYNC_TIMEOUT_S = 30


def _sync_client() -> httpx.Client:
    """httpx client for the World Bank probe.

    httpx parses NO_PROXY from the environment and raises InvalidURL on
    bracketed IPv6 entries (e.g. "[::1]") present in some sandbox/proxy
    setups, failing before any request is made. Passing the egress proxy
    explicitly bypasses env-proxy parsing while still routing through the
    configured proxy. Without a proxy env var this is a plain client.
    """
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or None
    if proxy:
        return httpx.Client(timeout=SYNC_TIMEOUT_S, proxy=proxy)
    return httpx.Client(timeout=SYNC_TIMEOUT_S)


def _redact_proxy(text: str) -> str:
    """Strip any egress-proxy URL (which may carry credentials) from an
    error message before it is stored in notes or returned to the caller."""
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = os.getenv(var)
        if value and value in text:
            text = text.replace(value, "[proxy]")
    return text


def ensure_seeded(db: Session) -> None:
    """Insert the six known sources when the table is empty (idempotent)."""
    if db.query(models.ExternalDataSource).count() > 0:
        return
    for s in SEED_SOURCES:
        db.add(models.ExternalDataSource(
            name=s["name"], kind=s["kind"], endpoint=s["endpoint"],
            countries=json.dumps(s["countries"]), status=s["status"], notes=s["notes"]))
    db.commit()


def sync_source(db: Session, row: models.ExternalDataSource) -> dict:
    """Sync one source; returns the status dict the admin endpoint returns.

    Manual-only sources report "manual" and leave last_sync_at untouched.
    World Bank runs the bounded probe fetch and records ok/error on the row.
    Network/API failure is recorded, never raised.
    """
    if row.kind != "worldbank":
        # No automatic sync exists for this source; report that honestly and
        # leave last_sync_at untouched.
        return {"id": row.id, "name": row.name, "kind": row.kind, "status": "manual",
                "last_sync_at": row.last_sync_at,
                "message": "This source requires manual download; no automatic sync is implemented."}
    # World Bank: real bounded fetch of one indicator via the existing adapter.
    try:
        with _sync_client() as client:
            series = worldbank.fetch_indicator(
                WORLDBANK_PROBE_COUNTRY, WORLDBANK_PROBE_INDICATOR, 2020, 2024, client)
        if not series:
            raise RuntimeError("World Bank API returned no data for the probe indicator")
        row.status = "ok"
        row.last_sync_at = datetime.utcnow()
        row.notes = (f"API v2 indicator fetch implemented in services/datasources/worldbank.py. "
                     f"Last sync OK: fetched {WORLDBANK_PROBE_INDICATOR} for "
                     f"{WORLDBANK_PROBE_COUNTRY} ({len(series)} yearly values).")
        db.commit()
        return {"id": row.id, "name": row.name, "kind": row.kind, "status": "ok",
                "last_sync_at": row.last_sync_at,
                "message": f"Fetched {len(series)} yearly values of "
                           f"{WORLDBANK_PROBE_INDICATOR} for {WORLDBANK_PROBE_COUNTRY}."}
    except Exception as exc:  # network/API failure: record it, do not raise 500
        detail = _redact_proxy(str(exc))
        row.status = "error"
        row.notes = (f"API v2 indicator fetch implemented in services/datasources/worldbank.py. "
                     f"Last sync failed: {detail}")
        db.commit()
        return {"id": row.id, "name": row.name, "kind": row.kind, "status": "error",
                "last_sync_at": row.last_sync_at,
                "message": f"Sync failed: {detail}"}
