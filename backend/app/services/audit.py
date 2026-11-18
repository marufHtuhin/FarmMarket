"""Best-effort audit logging.

log_audit() never raises: if the audit write fails it rolls back and the
request continues. Call it AFTER the request's own commit so a failed audit
write cannot roll back the request's changes.
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger(__name__)


def log_audit(db: Session, user_id: int | None, action: str, details: str = "") -> None:
    try:
        db.add(models.AuditLog(user_id=user_id, action=action, details=details))
        db.commit()
    except Exception:
        logger.exception("audit log write failed (action=%s)", action)
        try:
            db.rollback()
        except Exception:
            pass
