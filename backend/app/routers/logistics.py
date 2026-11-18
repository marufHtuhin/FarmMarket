from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..config import env, get_hub
from ..security import get_current_user
from ..services import logistics as L
from ..services import ortools_routing as OR
from ..services.datasources import openmeteo

router = APIRouter(prefix="/api/v1/logistics", tags=["logistics"])


class PointIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class StopIn(PointIn):
    id: str = Field(min_length=1, max_length=40)
    load_kg: float = Field(gt=0, le=50_000)
    service_min: float = Field(10, ge=0, le=240)
    window_start_min: float | None = Field(None, ge=0)
    window_end_min: float | None = Field(None, ge=0)
    max_transit_min: float | None = Field(None, gt=0)
    needs_refrigeration: bool = False   # /optimize only: such stops use refrigerated vehicles


class VehicleIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    capacity_kg: float = Field(gt=0, le=100_000)
    refrigerated: bool = False
    shelf_life_factor: float = Field(1.0, ge=1.0, le=5.0)
    empty_kg_co2_per_km: float | None = Field(None, ge=0)
    full_kg_co2_per_km: float | None = Field(None, ge=0)
    reefer_kg_co2_per_hour: float | None = Field(None, ge=0)


class WeightsIn(BaseModel):
    time_per_min: float = Field(1.0, ge=0)
    co2_per_kg: float = Field(4.0, ge=0)
    lateness_per_min: float = Field(5.0, ge=0)
    spoilage_per_min: float = Field(10.0, ge=0)
    vehicle_fixed: float = Field(30.0, ge=0)


class PlanIn(BaseModel):
    depot: PointIn
    stops: list[StopIn] = Field(min_length=1, max_length=60)
    vehicles: list[VehicleIn] = Field(min_length=1, max_length=10)
    mode: str = Field("delivery", pattern="^(delivery|collection)$")
    weights: WeightsIn = WeightsIn()
    road_provider: str = Field("haversine", pattern="^(haversine|osrm)$")
    hub_id: str | None = None            # fetch weather for this hub and derate speeds
    carbon_tradeoff: list[float] | None = Field(None, max_length=6)


class ObjectiveWeightsIn(BaseModel):
    """OR-Tools objective weights (normalised to sum to 1 by the solver).

    Defaults: time 0.5 / distance 0.3 / co2e 0.2.
    """
    time: float = Field(0.5, ge=0)
    distance: float = Field(0.3, ge=0)
    co2e: float = Field(0.2, ge=0)


class OptimizeIn(PlanIn):
    """Same request shape as /plan, plus OR-Tools-only options (all defaulted)."""
    objective_weights: ObjectiveWeightsIn = ObjectiveWeightsIn()
    time_limit_s: float = Field(10.0, ge=1, le=120)


def _vehicle(v: VehicleIn) -> L.Vehicle:
    d = L.EmissionProfile()
    em = L.EmissionProfile(v.empty_kg_co2_per_km if v.empty_kg_co2_per_km is not None else d.empty_kg_per_km,
                           v.full_kg_co2_per_km if v.full_kg_co2_per_km is not None else d.full_kg_per_km,
                           v.reefer_kg_co2_per_hour if v.reefer_kg_co2_per_hour is not None else d.reefer_kg_per_hour)
    return L.Vehicle(v.id, v.capacity_kg, v.refrigerated, em, v.shelf_life_factor)


@router.post("/plan")
def plan(data: PlanIn, user=Depends(get_current_user)):
    notes: list[str] = ["Emission factors are illustrative defaults unless you supply your own per vehicle."]
    speed, wx_note = 1.0, None
    if data.hub_id:
        hub = get_hub(data.hub_id)
        if hub is None:
            raise HTTPException(404, f"Unknown hub '{data.hub_id}'")
        speed, wx_note = openmeteo.speed_factor(
            openmeteo.fetch_daily_outlook(hub.lat, hub.lon))
        notes.append(wx_note)
    if data.road_provider == "osrm":
        base = env("OSRM_BASE_URL")
        if not base:
            raise HTTPException(400, "OSRM_BASE_URL is not configured on the server")
        provider = L.OSRMProvider(base, speed_factor=speed)
    else:
        provider = L.HaversineProvider(speed_factor=speed)
        notes.append("Using straight-line distance x detour factor, not real road data. Set road_provider=osrm for road routing.")
    problem = L.Problem(
        depot=(data.depot.lat, data.depot.lon), mode=data.mode,
        stops=[L.Stop(s.id, s.lat, s.lon, s.load_kg, s.service_min,
                      (s.window_start_min, s.window_end_min) if s.window_start_min is not None and s.window_end_min is not None else None,
                      s.max_transit_min) for s in data.stops],
        vehicles=[_vehicle(v) for v in data.vehicles])
    weights = L.Weights(**data.weights.model_dump())
    try:
        result = L.solve(problem, provider, weights, seed=0, time_limit_s=5.0)
        if data.carbon_tradeoff:
            result["carbon_tradeoff"] = L.tradeoff(problem, provider, data.carbon_tradeoff, weights)
    except L.InfeasibleError as e:
        raise HTTPException(422, str(e))
    except Exception as e:                      # road provider/network failures
        raise HTTPException(502, f"Road data provider failed: {e}")
    result["notes"] = notes
    result["road_provider"] = data.road_provider
    return result


def _vrp_vehicle(v: VehicleIn) -> OR.VRPVehicle:
    return OR.VRPVehicle(v.id, v.capacity_kg, v.refrigerated, _vehicle(v).emissions, v.shelf_life_factor)


@router.post("/optimize")
def optimize(data: OptimizeIn, user=Depends(get_current_user)):
    """OR-Tools vehicle routing (capacity + time windows + refrigeration).

    Same request body as /plan. Returns 503 when OR-Tools is not installed --
    it never silently substitutes the heuristic planner.
    """
    if not OR.ortools_available():
        raise HTTPException(
            503, "OR-Tools is not installed. Install requirements-ortools.txt, or use "
                 "POST /api/v1/logistics/plan (heuristic planner).")
    notes: list[str] = ["Emission factors are illustrative defaults unless you supply your own per vehicle."]
    speed, wx_note = 1.0, None
    if data.hub_id:
        hub = get_hub(data.hub_id)
        if hub is None:
            raise HTTPException(404, f"Unknown hub '{data.hub_id}'")
        speed, wx_note = openmeteo.speed_factor(
            openmeteo.fetch_daily_outlook(hub.lat, hub.lon))
        notes.append(wx_note)

    # Distance basis: OSRM road distances when requested and configured, with
    # a haversine fallback (recorded in the response) if OSRM is unreachable.
    state = {"basis": "haversine_estimate"}
    if data.road_provider == "osrm":
        base = env("OSRM_BASE_URL")
        if not base:
            raise HTTPException(400, "OSRM_BASE_URL is not configured on the server")
        osrm = L.OSRMProvider(base, speed_factor=speed)
        hav = L.HaversineProvider(speed_factor=speed)

        def matrix_fn(pts, _osrm=osrm, _hav=hav, _state=state, _notes=notes):
            try:
                m = _osrm.matrix(pts)
                _state["basis"] = "osrm"
                return m
            except Exception as e:
                _state["basis"] = "haversine_estimate"
                _notes.append(f"OSRM failed ({e}); fell back to haversine estimate.")
                return _hav.matrix(pts)
    else:
        matrix_fn = L.HaversineProvider(speed_factor=speed).matrix
        notes.append("Straight-line estimate — not road distance")

    scenario = OR.VRPScenario(
        depot=(data.depot.lat, data.depot.lon), mode=data.mode,
        stops=[OR.VRPStop(s.id, s.lat, s.lon, s.load_kg, s.service_min,
                          (s.window_start_min, s.window_end_min)
                          if s.window_start_min is not None and s.window_end_min is not None else None,
                          s.needs_refrigeration, s.max_transit_min) for s in data.stops],
        vehicles=[_vrp_vehicle(v) for v in data.vehicles],
        weights=data.objective_weights.model_dump(), time_limit_s=data.time_limit_s)
    try:
        result = OR.solve_vrp(scenario, matrix_fn)
    except OR.OrtoolsNotInstalledError as e:
        raise HTTPException(503, str(e))
    except OR.InfeasibleError as e:
        raise HTTPException(422, str(e))
    result["distance_basis"] = state["basis"]
    result["co2e_assumptions"] = OR.co2e_assumptions_text()
    result["notes"] = notes
    result["road_provider"] = data.road_provider
    return result
