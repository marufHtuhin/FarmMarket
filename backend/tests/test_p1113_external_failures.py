"""Phase 11 (audit/p11-13): external-service failure handling, ALL MOCKED.

These tests prove the app degrades honestly when a dependency fails; they
do NOT prove the real services work. Live checks are separate (Open-Meteo
and Carto/OSM tiles are exercised live by the smoke script; Gemini,
OSRM and MySQL are BLOCKED in this VM — no key/server).

Mocked failures covered here:
- World Bank unreachable in the forecast-context endpoint
- Open-Meteo failure in the forecast-context endpoint (weather is keyless
  Open-Meteo since 2026-11-17; the OpenWeather adapter is legacy)
- OSRM unreachable in logistics /plan (502) and /optimize (haversine fallback)
- httpx failure inside openweather.fetch_daily_outlook (legacy module)
- database failure on a normal endpoint (generic 500, no leak)
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import register
from app.database import get_db
from app.main import app as app_obj
from app.services import logistics as L
from app.services.datasources import openmeteo, openweather, worldbank

PLAN = {"depot": {"lat": -1.2921, "lon": 36.8219}, "mode": "delivery",
        "stops": [{"id": "a", "lat": -1.30, "lon": 36.85, "load_kg": 100},
                  {"id": "b", "lat": -1.25, "lon": 36.80, "load_kg": 150}],
        "vehicles": [{"id": "v1", "capacity_kg": 400}]}


# ---------------- forecast context: mocked provider failures ----------------
def test_context_mocked_worldbank_unreachable_degrades(client, monkeypatch):
    """[MOCKED] World Bank raising httpx.HTTPError -> macro unavailable,
    but the endpoint still returns 200 with the shape intact."""
    def _boom(*args, **kwargs):
        raise httpx.ConnectError("mocked: world bank down", request=None)

    monkeypatch.setattr(worldbank, "stability_summary", _boom)
    # Weather is keyless Open-Meteo now (no key to be missing): mock the
    # adapter down so this test never touches the live network.
    monkeypatch.setattr(openmeteo, "fetch_daily_outlook", lambda *a, **k: None)
    r = client.get("/api/v1/forecast/context/dhaka")
    assert r.status_code == 200
    body = r.json()
    assert body["hub"] == "dhaka"
    assert body["macro"]["available"] is False
    assert "unreachable" in body["macro"]["note"].lower()
    assert body["weather"]["available"] is False


def test_context_mocked_openmeteo_failure_degrades(client, monkeypatch):
    """[MOCKED] Open-Meteo returning None (API down) -> weather
    unavailable, never invented values."""
    monkeypatch.setattr(openmeteo, "fetch_daily_outlook",
                        lambda *a, **k: None)
    monkeypatch.setattr(worldbank, "stability_summary",
                        lambda *a, **k: {"iso3": "BGD", "available": True})
    r = client.get("/api/v1/forecast/context/dhaka")
    assert r.status_code == 200
    assert r.json()["weather"]["available"] is False
    assert "open-meteo" in r.json()["weather"]["note"].lower()
    assert r.json()["macro"]["available"] is True


def test_context_mocked_openmeteo_success_returns_weather(client, monkeypatch):
    """[MOCKED] Open-Meteo returning a daily outlook -> the endpoint
    returns the list verbatim (same shape the old OpenWeather adapter
    returned)."""
    outlook = [{"date": "2026-11-17", "temp_min_c": 21.7, "temp_max_c": 29.8,
                "rain_mm": 0.0, "rain_probability": 0.0},
               {"date": "2026-11-18", "temp_min_c": 19.2, "temp_max_c": 29.0,
                "rain_mm": 0.1, "rain_probability": 0.01}]
    monkeypatch.setattr(openmeteo, "fetch_daily_outlook",
                        lambda *a, **k: outlook)
    monkeypatch.setattr(worldbank, "stability_summary",
                        lambda *a, **k: {"iso3": "BGD", "available": True})
    r = client.get("/api/v1/forecast/context/dhaka")
    assert r.status_code == 200
    assert r.json()["weather"] == outlook


def test_context_unknown_hub_404(client):
    assert client.get("/api/v1/forecast/context/nowhere").status_code == 404


def test_fetch_daily_outlook_mocked_http_error_returns_none(monkeypatch):
    """[MOCKED] httpx failure inside fetch_daily_outlook -> None, not a raise."""

    class _FailingClient:
        def get(self, *args, **kwargs):
            raise httpx.ConnectError("mocked: network down", request=None)

        def close(self):
            pass

    assert openweather.fetch_daily_outlook(23.8, 90.4, "fake-key",
                                           client=_FailingClient()) is None


def test_fetch_daily_outlook_no_key_returns_none():
    assert openweather.fetch_daily_outlook(23.8, 90.4, "") is None
    assert openweather.fetch_daily_outlook(23.8, 90.4, None) is None


# ---------------- logistics: mocked Open-Meteo weather ----------------
RAINY_OUTLOOK = [{"date": "2026-11-17", "temp_min_c": 21.7, "temp_max_c": 29.8,
                  "rain_mm": 25.0, "rain_probability": 0.9}]


def test_plan_mocked_openmeteo_heavy_rain_derates_speeds(client, monkeypatch):
    """[MOCKED] Open-Meteo reporting heavy rain for the hub -> the plan
    derates speeds 25% and says so in the notes (same behaviour as the
    old OpenWeather path)."""
    monkeypatch.setattr(openmeteo, "fetch_daily_outlook",
                        lambda *a, **k: RAINY_OUTLOOK)
    h = register(client, "b@x.t", "buyer")
    r = client.post("/api/v1/logistics/plan", headers=h,
                    json={**PLAN, "hub_id": "dhaka"})
    assert r.status_code == 200, r.text
    assert any("derated 25%" in n for n in r.json()["notes"])


def test_plan_mocked_openmeteo_unreachable_no_derating_no_500(client, monkeypatch):
    """[MOCKED] Open-Meteo down -> the plan still succeeds at full speed
    with an explicit 'weather unavailable' note, never a 500."""
    monkeypatch.setattr(openmeteo, "fetch_daily_outlook",
                        lambda *a, **k: None)
    h = register(client, "b@x.t", "buyer")
    r = client.post("/api/v1/logistics/plan", headers=h,
                    json={**PLAN, "hub_id": "dhaka"})
    assert r.status_code == 200, r.text
    assert any("weather unavailable" in n for n in r.json()["notes"])


def test_optimize_mocked_openmeteo_unreachable_no_derating_no_500(client, monkeypatch):
    """[MOCKED] Same graceful degradation on the OR-Tools path."""
    pytest.importorskip("ortools")
    monkeypatch.setattr(openmeteo, "fetch_daily_outlook",
                        lambda *a, **k: None)
    h = register(client, "b@x.t", "buyer")
    r = client.post("/api/v1/logistics/optimize", headers=h,
                    json={**PLAN, "hub_id": "dhaka"})
    assert r.status_code == 200, r.text
    assert any("weather unavailable" in n for n in r.json()["notes"])


# ---------------- advisor: mocked Open-Meteo weather ----------------
def test_advisor_mocked_openmeteo_rain_reaches_context(client, monkeypatch):
    """[MOCKED] Open-Meteo reporting heavy rain for the hub -> the
    advisor's template advice carries the rain risk (weather context
    flows through, same as the old OpenWeather path)."""
    monkeypatch.setattr(openmeteo, "fetch_daily_outlook",
                        lambda *a, **k: RAINY_OUTLOOK)
    h = register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/advisor/advice", headers=h,
                    json={"crop": "tomato", "language": "sw",
                          "report": "", "hub_id": "dhaka"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "template"
    assert any("Mvua" in risk for risk in body["risks"])


def test_advisor_mocked_openmeteo_unreachable_degrades_no_500(client, monkeypatch):
    """[MOCKED] Open-Meteo down -> advice still returns 200 in template
    mode, without weather context, never a 500."""
    monkeypatch.setattr(openmeteo, "fetch_daily_outlook",
                        lambda *a, **k: None)
    h = register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/advisor/advice", headers=h,
                    json={"crop": "tomato", "language": "en",
                          "report": "", "hub_id": "dhaka"})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "template"


# ---------------- logistics: mocked OSRM failures ----------------
def test_plan_mocked_osrm_failure_returns_502(client, monkeypatch):
    """[MOCKED] OSRM configured but its matrix call fails -> 502, not a
    silent haversine substitution on /plan."""
    monkeypatch.setenv("OSRM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(L.OSRMProvider, "matrix",
                        lambda self, pts: (_ for _ in ()).throw(
                            httpx.ConnectError("mocked: osrm down",
                                               request=None)))
    h = register(client, "b@x.t", "buyer")
    r = client.post("/api/v1/logistics/plan", headers=h,
                    json={**PLAN, "road_provider": "osrm"})
    assert r.status_code == 502
    assert "provider failed" in r.json()["detail"].lower()


def test_optimize_mocked_osrm_failure_falls_back_to_haversine(client, monkeypatch):
    """[MOCKED] /optimize documents a haversine fallback when OSRM fails:
    the response must say so (distance_basis + note), not pretend the
    distances are road distances."""
    pytest.importorskip("ortools")
    monkeypatch.setenv("OSRM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(L.OSRMProvider, "matrix",
                        lambda self, pts: (_ for _ in ()).throw(
                            httpx.ConnectError("mocked: osrm down",
                                               request=None)))
    h = register(client, "b@x.t", "buyer")
    r = client.post("/api/v1/logistics/optimize", headers=h,
                    json={**PLAN, "road_provider": "osrm"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["distance_basis"] == "haversine_estimate"
    assert any("OSRM failed" in n for n in body["notes"])
    # /optimize returns stops as plain id strings (unlike /plan's dicts).
    assert sorted(s for rt in body["routes"]
                  for s in rt["stops"]) == ["a", "b"]


def test_plan_and_optimize_unknown_hub_404(client):
    h = register(client, "b@x.t", "buyer")
    assert client.post("/api/v1/logistics/plan", headers=h,
                       json={**PLAN, "hub_id": "nowhere"}).status_code == 404
    assert client.post("/api/v1/logistics/optimize", headers=h,
                       json={**PLAN, "hub_id": "nowhere"}).status_code == 404


def test_plan_validation_boundaries(client):
    h = register(client, "b@x.t", "buyer")
    # Latitude out of range.
    bad = {**PLAN, "depot": {"lat": 91, "lon": 0}}
    assert client.post("/api/v1/logistics/plan", headers=h,
                       json=bad).status_code == 422
    # Too many stops (max 60).
    many = {**PLAN, "stops": [{"id": f"s{i}", "lat": -1.3, "lon": 36.8,
                               "load_kg": 1} for i in range(61)]}
    assert client.post("/api/v1/logistics/plan", headers=h,
                       json=many).status_code == 422
    # Bad mode.
    assert client.post("/api/v1/logistics/plan", headers=h,
                       json={**PLAN, "mode": "teleport"}).status_code == 422
    # No vehicles.
    assert client.post("/api/v1/logistics/plan", headers=h,
                       json={**PLAN, "vehicles": []}).status_code == 422


# ---------------- database failure on a normal endpoint ----------------
def test_db_failure_on_products_is_generic_500(client, monkeypatch):
    """[MOCKED] A dependency that raises (simulating a dead DB) must hit
    the global handler: 500 with the generic detail, no internals leaked."""

    def _dead_db():
        raise RuntimeError("mocked: database connection refused")

    app_obj.dependency_overrides[get_db] = _dead_db
    try:
        quiet = TestClient(app_obj, raise_server_exceptions=False)
        r = quiet.get("/api/v1/products")
    finally:
        app_obj.dependency_overrides.pop(get_db, None)
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error"}
    assert "refused" not in r.text
