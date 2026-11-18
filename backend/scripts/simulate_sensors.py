"""Simulated IoT sensor device for Digital Twin demo batches.

Posts SIMULATED temperature/humidity readings to a batch through the real
device API (HMAC-signed, exactly like real firmware). Every reading is stored
with is_simulated=True and labelled SIMULATED in the UI and API responses.

NEVER present these readings as real measurements. They exist only so a
hackathon demo can show cold-chain charts, threshold alerts and sealing
without physical sensors.

Usage (server running, e.g. after `python seed_demo.py`):
    python scripts/simulate_sensors.py --create-batch --crop tomato
    python scripts/simulate_sensors.py --batch-code FM-XXXX --count 12 --seal

Login defaults to the demo farmer (farmer@farmmarket.demo / Demo123!).
"""
import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.services.twin import COLD_CHAIN_RULES, _iso, sign_reading

BASE = "http://127.0.0.1:8000"


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default=BASE)
    ap.add_argument("--email", default="farmer@farmmarket.demo")
    ap.add_argument("--password", default="Demo123!")
    ap.add_argument("--batch-code", default="")
    ap.add_argument("--create-batch", action="store_true",
                    help="Create a new batch first (needs --crop)")
    ap.add_argument("--crop", default="tomato")
    ap.add_argument("--district", default="Gazipur")
    ap.add_argument("--quantity-kg", type=float, default=500)
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--interval-min", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--seal", action="store_true",
                    help="Seal the readings into the ledger afterwards")
    args = ap.parse_args()

    rules = COLD_CHAIN_RULES.get(args.crop)
    tlo, thi = rules["temp_c"] if rules else (4.0, 15.0)
    rlo, rhi = rules["rh_pct"] if rules else (85.0, 95.0)

    with httpx.Client(base_url=args.base_url, timeout=30) as c:
        r = c.post("/api/v1/auth/login", json={"email": args.email, "password": args.password})
        if r.status_code != 200:
            fail(f"login failed ({r.status_code}): {r.text[:200]}")
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        if args.create_batch:
            r = c.post("/api/v1/twin/batches", headers=h, json={
                "crop": args.crop, "origin_district": args.district,
                "quantity_kg": args.quantity_kg})
            if r.status_code != 200:
                fail(f"batch creation failed ({r.status_code}): {r.text[:200]}")
            code = r.json()["batch_code"]
            print(f"Created batch {code}")
        else:
            code = args.batch_code
            if not code:
                fail("pass --batch-code or --create-batch")
        r = c.get(f"/api/v1/twin/public/{code}")
        if r.status_code != 200:
            fail(f"batch {code} not found ({r.status_code})")

        r = c.post(f"/api/v1/twin/batches/{code}/devices", headers=h,
                   params={"label": "SIMULATED demo device"})
        if r.status_code != 200:
            fail(f"device registration failed ({r.status_code}): {r.text[:200]}")
        dev = r.json()
        device_id, key = dev["device_id"], dev["hmac_key"]
        print(f"Registered SIMULATED device {device_id}")

        rng = random.Random(args.seed)
        temp = (tlo + thi) / 2
        rh = (rlo + rhi) / 2
        end = datetime.utcnow().replace(microsecond=0)
        start = end - timedelta(minutes=args.interval_min * (args.count - 1))
        accepted = 0
        for i in range(args.count):
            ts = start + timedelta(minutes=args.interval_min * i)
            temp = min(max(temp + rng.uniform(-0.8, 0.8), tlo - 2), thi + 2)
            rh = min(max(rh + rng.uniform(-1.5, 1.5), rlo - 3), rhi + 3)
            temp, rh = round(temp, 2), round(rh, 2)
            sig = sign_reading(key, device_id, _iso(ts), temp, rh, "rh")
            r = c.post("/api/v1/twin/readings", json={
                "device_id": device_id, "recorded_at": ts.isoformat(),
                "temperature_c": temp, "moisture_pct": rh, "moisture_kind": "rh",
                "signature": sig, "simulated": True})
            if r.status_code != 200:
                fail(f"reading {i} rejected ({r.status_code}): {r.text[:200]}")
            accepted += 1
        print(f"Posted {accepted} SIMULATED readings "
              f"({start:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M} UTC)")

        r = c.post(f"/api/v1/twin/batches/{code}/events", headers=h, json={
            "event_type": "sensor_simulation",
            "data": {"n_readings": accepted, "device_id": device_id,
                     "note": "SIMULATED readings from scripts/simulate_sensors.py — not real measurements."}})
        if r.status_code != 200:
            print(f"WARNING: could not record the simulation event ({r.status_code})")
        else:
            print("Recorded a sensor_simulation ledger event.")

        if args.seal:
            r = c.post(f"/api/v1/twin/batches/{code}/seal", headers=h)
            print(f"Seal: {r.status_code} {r.text[:200]}")

    print(f"\nVerify at: {args.base_url}/verify/{code}  (SIMULATED badge is shown)")


if __name__ == "__main__":
    main()
