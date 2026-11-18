"""OR-Tools routing tests (Phase 6).

Solver tests are skipped when OR-Tools is not installed, so this file PASSES
either way; the 503 test covers the not-installed path (via monkeypatch when
OR-Tools IS installed, for real otherwise). Validation of infeasible input
runs before the OR-Tools import, so the InfeasibleError test needs no solver.
"""
import pytest

from app.services import logistics as L
from app.services import ortools_routing as OR

try:
    import ortools  # noqa: F401
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False

needs_ortools = pytest.mark.skipif(not HAS_ORTOOLS, reason="ortools not installed")

# Dhaka hub (config.py) and stops around the city.
DHAKA = (23.8103, 90.4125)


def stop(sid, lat, lon, load, window=None, needs_refrigeration=False, service_min=10.0):
    return OR.VRPStop(sid, lat, lon, load, service_min, window, needs_refrigeration)


def vehicle(vid, cap, refrigerated=False):
    return OR.VRPVehicle(vid, cap, refrigerated)


def scenario(stops, vehicles, **kw):
    kw.setdefault("time_limit_s", 2.0)
    return OR.VRPScenario(DHAKA, stops, vehicles, **kw)


def solve(scn):
    return OR.solve_vrp(scn, L.HaversineProvider().matrix)


def dhaka_payload(stops=None, vehicles=None, **extra):
    body = {
        "depot": {"lat": DHAKA[0], "lon": DHAKA[1]},
        "stops": stops or [
            {"id": "s1", "lat": 23.82, "lon": 90.42, "load_kg": 100},
            {"id": "s2", "lat": 23.79, "lon": 90.40, "load_kg": 100},
            {"id": "s3", "lat": 23.83, "lon": 90.44, "load_kg": 100},
        ],
        "vehicles": vehicles or [{"id": "v1", "capacity_kg": 500}],
        "time_limit_s": 2.0,
    }
    body.update(extra)
    return body


# ---------------------------------------------------------------- service level
def test_single_stop_exceeding_all_capacity_is_infeasible():
    with pytest.raises(OR.InfeasibleError, match="exceeds the largest vehicle"):
        solve(scenario([stop("big", 23.82, 90.42, 900)], [vehicle("v", 500)]))


def test_refrigerated_stop_without_reefer_is_infeasible():
    with pytest.raises(OR.InfeasibleError, match="refrigerat"):
        solve(scenario([stop("cold", 23.82, 90.42, 100, needs_refrigeration=True)],
                       [vehicle("plain", 500)]))


@needs_ortools
def test_capacity_respected_and_two_vehicles_used_when_needed():
    scn = scenario([stop("a", 23.82, 90.42, 400), stop("b", 23.79, 90.40, 400),
                    stop("c", 23.83, 90.44, 100)],
                   [vehicle("v1", 500), vehicle("v2", 500)])
    r = solve(scn)
    assert len(r["routes"]) == 2                      # 900 kg total cannot fit in one 500 kg van
    assert sorted(s for rt in r["routes"] for s in rt["stops"]) == ["a", "b", "c"]
    assert all(rt["load_kg"] <= rt["capacity_kg"] for rt in r["routes"])


@needs_ortools
def test_time_windows_respected():
    scn = scenario([stop("early", 23.82, 90.42, 100, window=(60, 240)),
                    stop("late", 23.79, 90.40, 100, window=(120, 300))],
                   [vehicle("v", 500)])
    r = solve(scn)
    arrivals = {s: a for rt in r["routes"] for s, a in zip(rt["stops"], rt["arrivals_min"])}
    assert 60 <= arrivals["early"] <= 240
    assert 120 <= arrivals["late"] <= 300


@needs_ortools
def test_refrigeration_respected():
    scn = scenario([stop("cold", 23.82, 90.42, 100, needs_refrigeration=True),
                    stop("p1", 23.79, 90.40, 100), stop("p2", 23.83, 90.44, 100)],
                   [vehicle("plain", 500), vehicle("reefer", 500, refrigerated=True)])
    r = solve(scn)
    for rt in r["routes"]:
        if "cold" in rt["stops"]:
            assert rt["refrigerated"] is True
            assert rt["vehicle"] == "reefer"


@needs_ortools
def test_baseline_and_savings_present_and_computed():
    scn = scenario([stop(f"s{i}", 23.78 + 0.01 * i, 90.40 + 0.01 * i, 100) for i in range(5)],
                   [vehicle("v1", 500), vehicle("v2", 500)])
    r = solve(scn)
    assert r["baseline"] is not None
    assert r["baseline"]["method"] == OR.BASELINE_METHOD
    assert r["baseline"]["distance_km"] > 0 and r["baseline"]["duration_min"] > 0
    assert set(r["savings_pct"]) == {"distance", "duration", "co2e"}
    # savings are a real comparison against the computed baseline, not hardcoded
    assert r["savings_pct"]["distance"] == pytest.approx(
        (1 - r["total_distance_km"] / r["baseline"]["distance_km"]) * 100, abs=0.15)


# ---------------------------------------------------------------- HTTP level
def test_optimize_requires_auth(client):
    r = client.post("/api/v1/logistics/optimize", json=dhaka_payload())
    assert r.status_code == 401


def test_optimize_503_when_ortools_absent(client, monkeypatch):
    """Real 503 when OR-Tools is missing; monkeypatched guard when installed."""
    from conftest import register
    h = register(client, "f@x.t", "farmer")
    if HAS_ORTOOLS:
        monkeypatch.setattr(OR, "ortools_available", lambda: False)
    r = client.post("/api/v1/logistics/optimize", json=dhaka_payload(), headers=h)
    assert r.status_code == 503
    assert "OR-Tools is not installed" in r.json()["detail"]
    assert "/api/v1/logistics/plan" in r.json()["detail"]


@needs_ortools
def test_optimize_haversine_response_labelled(client):
    from conftest import register
    h = register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/logistics/optimize", json=dhaka_payload(), headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["distance_basis"] == "haversine_estimate"
    assert any("Straight-line estimate" in n for n in body["notes"])
    assert body["total_distance_km"] > 0 and body["total_co2e_kg"] > 0
    assert "co2e_assumptions" in body and "Illustrative" in body["co2e_assumptions"]
    assert body["baseline"] is not None and set(body["savings_pct"]) == {"distance", "duration", "co2e"}
    assert sorted(s for rt in body["routes"] for s in rt["stops"]) == ["s1", "s2", "s3"]
    assert all(rt["load_kg"] <= rt["capacity_kg"] for rt in body["routes"])


@needs_ortools
def test_optimize_422_for_infeasible_input(client):
    from conftest import register
    h = register(client, "f@x.t", "farmer")
    bad = dhaka_payload(stops=[{"id": "big", "lat": 23.82, "lon": 90.42, "load_kg": 900}],
                        vehicles=[{"id": "v1", "capacity_kg": 500}])
    r = client.post("/api/v1/logistics/optimize", json=bad, headers=h)
    assert r.status_code == 422
    assert "exceeds the largest vehicle" in r.json()["detail"]


@needs_ortools
def test_optimize_accepts_plan_request_shape(client):
    """A body valid for /plan (no optimize-only fields) is valid for /optimize."""
    from conftest import register
    h = register(client, "f@x.t", "farmer")
    plan = client.post("/api/v1/logistics/plan", json=dhaka_payload(), headers=h)
    assert plan.status_code == 200, plan.text
    opt = client.post("/api/v1/logistics/optimize", json=dhaka_payload(), headers=h)
    assert opt.status_code == 200, opt.text
