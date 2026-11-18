"""In-app scheduler gating + jobs (Workstream F).

The scheduler must NEVER start under pytest: PYTEST_CURRENT_TEST is set for
every test in this file, so is_scheduler_enabled() is False unless the test
explicitly removes that variable (simulating a real server process). No test
here starts a scheduler with live jobs except the lifecycle test, whose job
is a daily cron trigger that cannot fire during the test.

FAOSTAT correction: FAOSTAT is annual-only (see docs/knowledge/
faostat-notes.md) and is deliberately NOT scheduled — the scheduler runs
only the price-freshness job. The tests below assert that: exactly one
job, and no data-source sync job exists.
"""
import os
from datetime import date, timedelta

import pytest
from apscheduler.triggers.cron import CronTrigger

from app import models
from app.services import scheduler


@pytest.fixture(autouse=True)
def _clean_scheduler():
    scheduler.stop_scheduler()
    yield
    scheduler.stop_scheduler()


def _outside_pytest(monkeypatch):
    """Simulate a real server process: no pytest marker, non-test env."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")


def test_disabled_by_default(monkeypatch):
    _outside_pytest(monkeypatch)
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
    assert scheduler.is_scheduler_enabled() is False


def test_enabled_when_flag_true_outside_pytest(monkeypatch):
    _outside_pytest(monkeypatch)
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    assert scheduler.is_scheduler_enabled() is True


@pytest.mark.parametrize("value", ["1", "yes", "on", "TRUE", " True "])
def test_flag_values_enable(monkeypatch, value):
    _outside_pytest(monkeypatch)
    monkeypatch.setenv("SCHEDULER_ENABLED", value)
    assert scheduler.is_scheduler_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", ""])
def test_flag_values_disable(monkeypatch, value):
    _outside_pytest(monkeypatch)
    monkeypatch.setenv("SCHEDULER_ENABLED", value)
    assert scheduler.is_scheduler_enabled() is False


def test_never_enabled_under_pytest(monkeypatch):
    # PYTEST_CURRENT_TEST is set by pytest for every test; even with the flag
    # on, the gate stays closed.
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert os.getenv("PYTEST_CURRENT_TEST")
    assert scheduler.is_scheduler_enabled() is False


def test_never_enabled_when_environment_test(monkeypatch):
    _outside_pytest(monkeypatch)
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "test")
    assert scheduler.is_scheduler_enabled() is False


def test_start_does_nothing_when_disabled(monkeypatch):
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")  # still gated: under pytest
    assert scheduler.start_scheduler() is None
    assert scheduler.get_scheduler() is None


def test_create_scheduler_has_only_the_freshness_job(monkeypatch):
    # FAOSTAT correction: no data-source sync job exists — the scheduler
    # runs only the price-freshness check (FAOSTAT is annual-only).
    monkeypatch.setenv("SCHEDULER_FRESHNESS_HOUR", "6")
    sched = scheduler.create_scheduler()
    try:
        assert sched.running is False  # built, not started
        jobs = {job.id: job for job in sched.get_jobs()}
        assert set(jobs) == {"price_freshness"}
        job = jobs["price_freshness"]
        assert isinstance(job.trigger, CronTrigger)
        assert job.max_instances == 1
        assert "hour='6'" in str(job.trigger)
        assert not hasattr(scheduler, "run_data_source_sync")
    finally:
        if sched.running:
            sched.shutdown(wait=False)


def test_create_scheduler_defaults_to_4_utc(monkeypatch):
    monkeypatch.delenv("SCHEDULER_FRESHNESS_HOUR", raising=False)
    sched = scheduler.create_scheduler()
    try:
        jobs = {job.id: job for job in sched.get_jobs()}
        assert set(jobs) == {"price_freshness"}
        assert "hour='4'" in str(jobs["price_freshness"].trigger)
    finally:
        if sched.running:
            sched.shutdown(wait=False)


def test_start_stop_lifecycle(monkeypatch):
    # Force the gate open to exercise start/stop mechanics; the job is a
    # daily cron trigger, so nothing fires during this test.
    monkeypatch.setattr(scheduler, "is_scheduler_enabled", lambda: True)
    started = scheduler.start_scheduler()
    assert started is not None and started.running
    assert scheduler.get_scheduler() is started
    assert scheduler.start_scheduler() is started  # idempotent
    scheduler.stop_scheduler()
    assert scheduler.get_scheduler() is None
    scheduler.stop_scheduler()  # idempotent


def test_freshness_job_empty_db(db, caplog):
    with caplog.at_level("INFO", logger="app.services.scheduler"):
        result = scheduler.run_price_freshness_check()
    assert result == {"series": 0, "fresh": 0, "stale": 0, "stale_after_days": 60}
    assert "0 series" in caplog.text


def test_freshness_job_flags_stale_series(db, caplog):
    today = date.today()
    db.add(models.PriceObservation(hub_id="dhaka", crop="rice", observed_on=today,
                                   price=50.0, currency="BDT", source="test"))
    db.add(models.PriceObservation(hub_id="dhaka", crop="potato",
                                   observed_on=today - timedelta(days=100),
                                   price=30.0, currency="BDT", source="test"))
    db.commit()
    with caplog.at_level("INFO", logger="app.services.scheduler"):
        result = scheduler.run_price_freshness_check()
    assert result["series"] == 2 and result["fresh"] == 1 and result["stale"] == 1
    assert "dhaka/potato" in caplog.text
    assert "stale price series" in caplog.text


def test_freshness_threshold_env(monkeypatch, db):
    monkeypatch.setenv("SCHEDULER_FRESHNESS_DAYS", "10")
    db.add(models.PriceObservation(hub_id="dhaka", crop="rice",
                                   observed_on=date.today() - timedelta(days=20),
                                   price=50.0, currency="BDT", source="test"))
    db.commit()
    result = scheduler.run_price_freshness_check()
    assert result["stale"] == 1 and result["stale_after_days"] == 10


def test_lifespan_never_starts_scheduler_under_pytest(app_module, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    with TestClient(app_module):
        assert scheduler.get_scheduler() is None
    assert scheduler.get_scheduler() is None
