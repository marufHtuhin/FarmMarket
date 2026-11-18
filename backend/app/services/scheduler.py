"""In-app scheduler (APScheduler): daily price-freshness check, run inside
the API process.

Enabled ONLY when SCHEDULER_ENABLED=true (default false). It NEVER runs under
pytest (PYTEST_CURRENT_TEST is set) or when ENVIRONMENT=test — the lifespan
handler in main.py calls start_scheduler() unconditionally and the gate lives
here, so tests constructing the app can never spawn background jobs.

FAOSTAT is deliberately NOT scheduled. FAO's Producer Prices domain is
annual-only (latest release 23 Jan 2025 covers 2020-2024) and its prices
are national figures, not daily market prices — see
docs/knowledge/faostat-notes.md ("FAOSTAT prices are not daily market
prices for a local bazaar"). FAOSTAT stays a clearly-labelled annual
national reference behind the existing manual sync endpoint; nothing here
syncs it, and nothing here presents it as a realtime/auto-updated price
source. The only scheduled job is the read-only price-freshness check.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func

from .. import models
from ..database import SessionLocal

logger = logging.getLogger(__name__)

JOB_FRESHNESS_ID = "price_freshness"
DEFAULT_FRESHNESS_HOUR = 4
DEFAULT_FRESHNESS_DAYS = 60
MAX_STALE_LISTED = 20

_scheduler: BackgroundScheduler | None = None


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _hour_env(name: str, default: int) -> int:
    """Hour-of-day env var (0-23, UTC); invalid values fall back to default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        hour = int(raw.strip())
    except ValueError:
        logger.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default
    if not 0 <= hour <= 23:
        logger.warning("Invalid %s=%r (must be 0-23); using default %d",
                       name, raw, default)
        return default
    return hour


def _days_env(name: str, default: int) -> int:
    """Positive-day-count env var; invalid values fall back to default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        days = int(raw.strip())
    except ValueError:
        logger.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default
    if days < 1:
        logger.warning("Invalid %s=%r (must be >= 1); using default %d",
                       name, raw, default)
        return default
    return days


def is_scheduler_enabled() -> bool:
    """True only when explicitly enabled AND not running under pytest."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if os.getenv("ENVIRONMENT", "").strip().lower() == "test":
        return False
    return _truthy(os.getenv("SCHEDULER_ENABLED"))


def run_price_freshness_check() -> dict:
    """Scheduled job (read-only): for each hub/crop series, compare the
    latest observation date with today and log an info summary plus a
    warning listing stale series (older than SCHEDULER_FRESHNESS_DAYS,
    default 60). Never mutates data.

    Note: annual reference series (FAOSTAT) will naturally read stale
    against a 60-day threshold — that is expected for an annual source,
    not an error. The warning is informational.
    """
    stale_after_days = _days_env("SCHEDULER_FRESHNESS_DAYS", DEFAULT_FRESHNESS_DAYS)
    cutoff = date.today() - timedelta(days=stale_after_days)
    db = SessionLocal()
    try:
        latest = (db.query(models.PriceObservation.hub_id,
                           models.PriceObservation.crop,
                           func.max(models.PriceObservation.observed_on))
                  .group_by(models.PriceObservation.hub_id,
                            models.PriceObservation.crop).all())
        stale = [(hub, crop, latest_on) for hub, crop, latest_on in latest
                 if latest_on is None or latest_on < cutoff]
        fresh = len(latest) - len(stale)
        logger.info("Scheduler: price-freshness check: %d series, %d fresh, "
                    "%d stale (older than %d days)",
                    len(latest), fresh, len(stale), stale_after_days)
        if stale:
            listed = ", ".join(f"{hub}/{crop} (latest {d})"
                               for hub, crop, d in stale[:MAX_STALE_LISTED])
            suffix = (f" and {len(stale) - MAX_STALE_LISTED} more"
                      if len(stale) > MAX_STALE_LISTED else "")
            logger.warning("Scheduler: stale price series: %s%s", listed, suffix)
        return {"series": len(latest), "fresh": fresh, "stale": len(stale),
                "stale_after_days": stale_after_days}
    except Exception:
        logger.exception("Scheduler: price-freshness check failed")
        return {}
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    """Build (but do not start) the scheduler with its one daily job: the
    price-freshness check. Hours are UTC. The job never overlaps
    (max_instances=1) and a missed run is picked up within an hour
    (misfire_grace_time). No data-source sync job exists here by design —
    see the module docstring (FAOSTAT is annual-only)."""
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(run_price_freshness_check,
                  CronTrigger(hour=_hour_env("SCHEDULER_FRESHNESS_HOUR", DEFAULT_FRESHNESS_HOUR),
                              minute=0, timezone="UTC"),
                  id=JOB_FRESHNESS_ID, name="Daily price-freshness check",
                  max_instances=1, misfire_grace_time=3600, replace_existing=True)
    return sched


def start_scheduler() -> BackgroundScheduler | None:
    """Start the background scheduler when enabled; otherwise log and return
    None. Idempotent: a second call returns the running scheduler."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    if not is_scheduler_enabled():
        logger.info("Scheduler disabled (SCHEDULER_ENABLED is not 'true'); "
                    "no jobs scheduled")
        return None
    _scheduler = create_scheduler()
    _scheduler.start()
    logger.info("Scheduler started: daily price-freshness check at %02d:00 UTC",
                _hour_env("SCHEDULER_FRESHNESS_HOUR", DEFAULT_FRESHNESS_HOUR))
    return _scheduler


def stop_scheduler() -> None:
    """Shut the scheduler down (no-op when not running). Idempotent."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")


def get_scheduler() -> BackgroundScheduler | None:
    """The running scheduler, or None (mainly for tests)."""
    return _scheduler
