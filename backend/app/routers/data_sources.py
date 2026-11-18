"""Admin registry of external data sources (Phase 3).

The table self-seeds on first read with the six known sources. Endpoints are
never invented: a source with no public API gets an empty endpoint and a
status that says so. Sync is only automatic for World Bank (a real bounded
API call); every other source honestly reports that it needs manual download.

The registry and sync logic live in services/datasources/sync.py, shared
with the in-app scheduler; this module is only the HTTP surface.
SEED_SOURCES and ensure_seeded are re-exported here so
scripts/seed_data_sources.py keeps importing them from this module.
"""
from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..security import require_role
from ..services.datasources.sync import (SEED_SOURCES, ensure_seeded,
                                        sync_source)

__all__ = ["router", "SEED_SOURCES", "ensure_seeded"]

router = APIRouter(prefix="/api/v1/admin/data-sources", tags=["data-sources"])
admin = require_role("admin")


def _serialize(row: models.ExternalDataSource) -> dict:
    try:
        countries = json.loads(row.countries or "[]")
    except (ValueError, TypeError):
        countries = []
    return {"id": row.id, "name": row.name, "kind": row.kind,
            "endpoint": row.endpoint, "countries": countries,
            "last_sync_at": row.last_sync_at, "status": row.status,
            "notes": row.notes}


@router.get("")
def list_data_sources(db: Session = Depends(get_db), user=Depends(admin)):
    ensure_seeded(db)
    rows = db.query(models.ExternalDataSource).order_by(models.ExternalDataSource.id).all()
    return [_serialize(r) for r in rows]


@router.post("/{source_id}/sync")
def sync_data_source(source_id: int, db: Session = Depends(get_db), user=Depends(admin)):
    ensure_seeded(db)
    row = db.query(models.ExternalDataSource).filter_by(id=source_id).first()
    if not row:
        raise HTTPException(404, "Data source not found")
    return sync_source(db, row)
