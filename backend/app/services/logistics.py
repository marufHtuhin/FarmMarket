"""Multi-stop dispatch optimisation for perishables: transit time + carbon + freshness.

Objective (all in "minute-equivalents"):
    time_per_min * route_minutes
  + co2_per_kg   * kg CO2e                      (distance, load-dependent, + reefer hours)
  + lateness_per_min * minutes past time window (soft)
  + spoilage_per_min * minutes beyond shelf-life budget (soft)
  + vehicle_fixed    per vehicle used
Hard constraint: vehicle capacity.

Road data comes from a pluggable provider:
  * HaversineProvider  - straight line x detour factor (offline fallback, rough)
  * OSRMProvider       - real road network times/distances from an OSRM server
                         (OpenStreetMap-based; self-host for production volumes)
No proprietary satellite-imagery API is integrated; plug one in by implementing
`RoadProvider.matrix`.

Emission factors below are ILLUSTRATIVE DEFAULTS. Replace with measured fleet data or a
recognised source (e.g. GLEC Framework / DEFRA) before reporting carbon numbers.
"""
from __future__ import annotations
import math
import random
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

INF = float("inf")


# ---------------------------------------------------------------- road data
class RoadProvider(Protocol):
    def matrix(self, points: list[tuple[float, float]]) -> tuple[list[list[float]], list[list[float]]]:
        """Return (distance_km, time_min) square matrices for (lat, lon) points."""


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0088
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class HaversineProvider:
    def __init__(self, detour_factor: float = 1.35, avg_speed_kph: float = 40.0, speed_factor: float = 1.0):
        self.detour, self.speed, self.sf = detour_factor, avg_speed_kph, speed_factor

    def matrix(self, points):
        n = len(points)
        dist = [[0.0] * n for _ in range(n)]
        tm = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    d = haversine_km(points[i], points[j]) * self.detour
                    dist[i][j], tm[i][j] = d, d / (self.speed * self.sf) * 60
        return dist, tm


class OSRMProvider:
    def __init__(self, base_url: str, speed_factor: float = 1.0, client: httpx.Client | None = None):
        self.base, self.sf, self.client = base_url.rstrip("/"), speed_factor, client

    def matrix(self, points):
        if len(points) > 100:
            raise ValueError("OSRM table requests are limited to 100 points here")
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
        own = self.client is None
        c = self.client or httpx.Client(timeout=30)
        try:
            r = c.get(f"{self.base}/table/v1/driving/{coords}", params={"annotations": "duration,distance"})
            r.raise_for_status()
            data = r.json()
        finally:
            if own:
                c.close()
        if data.get("code") != "Ok":
            raise RuntimeError(f"OSRM error: {data.get('code')} {data.get('message', '')}")
        dur, dist = data["durations"], data["distances"]
        if any(v is None for row in dur + dist for v in row):
            raise RuntimeError("OSRM could not route between some points (unreachable)")
        return ([[v / 1000.0 for v in row] for row in dist],
                [[v / 60.0 / self.sf for v in row] for row in dur])


# ---------------------------------------------------------------- problem model
@dataclass(frozen=True)
class EmissionProfile:
    empty_kg_per_km: float = 0.20
    full_kg_per_km: float = 0.32
    reefer_kg_per_hour: float = 1.5

    def at(self, load_fraction: float) -> float:
        f = min(max(load_fraction, 0.0), 1.0)
        return self.empty_kg_per_km + (self.full_kg_per_km - self.empty_kg_per_km) * f


@dataclass
class Vehicle:
    id: str
    capacity_kg: float
    refrigerated: bool = False
    emissions: EmissionProfile = field(default_factory=EmissionProfile)
    shelf_life_factor: float = 1.0   # e.g. 2.0 if cold chain doubles the freshness budget


@dataclass
class Stop:
    id: str
    lat: float
    lon: float
    load_kg: float
    service_min: float = 10.0
    window: tuple[float, float] | None = None   # minutes after dispatch start
    max_transit_min: float | None = None        # freshness budget for this stop's goods


@dataclass
class Weights:
    time_per_min: float = 1.0
    co2_per_kg: float = 4.0
    lateness_per_min: float = 5.0
    spoilage_per_min: float = 10.0
    vehicle_fixed: float = 30.0


@dataclass
class Problem:
    depot: tuple[float, float]
    stops: list[Stop]
    vehicles: list[Vehicle]
    mode: str = "delivery"          # delivery: depot->stops ; collection: stops->depot
    start_min: float = 0.0


class InfeasibleError(ValueError):
    pass


@dataclass
class Matrices:
    dist: list[list[float]]
    time: list[list[float]]


@dataclass
class RouteEval:
    cost: float
    dist_km: float = 0.0
    minutes: float = 0.0
    co2_kg: float = 0.0
    late_min: float = 0.0
    spoil_min: float = 0.0
    timeline: list[dict] = field(default_factory=list)


def build_matrices(p: Problem, provider: RoadProvider) -> Matrices:
    pts = [p.depot] + [(s.lat, s.lon) for s in p.stops]
    d, t = provider.matrix(pts)
    return Matrices(d, t)


def validate(p: Problem) -> None:
    if not p.vehicles:
        raise InfeasibleError("At least one vehicle is required")
    if p.mode not in ("delivery", "collection"):
        raise InfeasibleError("mode must be 'delivery' or 'collection'")
    cap = max(v.capacity_kg for v in p.vehicles)
    ids = [s.id for s in p.stops]
    if len(set(ids)) != len(ids):
        raise InfeasibleError("Stop ids must be unique")
    for s in p.stops:
        if s.load_kg <= 0:
            raise InfeasibleError(f"Stop {s.id}: load_kg must be positive")
        if s.load_kg > cap:
            raise InfeasibleError(f"Stop {s.id}: load {s.load_kg} kg exceeds the largest vehicle ({cap} kg)")
        if s.window and s.window[0] > s.window[1]:
            raise InfeasibleError(f"Stop {s.id}: time window start is after end")
    if sum(s.load_kg for s in p.stops) > sum(v.capacity_kg for v in p.vehicles) + 1e-9:
        raise InfeasibleError("Total load exceeds total fleet capacity")


def evaluate(route: list[int], veh: Vehicle, p: Problem, m: Matrices, w: Weights, detail: bool = False) -> RouteEval:
    """Cost of one vehicle route. `route` holds stop indices 1..n (0 is the depot)."""
    if not route:
        return RouteEval(0.0)
    total = sum(p.stops[i - 1].load_kg for i in route)
    if total > veh.capacity_kg + 1e-9:
        return RouteEval(INF)
    delivery = p.mode == "delivery"
    load = total if delivery else 0.0
    t, prev = p.start_min, 0
    dist = co2 = late = spoil = 0.0
    loaded_at: dict[int, float] = {}
    tl: list[dict] = []
    for i in route:
        s = p.stops[i - 1]
        d = m.dist[prev][i]
        co2 += d * veh.emissions.at(max(load, 0.0) / veh.capacity_kg)
        dist += d
        t += m.time[prev][i]
        arrive = t
        start = max(t, s.window[0]) if s.window else t
        lt = max(0.0, start - s.window[1]) if s.window else 0.0
        late += lt
        if delivery:
            load -= s.load_kg
            if s.max_transit_min is not None:
                spoil += max(0.0, (start - p.start_min) - s.max_transit_min * veh.shelf_life_factor)
        else:
            load += s.load_kg
        t = start + s.service_min
        if not delivery:
            loaded_at[i] = t
        if detail:
            tl.append({"stop_id": s.id, "arrive_min": round(arrive, 1), "service_start_min": round(start, 1),
                       "depart_min": round(t, 1), "late_min": round(lt, 1)})
        prev = i
    d = m.dist[prev][0]
    co2 += d * veh.emissions.at(max(load, 0.0) / veh.capacity_kg)
    dist += d
    t += m.time[prev][0]
    if not delivery:
        for i, dep in loaded_at.items():
            mt = p.stops[i - 1].max_transit_min
            if mt is not None:
                spoil += max(0.0, (t - dep) - mt * veh.shelf_life_factor)
    minutes = t - p.start_min
    if veh.refrigerated:
        co2 += veh.emissions.reefer_kg_per_hour * minutes / 60
    cost = (w.time_per_min * minutes + w.co2_per_kg * co2 + w.lateness_per_min * late
            + w.spoilage_per_min * spoil + w.vehicle_fixed)
    return RouteEval(cost, dist, minutes, co2, late, spoil, tl)


# ---------------------------------------------------------------- solver
Routes = list[list[int]]   # routes[k] belongs to vehicles[k]


def _total(routes: Routes, p, m, w) -> float:
    return sum(evaluate(r, p.vehicles[k], p, m, w).cost for k, r in enumerate(routes))


def construct(p: Problem, m: Matrices, w: Weights) -> Routes:
    """Cheapest-insertion construction; heavy stops first so big loads claim big vehicles."""
    routes: Routes = [[] for _ in p.vehicles]
    costs = [0.0] * len(p.vehicles)
    order = sorted(range(1, len(p.stops) + 1), key=lambda i: -p.stops[i - 1].load_kg)
    for i in order:
        best = (INF, -1, -1)
        for k, v in enumerate(p.vehicles):
            for pos in range(len(routes[k]) + 1):
                cand = routes[k][:pos] + [i] + routes[k][pos:]
                c = evaluate(cand, v, p, m, w).cost
                if c < INF and c - costs[k] < best[0]:
                    best = (c - costs[k], k, pos)
        if best[1] < 0:
            raise InfeasibleError(f"Could not place stop {p.stops[i - 1].id} in any vehicle")
        _, k, pos = best
        routes[k].insert(pos, i)
        costs[k] = evaluate(routes[k], p.vehicles[k], p, m, w).cost
    return routes


def nearest_neighbour_baseline(p: Problem, m: Matrices) -> Routes:
    """Naive reference: nearest unvisited stop that fits; ignores carbon, windows and freshness."""
    left = set(range(1, len(p.stops) + 1))
    routes: Routes = [[] for _ in p.vehicles]
    for k, v in enumerate(p.vehicles):
        cap, cur = v.capacity_kg, 0
        while left:
            fits = [i for i in left if p.stops[i - 1].load_kg <= cap + 1e-9]
            if not fits:
                break
            nxt = min(fits, key=lambda i: m.dist[cur][i])
            routes[k].append(nxt); left.remove(nxt)
            cap -= p.stops[nxt - 1].load_kg; cur = nxt
    if left:
        raise InfeasibleError("Baseline could not place every stop (fleet too small for greedy packing)")
    return routes


def improve(routes: Routes, p: Problem, m: Matrices, w: Weights, max_passes: int = 50,
            deadline: float | None = None) -> Routes:
    """First-improvement local search: relocate (seg<=3), swap, intra-route 2-opt."""
    routes = [r[:] for r in routes]
    ev = lambda k, r: evaluate(r, p.vehicles[k], p, m, w).cost  # noqa: E731
    costs = [ev(k, r) for k, r in enumerate(routes)]
    for _ in range(max_passes):
        improved = False
        if deadline and time.monotonic() > deadline:
            break
        # 2-opt inside a route
        for k, r in enumerate(routes):
            for a in range(len(r) - 1):
                for b in range(a + 1, len(r)):
                    cand = r[:a] + r[a:b + 1][::-1] + r[b + 1:]
                    c = ev(k, cand)
                    if c < costs[k] - 1e-9:
                        routes[k], costs[k], r, improved = cand, c, cand, True
        # relocate segments (len 1..3) between/inside routes
        for k1 in range(len(routes)):
            for seg in (1, 2, 3):
                a = 0
                while a + seg <= len(routes[k1]):
                    segment = routes[k1][a:a + seg]
                    rest = routes[k1][:a] + routes[k1][a + seg:]
                    base_rest = ev(k1, rest)
                    done = False
                    for k2 in range(len(routes)):
                        tgt = rest if k2 == k1 else routes[k2]
                        for pos in range(len(tgt) + 1):
                            if k2 == k1 and pos == a:
                                continue
                            new_t = tgt[:pos] + segment + tgt[pos:]
                            c2 = ev(k2, new_t)
                            if k2 == k1:
                                gain = costs[k1] - c2
                            else:
                                gain = costs[k1] + costs[k2] - base_rest - c2
                            if gain > 1e-9:
                                if k2 == k1:
                                    routes[k1], costs[k1] = new_t, c2
                                else:
                                    routes[k1], costs[k1] = rest, base_rest
                                    routes[k2], costs[k2] = new_t, c2
                                improved = done = True
                                break
                        if done:
                            break
                    if not done:
                        a += 1
        # swap single stops across routes
        for k1 in range(len(routes)):
            for k2 in range(k1 + 1, len(routes)):
                for i in range(len(routes[k1])):
                    for j in range(len(routes[k2])):
                        r1, r2 = routes[k1][:], routes[k2][:]
                        r1[i], r2[j] = r2[j], r1[i]
                        c1, c2 = ev(k1, r1), ev(k2, r2)
                        if c1 + c2 < costs[k1] + costs[k2] - 1e-9:
                            routes[k1], routes[k2], costs[k1], costs[k2], improved = r1, r2, c1, c2, True
        if not improved:
            break
    return routes


def solve(p: Problem, provider: RoadProvider, w: Weights | None = None, restarts: int = 8,
          seed: int = 0, time_limit_s: float = 5.0) -> dict:
    w = w or Weights()
    validate(p)
    m = build_matrices(p, provider)
    return solve_with_matrices(p, m, w, restarts, seed, time_limit_s)


def solve_with_matrices(p: Problem, m: Matrices, w: Weights, restarts: int = 8, seed: int = 0,
                        time_limit_s: float = 5.0) -> dict:
    if not p.stops:
        return {"routes": [], "totals": _totals([]), "baseline": None, "improvement_vs_baseline": None}
    deadline = time.monotonic() + time_limit_s
    rng = random.Random(seed)
    best = improve(construct(p, m, w), p, m, w, deadline=deadline)
    best_cost = _total(best, p, m, w)
    for _ in range(restarts):                       # iterated local search: perturb then re-optimise
        if time.monotonic() > deadline:
            break
        cand = [r[:] for r in best]
        for _ in range(2):
            donors = [k for k, r in enumerate(cand) if r]
            k1 = rng.choice(donors)
            i = cand[k1].pop(rng.randrange(len(cand[k1])))
            k2 = rng.randrange(len(cand))
            cand[k2].insert(rng.randrange(len(cand[k2]) + 1), i)
        if any(evaluate(r, p.vehicles[k], p, m, w).cost == INF for k, r in enumerate(cand)):
            continue
        cand = improve(cand, p, m, w, deadline=deadline)
        c = _total(cand, p, m, w)
        if c < best_cost - 1e-9:
            best, best_cost = cand, c
    result = _describe(best, p, m, w)
    try:
        base_routes = nearest_neighbour_baseline(p, m)
        base = _describe(base_routes, p, m, w)
        result["baseline"] = {"method": "nearest-neighbour (distance only)", "totals": base["totals"]}
        bc = base["totals"]["objective_cost"]
        result["improvement_vs_baseline"] = {
            "objective_pct": round((1 - best_cost / bc) * 100, 1) if bc > 0 else 0.0,
            "co2_pct": _pct(base["totals"]["co2_kg"], result["totals"]["co2_kg"]),
            "minutes_pct": _pct(base["totals"]["minutes"], result["totals"]["minutes"])}
    except InfeasibleError:
        result["baseline"], result["improvement_vs_baseline"] = None, None
    return result


def _pct(before: float, after: float) -> float:
    return round((1 - after / before) * 100, 1) if before > 0 else 0.0


def _totals(parts: list[RouteEval]) -> dict:
    return {"vehicles_used": len(parts), "distance_km": round(sum(e.dist_km for e in parts), 2),
            "minutes": round(sum(e.minutes for e in parts), 1), "co2_kg": round(sum(e.co2_kg for e in parts), 2),
            "late_min": round(sum(e.late_min for e in parts), 1), "spoilage_risk_min": round(sum(e.spoil_min for e in parts), 1),
            "objective_cost": round(sum(e.cost for e in parts), 2)}


def _describe(routes: Routes, p: Problem, m: Matrices, w: Weights) -> dict:
    out, evals = [], []
    for k, r in enumerate(routes):
        if not r:
            continue
        v = p.vehicles[k]
        e = evaluate(r, v, p, m, w, detail=True)
        evals.append(e)
        out.append({"vehicle_id": v.id, "refrigerated": v.refrigerated,
                    "load_kg": round(sum(p.stops[i - 1].load_kg for i in r), 1),
                    "capacity_kg": v.capacity_kg, "stops": e.timeline, "distance_km": round(e.dist_km, 2),
                    "minutes": round(e.minutes, 1), "co2_kg": round(e.co2_kg, 2),
                    "late_min": round(e.late_min, 1), "spoilage_risk_min": round(e.spoil_min, 1)})
    return {"mode": p.mode, "routes": out, "totals": _totals(evals)}


def tradeoff(p: Problem, provider: RoadProvider, co2_weights: list[float], base: Weights | None = None,
             seed: int = 0, time_limit_s: float = 2.0) -> list[dict]:
    """Re-solve under several carbon weights to expose the time-vs-carbon trade-off."""
    validate(p)
    m = build_matrices(p, provider)
    out = []
    for cw in co2_weights:
        w = Weights(**{**(base or Weights()).__dict__, "co2_per_kg": cw})
        r = solve_with_matrices(p, m, w, restarts=4, seed=seed, time_limit_s=time_limit_s)
        out.append({"co2_per_kg_weight": cw, **r["totals"]})
    return out
