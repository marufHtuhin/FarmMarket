"""Simulated-sensor labelling: readings flagged is_simulated, counted in the
public cold-chain view, flagged in alerts, and logged as a ledger event."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app import models
from app.services import twin as T

T0 = datetime(2026, 11, 2, 12, 0)


def _setup(db):
    farmer = models.User(name="F", email="f@x.t", password_hash="x", role="farmer")
    db.add(farmer)
    db.commit()
    batch = T.create_batch(db, farmer.id, "tomato", "Gazipur", 500, datetime(2026, 11, 1, 6))
    dev = T.register_device(db, batch, "SIMULATED demo device")
    return SimpleNamespace(db=db, farmer=farmer, batch=batch, dev=dev)


def _push(s, i, temp, rh=90.0, simulated=False):
    ts = T0 + timedelta(minutes=30 * i)
    sig = T.sign_reading(s.dev["hmac_key"], s.dev["device_id"], T._iso(ts), temp, rh, "rh")
    return T.ingest_reading(s.db, s.dev["device_id"], ts, temp, rh, "rh", sig,
                            now=T0 + timedelta(hours=10), is_simulated=simulated)


def test_simulated_flag_stored_and_counted_in_public_view(db):
    s = _setup(db)
    _push(s, 0, 12, simulated=True)
    _push(s, 1, 13, simulated=True)
    _push(s, 2, 12, simulated=False)
    T.seal_readings(s.db, s.batch)
    rows = s.db.query(models.SensorReading).all()
    assert sum(r.is_simulated for r in rows) == 2
    view = T.public_view(s.db, s.batch)
    assert view["cold_chain"]["n_readings"] == 3
    assert view["cold_chain"]["simulated_readings"] == 2


def test_reading_endpoint_accepts_simulated_flag(client, db):
    s = _setup(db)
    ts = T0 + timedelta(minutes=30)
    sig = T.sign_reading(s.dev["hmac_key"], s.dev["device_id"], T._iso(ts), 12, 90, "rh")
    r = client.post("/api/v1/twin/readings", json={
        "device_id": s.dev["device_id"], "recorded_at": ts.isoformat(),
        "temperature_c": 12, "moisture_pct": 90, "moisture_kind": "rh",
        "signature": sig, "simulated": True})
    assert r.status_code == 200, r.text
    row = s.db.query(models.SensorReading).filter_by(id=r.json()["reading_id"]).one()
    assert row.is_simulated is True
    # Default is False when the flag is omitted.
    ts2 = T0 + timedelta(minutes=60)
    sig2 = T.sign_reading(s.dev["hmac_key"], s.dev["device_id"], T._iso(ts2), 12, 90, "rh")
    r2 = client.post("/api/v1/twin/readings", json={
        "device_id": s.dev["device_id"], "recorded_at": ts2.isoformat(),
        "temperature_c": 12, "moisture_pct": 90, "moisture_kind": "rh",
        "signature": sig2})
    assert r2.status_code == 200
    row2 = s.db.query(models.SensorReading).filter_by(id=r2.json()["reading_id"]).one()
    assert row2.is_simulated is False


def test_simulation_ledger_event_and_alert_flag(db):
    s = _setup(db)
    farmer = SimpleNamespace(id=s.farmer.id, role="farmer")
    blk = T.add_event(s.db, s.batch, farmer, "sensor_simulation",
                      {"n_readings": 1, "note": "SIMULATED"})
    assert blk.event_type == "sensor_simulation"
    view = T.public_view(s.db, s.batch)
    assert any(ev["event"] == "sensor_simulation" for ev in view["timeline"])
    # Out-of-range SIMULATED reading: the alert carries the flag.
    _push(s, 0, 45, simulated=True)
    out = T.alerts_for_readings("tomato", s.db.query(models.SensorReading).all())
    assert len(out["alerts"]) == 1
    assert out["alerts"][0]["simulated"] is True
