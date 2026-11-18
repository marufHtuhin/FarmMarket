"""OR-Tools vehicle-routing optimisation for FarmMarket logistics (Phase 6).

This module is OPTIONAL: OR-Tools lives in ``requirements-ortools.txt`` and is
imported lazily inside :func:`solve_vrp`, so this module (and the whole app)
imports fine when OR-Tools is absent. Callers must check
:func:`ortools_available` first; ``POST /api/v1/logistics/optimize`` returns
503 when it is missing and never silently substitutes the heuristic planner.

Model
-----
* One depot (index 0) + one location per stop; one OR-Tools vehicle per fleet
  vehicle.
* Capacity: a dimension over load (0.1 kg resolution); a route's load can
  never exceed its vehicle's capacity.
* Time windows: a time dimension (seconds) with slack for waiting and service
  times folded into the transit callback, so a vehicle's cumul value at a stop
  is the service-start time and must fall inside the stop's window.
* Refrigeration: a stop flagged ``needs_refrigeration`` may only be served by
  a vehicle flagged ``refrigerated`` (enforced with ``VehicleVar.SetValues``).
* Objective: minimise a weighted sum of travel time + distance + CO2e, with
  default weights time 0.5 / distance 0.3 / co2e 0.2 (configurable per
  request; weights are normalised to sum to 1). CO2e per arc uses the
  vehicle's load-interpolated emission factor at 50% load plus reefer energy
  for refrigerated vehicles -- an approximation, because the exact load on an
  arc depends on the route; final reported CO2e is recomputed exactly with
  ``services.logistics.evaluate`` on the solved routes.
* Search: PATH_CHEAPEST_ARC first solution + GUIDED_LOCAL_SEARCH improvement,
  bounded by ``scenario.time_limit_s`` (default 10 s).

Distance/time matrices come from a caller-supplied function (OSRM road data
or haversine estimates), so this module never does I/O itself.

The returned baseline is a computed nearest-neighbour ordering over the same
stops and vehicles (capacity- and refrigeration-aware), not a hardcoded
number, so ``savings_pct`` is a real comparison.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import logistics as L

# Objective weights: minimise w_time * minutes + w_distance * km + w_co2e * kg CO2e.
DEFAULT_WEIGHTS: dict[str, float] = {"time": 0.5, "distance": 0.3, "co2e": 0.2}
DEFAULT_TIME_LIMIT_S: float = 10.0
BASELINE_METHOD = "nearest-neighbour visit order, same stops/vehicles"

# Integer scaling for the OR-Tools model (it works in integers).
_LOAD_SCALE = 10          # 0.1 kg resolution for demands/capacities
_COST_SCALE = 100         # objective kept to 0.01 weighted units
_HORIZON_S = 24 * 3600    # default time-dimension horizon (extended if windows need it)

InfeasibleError = L.InfeasibleError


class OrtoolsNotInstalledError(RuntimeError):
    """Raised when OR-Tools is needed but not installed (maps to HTTP 503)."""


def ortools_available() -> bool:
    try:
        import ortools  # noqa: F401
        return True
    except ImportError:
        return False


def _load_ortools():
    """Import OR-Tools lazily so this module imports without it installed."""
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError as e:
        raise OrtoolsNotInstalledError(
            "OR-Tools is not installed. Install requirements-ortools.txt, or use "
            "POST /api/v1/logistics/plan (heuristic planner)."
        ) from e
    return pywrapcp, routing_enums_pb2


# ---------------------------------------------------------------- scenario
@dataclass
class VRPStop:
    id: str
    lat: float
    lon: float
    load_kg: float
    service_min: float = 10.0
    window: tuple[float, float] | None = None   # [earliest, latest] minutes after dispatch
    needs_refrigeration: bool = False
    max_transit_min: float | None = None        # accepted for API parity; not a hard
    # constraint in the OR-Tools model (the heuristic planner penalises it softly)


@dataclass
class VRPVehicle:
    id: str
    capacity_kg: float
    refrigerated: bool = False
    emissions: L.EmissionProfile = field(default_factory=L.EmissionProfile)
    shelf_life_factor: float = 1.0


@dataclass
class VRPScenario:
    depot: tuple[float, float]
    stops: list[VRPStop]
    vehicles: list[VRPVehicle]
    mode: str = "delivery"
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    time_limit_s: float = DEFAULT_TIME_LIMIT_S

    def normalised_weights(self) -> dict[str, float]:
        w = {k: max(float(self.weights.get(k, DEFAULT_WEIGHTS[k])), 0.0)
             for k in ("time", "distance", "co2e")}
        total = sum(w.values())
        if total <= 0:
            return dict(DEFAULT_WEIGHTS)
        return {k: v / total for k, v in w.items()}


def co2e_assumptions_text() -> str:
    """Explicit CO2e assumptions, reusing the factors from services/logistics.py."""
    d = L.EmissionProfile()
    return (
        f"Load-interpolated emission factor {d.empty_kg_per_km:.2f} (empty) to "
        f"{d.full_kg_per_km:.2f} (full) kg CO2e/km by vehicle load fraction, plus "
        f"{d.reefer_kg_per_hour:.1f} kg CO2e/hour for refrigerated vehicles. "
        "Illustrative defaults from services/logistics.py -- replace with measured "
        "fleet data (e.g. GLEC Framework / DEFRA) before reporting carbon numbers."
    )


# ---------------------------------------------------------------- validation
def validate(scenario: VRPScenario) -> None:
    if not scenario.vehicles:
        raise InfeasibleError("At least one vehicle is required")
    if scenario.mode not in ("delivery", "collection"):
        raise InfeasibleError("mode must be 'delivery' or 'collection'")
    ids = [s.id for s in scenario.stops]
    if len(set(ids)) != len(ids):
        raise InfeasibleError("Stop ids must be unique")
    cap = max(v.capacity_kg for v in scenario.vehicles)
    reef_cap = max((v.capacity_kg for v in scenario.vehicles if v.refrigerated), default=0.0)
    for s in scenario.stops:
        if s.load_kg <= 0:
            raise InfeasibleError(f"Stop {s.id}: load_kg must be positive")
        if s.load_kg > cap:
            raise InfeasibleError(
                f"Stop {s.id}: load {s.load_kg} kg exceeds the largest vehicle ({cap} kg)")
        if s.needs_refrigeration and s.load_kg > reef_cap:
            raise InfeasibleError(
                f"Stop {s.id}: needs refrigeration and its load {s.load_kg} kg exceeds the "
                f"largest refrigerated vehicle ({reef_cap} kg)")
        if s.window and s.window[0] > s.window[1]:
            raise InfeasibleError(f"Stop {s.id}: time window start is after end")
    if any(s.needs_refrigeration for s in scenario.stops) and reef_cap <= 0:
        raise InfeasibleError("A stop needs refrigeration but no vehicle is refrigerated")
    if sum(s.load_kg for s in scenario.stops) > sum(v.capacity_kg for v in scenario.vehicles) + 1e-9:
        raise InfeasibleError("Total load exceeds total fleet capacity")


def _as_problem(scenario: VRPScenario) -> L.Problem:
    """Mirror of the scenario in services.logistics terms, for exact metrics."""
    return L.Problem(
        depot=scenario.depot, mode=scenario.mode,
        stops=[L.Stop(s.id, s.lat, s.lon, s.load_kg, s.service_min, s.window, s.max_transit_min)
               for s in scenario.stops],
        vehicles=[L.Vehicle(v.id, v.capacity_kg, v.refrigerated, v.emissions, v.shelf_life_factor)
                  for v in scenario.vehicles])


# ---------------------------------------------------------------- baseline
def nearest_neighbour_routes(scenario: VRPScenario, dist: list[list[float]]) -> list[list[int]] | None:
    """Greedy nearest-neighbour ordering over the same stops/vehicles.

    Capacity- and refrigeration-aware; a stop that fits nowhere in the greedy
    pass is retried with cheapest insertion into any feasible route. Returns
    ``None`` only if some stop still cannot be placed (pathological packing).
    Routes hold 1-based stop indices (0 is the depot), as in services.logistics.
    """
    left = set(range(1, len(scenario.stops) + 1))
    routes: list[list[int]] = [[] for _ in scenario.vehicles]
    loads = [0.0] * len(scenario.vehicles)
    for k, v in enumerate(scenario.vehicles):
        cur = 0
        while left:
            fits = [i for i in left
                    if loads[k] + scenario.stops[i - 1].load_kg <= v.capacity_kg + 1e-9
                    and (not scenario.stops[i - 1].needs_refrigeration or v.refrigerated)]
            if not fits:
                break
            nxt = min(fits, key=lambda i: dist[cur][i])
            routes[k].append(nxt)
            left.remove(nxt)
            loads[k] += scenario.stops[nxt - 1].load_kg
            cur = nxt
    # Second chance: cheapest insertion for anything the greedy pass stranded.
    for i in sorted(left):
        s = scenario.stops[i - 1]
        best: tuple[float, int, int] | None = None
        for k, v in enumerate(scenario.vehicles):
            if loads[k] + s.load_kg > v.capacity_kg + 1e-9:
                continue
            if s.needs_refrigeration and not v.refrigerated:
                continue
            seq = [0] + routes[k] + [0]
            for pos in range(len(routes[k]) + 1):
                extra = dist[seq[pos]][i] + dist[i][seq[pos + 1]] - dist[seq[pos]][seq[pos + 1]]
                if best is None or extra < best[0]:
                    best = (extra, k, pos)
        if best is None:
            return None
        _, k, pos = best
        routes[k].insert(pos, i)
        loads[k] += s.load_kg
        left.remove(i)
    return routes


def _pct(before: float, after: float) -> float:
    return round((1 - after / before) * 100, 1) if before > 0 else 0.0


def _describe_routes(routes: list[list[int]], problem: L.Problem, m: L.Matrices,
                     scenario: VRPScenario, arrivals: list[list[float]] | None = None) -> tuple[list[dict], dict]:
    """Per-route metrics (exact, via services.logistics.evaluate) + totals."""
    out, evals = [], []
    for k, r in enumerate(routes):
        if not r:
            continue
        v = problem.vehicles[k]
        e = L.evaluate(r, v, problem, m, L.Weights(), detail=True)
        evals.append(e)
        arr = arrivals[k] if arrivals else [t["service_start_min"] for t in e.timeline]
        out.append({"vehicle": v.id, "vehicle_id": v.id, "refrigerated": v.refrigerated,
                    "stops": [problem.stops[i - 1].id for i in r],
                    "arrivals_min": [round(a, 1) for a in arr],
                    "distance_km": round(e.dist_km, 2), "duration_min": round(e.minutes, 1),
                    "load_kg": round(sum(problem.stops[i - 1].load_kg for i in r), 1),
                    "capacity_kg": v.capacity_kg, "co2e_kg": round(e.co2_kg, 2)})
    totals = {"distance_km": round(sum(e.dist_km for e in evals), 2),
              "duration_min": round(sum(e.minutes for e in evals), 1),
              "co2e_kg": round(sum(e.co2_kg for e in evals), 2)}
    return out, totals


# ---------------------------------------------------------------- solver
def solve_vrp(scenario: VRPScenario, distance_matrix_fn) -> dict:
    """Solve the scenario with OR-Tools.

    ``distance_matrix_fn(points)`` takes ``[(lat, lon), ...]`` (depot first)
    and returns ``(distance_km, time_min)`` square matrices -- OSRM or
    haversine, supplied by the caller. Raises :class:`InfeasibleError` for
    infeasible input and :class:`OrtoolsNotInstalledError` when OR-Tools is
    absent (validation runs first, so bad input is still reported as 422
    even without OR-Tools installed).
    """
    validate(scenario)
    pywrapcp, routing_enums_pb2 = _load_ortools()

    points = [scenario.depot] + [(s.lat, s.lon) for s in scenario.stops]
    dist, tmin = distance_matrix_fn(points)
    problem = _as_problem(scenario)
    matrices = L.Matrices(dist, tmin)
    n = len(points)
    weights = scenario.normalised_weights()

    manager = pywrapcp.RoutingIndexManager(n, len(scenario.vehicles), 0)
    routing = pywrapcp.RoutingModel(manager)

    service_s = [0] + [int(round(s.service_min * 60)) for s in scenario.stops]
    travel_s = [[int(round(tmin[i][j] * 60)) for j in range(n)] for i in range(n)]

    def time_cb(from_idx, to_idx):
        # Transit = travel + service time at the departure node, so the time
        # dimension's cumul value at a stop is its service-start time.
        f, t = manager.IndexToNode(from_idx), manager.IndexToNode(to_idx)
        return travel_s[f][t] + service_s[f]

    time_cb_idx = routing.RegisterTransitCallback(time_cb)

    # Per-vehicle arc cost: weighted time + distance + CO2e (mid-load factor).
    for k, v in enumerate(scenario.vehicles):
        em = v.emissions
        reefer_per_min = (em.reefer_kg_per_hour / 60.0) if v.refrigerated else 0.0

        def cost_cb(from_idx, to_idx, _em=em, _reefer=reefer_per_min):
            f, t = manager.IndexToNode(from_idx), manager.IndexToNode(to_idx)
            d, tm = dist[f][t], tmin[f][t]
            co2 = d * _em.at(0.5) + _reefer * tm
            return int(round(_COST_SCALE * (weights["time"] * tm + weights["distance"] * d
                                            + weights["co2e"] * co2)))

        routing.SetArcCostEvaluatorOfVehicle(routing.RegisterTransitCallback(cost_cb), k)

    def demand_cb(from_idx):
        node = manager.IndexToNode(from_idx)
        return 0 if node == 0 else int(round(scenario.stops[node - 1].load_kg * _LOAD_SCALE))

    # NB: OR-Tools renamed this method (plural -> singular) in 9.12; support both.
    add_capacity_dim = getattr(routing, "AddDimensionWithVehicleCapacities", None) or getattr(
        routing, "AddDimensionWithVehicleCapacity")
    add_capacity_dim(
        routing.RegisterUnaryTransitCallback(demand_cb), 0,
        [int(round(v.capacity_kg * _LOAD_SCALE)) for v in scenario.vehicles],
        True, "Capacity")

    horizon = _HORIZON_S
    for s in scenario.stops:
        if s.window:
            horizon = max(horizon, int((s.window[1] + 60) * 60))
    routing.AddDimension(time_cb_idx, horizon, horizon, True, "Time")
    time_dim = routing.GetDimensionOrDie("Time")
    for i, s in enumerate(scenario.stops, start=1):
        if s.window:
            time_dim.CumulVar(manager.NodeToIndex(i)).SetRange(
                int(round(s.window[0] * 60)), int(round(s.window[1] * 60)))
    # Refrigeration: a refrigerated stop may only use refrigerated vehicles.
    reef_vehicles = [k for k, v in enumerate(scenario.vehicles) if v.refrigerated]
    for i, s in enumerate(scenario.stops, start=1):
        if s.needs_refrigeration:
            routing.VehicleVar(manager.NodeToIndex(i)).SetValues(reef_vehicles)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromMilliseconds(int(round(max(1.0, float(scenario.time_limit_s)) * 1000)))
    params.log_search = False
    solution = routing.SolveWithParameters(params)
    if solution is None:
        raise InfeasibleError(
            "OR-Tools could not find a feasible solution for this scenario "
            "(check time windows, refrigeration requirements and capacities)")
    if solution.ObjectiveValue() < 0:
        raise InfeasibleError("OR-Tools returned an invalid solution")

    routes: list[list[int]] = []
    arrivals: list[list[float]] = []
    for k in range(len(scenario.vehicles)):
        route, arr, idx = [], [], routing.Start(k)
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            if node != 0:
                route.append(node)
                arr.append(solution.Value(time_dim.CumulVar(idx)) / 60.0)
            idx = solution.Value(routing.NextVar(idx))
        routes.append(route)
        arrivals.append(arr)

    described, totals = _describe_routes(routes, problem, matrices, scenario, arrivals)

    # Computed baseline: nearest-neighbour over the same stops/vehicles.
    baseline = None
    savings = None
    base_routes = nearest_neighbour_routes(scenario, dist)
    if base_routes is not None:
        _, base_totals = _describe_routes(base_routes, problem, matrices, scenario)
        baseline = {"distance_km": base_totals["distance_km"],
                    "duration_min": base_totals["duration_min"],
                    "co2e_kg": base_totals["co2e_kg"], "method": BASELINE_METHOD}
        savings = {"distance": _pct(base_totals["distance_km"], totals["distance_km"]),
                   "duration": _pct(base_totals["duration_min"], totals["duration_min"]),
                   "co2e": _pct(base_totals["co2e_kg"], totals["co2e_kg"])}

    return {"routes": described,
            "total_distance_km": totals["distance_km"],
            "total_duration_min": totals["duration_min"],
            "total_co2e_kg": totals["co2e_kg"],
            "baseline": baseline, "savings_pct": savings,
            "weights": weights, "solver": "ortools"}
