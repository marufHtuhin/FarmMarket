import json
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app import models
from app.services import twin as T

T0 = datetime(2026, 11, 2, 12, 0)


@pytest.fixture()
def setup(db):
    farmer = models.User(name="F", email="f@x.t", password_hash="x", role="farmer")
    buyer = models.User(name="B", email="b@x.t", password_hash="x", role="buyer")
    db.add_all([farmer, buyer]); db.commit()
    batch = T.create_batch(db, farmer.id, "tomato", "Gazipur", 500, datetime(2026, 11, 1, 6))
    dev = T.register_device(db, batch, "truck")
    return SimpleNamespace(db=db, farmer=farmer, buyer=buyer, batch=batch, dev=dev)


def push(s, i, temp, rh=90.0, kind="rh"):
    ts = T0 + timedelta(minutes=30 * i)
    sig = T.sign_reading(s.dev["hmac_key"], s.dev["device_id"], T._iso(ts), temp, rh, kind)
    return T.ingest_reading(s.db, s.dev["device_id"], ts, temp, rh, kind, sig, now=T0 + timedelta(hours=10))


def test_fresh_chain_verifies(setup):
    v = T.verify_chain(setup.db, setup.batch)
    assert v["valid"] and v["blocks"] == 1 and v["head_hash"]


def test_altering_a_block_is_detected(setup):
    T.add_event(setup.db, setup.batch, SimpleNamespace(id=setup.farmer.id, role="farmer"), "packed", {"crates": 10})
    blk = setup.db.query(models.LedgerBlock).filter_by(event_type="packed").one()
    blk.payload = json.dumps({"crates": 1}); setup.db.commit()
    probs = T.verify_chain(setup.db, setup.batch)["problems"]
    assert probs and probs[0]["block"] == 1


def test_rehashing_one_block_still_breaks_the_next_link(setup):
    farmer = SimpleNamespace(id=setup.farmer.id, role="farmer")
    T.add_event(setup.db, setup.batch, farmer, "packed", {"n": 1})
    T.add_event(setup.db, setup.batch, farmer, "dispatched", {"n": 2})
    b1 = setup.db.query(models.LedgerBlock).filter_by(event_type="packed").one()
    b1.payload = json.dumps({"n": 99, "actor_role": "farmer"})
    b1.block_hash = T.block_hash(b1.idx, b1.timestamp, b1.event_type, b1.actor_user_id, b1.payload, b1.prev_hash)
    setup.db.commit()
    assert any("prev_hash" in p["problem"] for p in T.verify_chain(setup.db, setup.batch)["problems"])


def test_sensor_tampering_detected_after_seal(setup):
    for i, t in enumerate([12, 13, 14]):
        push(setup, i, t)
    assert T.seal_readings(setup.db, setup.batch) is not None
    assert T.verify_chain(setup.db, setup.batch)["valid"]
    r = setup.db.query(models.SensorReading).first(); r.temperature_c = 5.0; setup.db.commit()
    assert any("sensor" in p["problem"] for p in T.verify_chain(setup.db, setup.batch)["problems"])


def test_deleting_a_sealed_reading_detected(setup):
    for i in range(3):
        push(setup, i, 12)
    T.seal_readings(setup.db, setup.batch)
    setup.db.delete(setup.db.query(models.SensorReading).first()); setup.db.commit()
    assert not T.verify_chain(setup.db, setup.batch)["valid"]


def test_bad_signature_unknown_device_replay_and_future_rejected(setup):
    d = setup.dev["device_id"]
    with pytest.raises(PermissionError):
        T.ingest_reading(setup.db, d, T0, 12, 90, "rh", "0" * 64, now=T0)
    with pytest.raises(PermissionError):
        T.ingest_reading(setup.db, "DEV-NOPE", T0, 12, 90, "rh", "x", now=T0)
    push(setup, 0, 12)
    with pytest.raises(T.TwinError):
        push(setup, 0, 12)                                   # exact replay
    ts = T0 + timedelta(days=2)
    sig = T.sign_reading(setup.dev["hmac_key"], d, T._iso(ts), 12, 90, "rh")
    with pytest.raises(T.TwinError):
        T.ingest_reading(setup.db, d, ts, 12, 90, "rh", sig, now=T0)
    # a signature for different values must not validate
    sig2 = T.sign_reading(setup.dev["hmac_key"], d, T._iso(T0 + timedelta(hours=1)), 12, 90, "rh")
    with pytest.raises(PermissionError):
        T.ingest_reading(setup.db, d, T0 + timedelta(hours=1), 3, 90, "rh", sig2, now=T0 + timedelta(hours=2))


def test_cold_chain_excursion_analysis(setup):
    for i, t in enumerate([12, 13, 19, 19, 14]):            # tomato range 8-15 C
        push(setup, i, t)
    out = T.analyse_readings("tomato", setup.db.query(models.SensorReading).all())
    assert out["status"] == "excursion" and out["temp_excursions"] == 2 and out["minutes_out_of_temp_range"] == 60.0


def test_maize_product_moisture_limit(setup):
    push(setup, 0, 20, 16.0, "product")
    out = T.analyse_readings("maize", setup.db.query(models.SensorReading).all())
    assert out["product_moisture_exceeded"] and out["status"] == "excursion"


def test_role_rules(setup):
    outsider = SimpleNamespace(id=999, role="farmer")
    with pytest.raises(PermissionError):
        T.add_event(setup.db, setup.batch, outsider, "packed", {})
    with pytest.raises(PermissionError):                      # buyer with no linked order
        T.add_event(setup.db, setup.batch, SimpleNamespace(id=setup.buyer.id, role="buyer"), "received", {})
    with pytest.raises(T.TwinError):
        T.add_event(setup.db, setup.batch, SimpleNamespace(id=setup.farmer.id, role="farmer"), "sensor_seal", {})


def test_public_view_has_no_personal_data_and_says_not_anchored(setup):
    push(setup, 0, 12); T.seal_readings(setup.db, setup.batch)
    pv = T.public_view(setup.db, setup.batch)
    blob = json.dumps(pv, default=str)
    assert "f@x.t" not in blob
    # Check for coordinate *keys*, not the raw substring "lat": the legitimate
    # key "simulated_readings" contains "lat" as a substring.
    assert '"lat":' not in blob and '"lon":' not in blob and "latitude" not in blob
    assert '"actor"' not in blob
    assert pv["integrity"]["chain_valid"] and pv["integrity"]["externally_anchored"] is False
    assert "Not yet anchored" in pv["integrity"]["note"]


def test_local_anchor_is_reported_as_not_external(setup):
    a = T.anchor_head(setup.db, setup.batch)
    assert a["external"] is False and a["provider"] == "local-unanchored"


def test_merkle_root_changes_with_any_leaf():
    base = T.merkle_root(["a", "b", "c"])
    assert base != T.merkle_root(["a", "b", "d"]) and base != T.merkle_root(["a", "b"])
