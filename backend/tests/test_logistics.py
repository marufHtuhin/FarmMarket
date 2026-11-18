import random
import httpx
import pytest
from app.services import logistics as L

DEPOT = (-1.2921, 36.8219)


def problem(n=14, seed=2, **kw):
    rng = random.Random(seed)
    stops = [L.Stop(f"s{i}", -1.29 + rng.uniform(-.2, .2), 36.82 + rng.uniform(-.2, .2),
                    rng.choice([30, 50, 70]), 8) for i in range(n)]
    return L.Problem(DEPOT, stops, kw.pop("vehicles", [L.Vehicle("a", 400), L.Vehicle("b", 400), L.Vehicle("c", 400)]), **kw)


def served(result):
    return sorted(s["stop_id"] for r in result["routes"] for s in r["stops"])


def test_every_stop_served_once_and_capacity_respected():
    p = problem()
    r = L.solve(p, L.HaversineProvider(), seed=1, time_limit_s=3)
    assert served(r) == sorted(s.id for s in p.stops)
    assert all(rt["load_kg"] <= rt["capacity_kg"] for rt in r["routes"])


def test_beats_or_matches_distance_only_baseline_on_objective():
    p = problem(n=20, seed=5)
    r = L.solve(p, L.HaversineProvider(), seed=1, time_limit_s=3)
    assert r["improvement_vs_baseline"]["objective_pct"] >= 0


def test_deterministic_for_same_seed():
    p = problem()
    a = L.solve(p, L.HaversineProvider(), seed=3, time_limit_s=3)
    b = L.solve(p, L.HaversineProvider(), seed=3, time_limit_s=3)
    assert a["totals"] == b["totals"]


def test_infeasible_inputs_are_rejected():
    with pytest.raises(L.InfeasibleError):
        L.solve(L.Problem(DEPOT, [L.Stop("big", -1.3, 36.8, 900)], [L.Vehicle("v", 500)]), L.HaversineProvider())
    with pytest.raises(L.InfeasibleError):
        L.solve(L.Problem(DEPOT, [L.Stop("a", -1.3, 36.8, 300), L.Stop("b", -1.3, 36.9, 300)], [L.Vehicle("v", 500)]), L.HaversineProvider())
    with pytest.raises(L.InfeasibleError):
        L.solve(L.Problem(DEPOT, [L.Stop("a", -1.3, 36.8, 10), L.Stop("a", -1.3, 36.9, 10)], [L.Vehicle("v", 500)]), L.HaversineProvider())


def test_time_window_lateness_and_waiting():
    p = L.Problem(DEPOT, [L.Stop("w", -1.30, 36.83, 50, 10, window=(120, 130))], [L.Vehicle("v", 500)])
    m = L.build_matrices(p, L.HaversineProvider())
    e = L.evaluate([1], p.vehicles[0], p, m, L.Weights(), detail=True)
    assert e.timeline[0]["service_start_min"] == 120 and e.late_min == 0          # waited for the window
    p.stops[0].window = (0, 1)                                                      # impossible: lateness counted
    assert L.evaluate([1], p.vehicles[0], p, m, L.Weights()).late_min > 0


def test_shelf_life_penalty_and_reefer_benefit():
    far = L.Stop("far", -1.6, 37.2, 50, 10, max_transit_min=30)
    p = L.Problem(DEPOT, [far], [L.Vehicle("plain", 500), L.Vehicle("reefer", 500, True, shelf_life_factor=20.0)])
    m = L.build_matrices(p, L.HaversineProvider())
    plain = L.evaluate([1], p.vehicles[0], p, m, L.Weights())
    reefer = L.evaluate([1], p.vehicles[1], p, m, L.Weights())
    assert plain.spoil_min > 0 and reefer.spoil_min == 0
    assert reefer.co2_kg > plain.co2_kg   # cooling costs carbon: the trade-off is visible


def test_carbon_increases_with_load():
    em = L.EmissionProfile()
    assert em.at(1.0) > em.at(0.5) > em.at(0.0)
    p = L.Problem(DEPOT, [L.Stop("s", -1.4, 36.9, 100)], [L.Vehicle("v", 1000)])
    m = L.build_matrices(p, L.HaversineProvider())
    light = L.evaluate([1], p.vehicles[0], p, m, L.Weights()).co2_kg
    p.stops[0].load_kg = 900
    assert L.evaluate([1], p.vehicles[0], p, m, L.Weights()).co2_kg > light


def test_collection_mode_runs_and_returns_loaded():
    p = problem(n=8, mode="collection")
    r = L.solve(p, L.HaversineProvider(), seed=1, time_limit_s=2)
    assert r["mode"] == "collection" and served(r) == sorted(s.id for s in p.stops)


def test_tradeoff_returns_one_row_per_weight():
    rows = L.tradeoff(problem(n=10), L.HaversineProvider(), [0, 5, 50], time_limit_s=1)
    assert [r["co2_per_kg_weight"] for r in rows] == [0, 5, 50]


def test_osrm_provider_parses_and_flags_unreachable():
    def handler(req):
        assert "36.821900" in str(req.url)
        return httpx.Response(200, json={"code": "Ok", "durations": [[0, 600], [660, 0]], "distances": [[0, 5000], [5200, 0]]})
    prov = L.OSRMProvider("http://osrm.test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    d, t = prov.matrix([(-1.2921, 36.8219), (-1.30, 36.85)])
    assert d[0][1] == 5.0 and t[0][1] == 10.0
    bad = L.OSRMProvider("http://osrm.test", client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"code": "Ok", "durations": [[0, None], [1, 0]], "distances": [[0, None], [1, 0]]}))))
    with pytest.raises(RuntimeError):
        bad.matrix([(0, 0), (1, 1)])


def test_weather_speed_factor_never_assumes_clear_sky():
    from app.services.datasources.openweather import speed_factor
    assert speed_factor(None)[0] == 1.0 and "unavailable" in speed_factor(None)[1]
    assert speed_factor([{"rain_mm": 25}])[0] == 0.75 and speed_factor([{"rain_mm": 3}])[0] == 0.9
