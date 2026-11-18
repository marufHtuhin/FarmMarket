"""Open-Meteo weather service + endpoint tests (mocked httpx).

No live network is used here: the fake client returns a canned payload shaped
like the real Open-Meteo forecast response with past_days=7 (verified live
for Dhaka on 2026-11-17). The live smoke check is a separate manual step.
"""
from datetime import date

import httpx
import pytest

from app.routers import weather as weather_router
from app.services.datasources import openmeteo

TODAY = date(2026, 11, 17)

# One forecast payload covering past 7 days + today + next 7 days (15 days),
# exactly as the Forecast API returns it with past_days=7&forecast_days=8.
FORECAST_PAYLOAD = {
    "timezone": "Asia/Dhaka",
    "current": {
        "time": "2026-11-17T11:15",
        "temperature_2m": 28.9,
        "relative_humidity_2m": 51,
        "precipitation": 0.0,
        "weather_code": 0,
        "wind_speed_10m": 6.0,
    },
    "daily": {
        "time": ["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13",
                 "2026-11-14", "2026-11-15", "2026-11-16",
                 "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20",
                 "2026-11-21", "2026-11-22", "2026-11-23", "2026-11-24"],
        "temperature_2m_max": [31.2, 31.4, 30.5, 30.3, 29.7, 29.6, 29.4,
                               29.8, 29.0, 28.2, 24.9, 28.1, 27.5, 24.8, 27.7],
        "temperature_2m_min": [22.7, 22.0, 22.3, 21.9, 21.1, 21.4, 21.9,
                               21.7, 19.2, 19.7, 21.9, 22.3, 21.3, 22.0, 20.3],
        "precipitation_sum": [1.1, 1.1, 0.0, 0.0, 0.0, 0.0, 0.0,
                              0.0, 0.0, 0.1, 16.4, 0.6, 0.0, 17.4, 0.0],
        "precipitation_probability_max": [None, None, None, None, None, None, None,
                                          0, 1, 41, 37, 31, 22, 24, 8],
        "weather_code": [53, 51, 0, 0, 0, 3, 3,
                         3, 3, 51, 81, 51, 3, 80, 45],
    },
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """httpx.Client stand-in; records (url, params) of every call."""

    def __init__(self, payload=FORECAST_PAYLOAD, error=None):
        self.payload = payload
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        if self.error is not None:
            raise self.error
        return _FakeResponse(self.payload)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _fresh_cache():
    weather_router.clear_weather_cache()
    yield
    weather_router.clear_weather_cache()


# --- Service ---------------------------------------------------------------

def test_fetch_weather_parses_past_and_forecast_from_one_call():
    client = _FakeClient()
    data = openmeteo.fetch_weather(23.8103, 90.4125, client=client, today=TODAY)
    assert data is not None
    assert data["source"] == "open-meteo"
    assert data["fetched_at"]  # every value carries source + timestamp
    assert data["timezone"] == "Asia/Dhaka"
    assert data["notes"] == []
    assert data["current"] == {
        "time": "2026-11-17T11:15", "temperature_c": 28.9, "humidity_pct": 51,
        "precipitation_mm": 0.0, "wind_speed_kmh": 6.0,
        "weather_code": 0, "condition": "clear",
    }
    assert len(data["past"]) == 7
    assert data["past"][0] == {"date": "2026-11-10", "temp_max_c": 31.2,
                               "temp_min_c": 22.7, "rain_mm": 1.1,
                               "weather_code": 53, "condition": "drizzle"}
    assert data["past"][-1]["date"] == "2026-11-16"  # yesterday, not today
    assert "rain_probability_pct" not in data["past"][0]  # meaningless for past
    assert len(data["forecast"]) == 8
    assert data["forecast"][0]["date"] == "2026-11-17"  # today + 7 days
    assert data["forecast"][3] == {"date": "2026-11-20", "temp_max_c": 24.9,
                                   "temp_min_c": 21.9, "rain_mm": 16.4,
                                   "weather_code": 81, "condition": "rain",
                                   "rain_probability_pct": 37}
    # Exactly ONE call, to the Forecast API (not the Archive API), asking
    # for the past window in the same request.
    assert len(client.calls) == 1
    url, params = client.calls[0]
    assert "api.open-meteo.com" in url
    assert "archive-api" not in url
    assert params["past_days"] == 7
    assert params["forecast_days"] == 8


def test_fetch_weather_returns_none_when_api_unreachable():
    err = httpx.ConnectError("boom", request=httpx.Request("GET", "https://x"))
    data = openmeteo.fetch_weather(23.8103, 90.4125,
                                   client=_FakeClient(error=err), today=TODAY)
    assert data is None


def test_fetch_weather_empty_past_is_labelled_not_invented():
    no_past = {"timezone": "Asia/Dhaka",
               "current": FORECAST_PAYLOAD["current"],
               "daily": {"time": FORECAST_PAYLOAD["daily"]["time"][7:],
                         "temperature_2m_max": FORECAST_PAYLOAD["daily"]["temperature_2m_max"][7:],
                         "temperature_2m_min": FORECAST_PAYLOAD["daily"]["temperature_2m_min"][7:],
                         "precipitation_sum": FORECAST_PAYLOAD["daily"]["precipitation_sum"][7:],
                         "precipitation_probability_max": FORECAST_PAYLOAD["daily"]["precipitation_probability_max"][7:],
                         "weather_code": FORECAST_PAYLOAD["daily"]["weather_code"][7:]}}
    data = openmeteo.fetch_weather(23.8103, 90.4125,
                                   client=_FakeClient(payload=no_past), today=TODAY)
    assert data is not None
    assert data["past"] == []  # missing past is labelled, never invented
    assert data["notes"] == ["past_unavailable"]
    assert data["current"]["temperature_c"] == 28.9
    assert len(data["forecast"]) == 8


def test_fetch_weather_missing_fields_become_none_not_zero():
    sparse = {"timezone": "Asia/Dhaka", "current": {"time": "2026-11-17T11:15"},
              "daily": {"time": ["2026-11-17"], "temperature_2m_max": [29.8]}}
    data = openmeteo.fetch_weather(23.8103, 90.4125,
                                   client=_FakeClient(payload=sparse),
                                   today=TODAY)
    assert data["current"]["temperature_c"] is None
    assert data["current"]["condition"] == "unknown"
    assert data["forecast"][0]["temp_min_c"] is None
    assert data["forecast"][0]["rain_mm"] is None
    assert data["forecast"][0]["rain_probability_pct"] is None


def test_condition_for_code_covers_wmo_groups():
    assert openmeteo.condition_for_code(0) == "clear"
    assert openmeteo.condition_for_code(2) == "partly_cloudy"
    assert openmeteo.condition_for_code(45) == "fog"
    assert openmeteo.condition_for_code(95) == "thunderstorm"
    assert openmeteo.condition_for_code(71) == "snow"
    assert openmeteo.condition_for_code(None) == "unknown"
    assert openmeteo.condition_for_code(999) == "unknown"


# --- fetch_daily_outlook adapter (keyless Open-Meteo replacement for the
# retired OpenWeather adapter; same return shape, no API key) ------------
def test_fetch_daily_outlook_shape_today_plus_seven():
    """Exact OpenWeather shape — {date, temp_min_c, temp_max_c, rain_mm,
    rain_probability} — for today + the next 7 days, from the 15-day
    fixture payload (past rows are dropped, not returned)."""
    client = _FakeClient()
    out = openmeteo.fetch_daily_outlook(23.8103, 90.4125, client=client,
                                        today=TODAY)
    assert out is not None
    assert len(out) == 8
    assert out[0] == {"date": "2026-11-17", "temp_min_c": 21.7,
                      "temp_max_c": 29.8, "rain_mm": 0.0,
                      "rain_probability": 0.0}
    assert out[3] == {"date": "2026-11-20", "temp_min_c": 21.9,
                      "temp_max_c": 24.9, "rain_mm": 16.4,
                      "rain_probability": 0.37}  # 37% -> 0.37
    assert out[-1]["date"] == "2026-11-24"
    # One Forecast API call, no past_days requested, 8 forecast days.
    assert len(client.calls) == 1
    url, params = client.calls[0]
    assert "api.open-meteo.com" in url
    assert "past_days" not in params
    assert params["forecast_days"] == 8
    assert "precipitation_probability_max" in params["daily"]


def test_fetch_daily_outlook_returns_none_when_api_unreachable():
    err = httpx.ConnectError("boom", request=httpx.Request("GET", "https://x"))
    assert openmeteo.fetch_daily_outlook(
        23.8103, 90.4125, client=_FakeClient(error=err), today=TODAY) is None


def test_fetch_daily_outlook_malformed_body_degrades_to_none_or_empty():
    # Non-object JSON: None (unusable response).
    assert openmeteo.fetch_daily_outlook(
        23.8103, 90.4125, client=_FakeClient(payload=["not", "a", "dict"]),
        today=TODAY) is None
    # Well-formed but no daily rows: [] (callers treat falsy as unavailable).
    assert openmeteo.fetch_daily_outlook(
        23.8103, 90.4125, client=_FakeClient(payload={}), today=TODAY) == []
    assert openmeteo.fetch_daily_outlook(
        23.8103, 90.4125, client=_FakeClient(payload={"daily": {}}),
        today=TODAY) == []


def test_fetch_daily_outlook_missing_values_degrade_not_500():
    """A missing rain value becomes 0.0 (no derating); missing temps stay
    None — the adapter never raises on a sparse response."""
    sparse = {"daily": {"time": ["2026-11-17"],
                        "temperature_2m_max": [29.8]}}
    out = openmeteo.fetch_daily_outlook(
        23.8103, 90.4125, client=_FakeClient(payload=sparse), today=TODAY)
    assert out == [{"date": "2026-11-17", "temp_min_c": None,
                    "temp_max_c": 29.8, "rain_mm": 0.0,
                    "rain_probability": 0.0}]
    # ...and the speed factor still works on that row.
    assert openmeteo.speed_factor(out)[0] == 1.0


def test_speed_factor_unchanged_after_move_to_openmeteo():
    assert openmeteo.speed_factor(None)[0] == 1.0
    assert "unavailable" in openmeteo.speed_factor(None)[1]
    assert openmeteo.speed_factor([{"rain_mm": 25}])[0] == 0.75
    assert openmeteo.speed_factor([{"rain_mm": 3}])[0] == 0.9
    assert openmeteo.speed_factor([{"rain_mm": 0.5}])[0] == 1.0


# --- Endpoint --------------------------------------------------------------

def _patch_fetch(monkeypatch, client):
    """Route the endpoint through a fake httpx client."""
    monkeypatch.setattr(openmeteo.httpx, "Client", lambda *a, **k: client)


def test_endpoint_success_shape(client, monkeypatch):
    fake = _FakeClient()
    _patch_fetch(monkeypatch, fake)
    r = client.get("/api/v1/weather/dhaka")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hub"] == "dhaka"
    assert body["hub_name"] == "Dhaka"
    assert body["available"] is True
    assert body["source"] == "open-meteo"
    assert body["fetched_at"]
    assert body["current"]["temperature_c"] == 28.9
    assert len(body["past"]) == 7
    assert len(body["forecast"]) == 8


def test_endpoint_unknown_hub_404(client):
    r = client.get("/api/v1/weather/nowhere")
    assert r.status_code == 404


def test_endpoint_unreachable_degrades_with_label(client, monkeypatch):
    err = httpx.ConnectError("boom", request=httpx.Request("GET", "https://x"))
    _patch_fetch(monkeypatch, _FakeClient(error=err))
    r = client.get("/api/v1/weather/dhaka")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is False
    assert body["note"]  # labelled unavailable state, no invented values
    assert body["source"] == "open-meteo"
    assert "current" not in body
    assert "forecast" not in body


def test_endpoint_caches_for_ten_minutes(client, monkeypatch):
    fake = _FakeClient()
    _patch_fetch(monkeypatch, fake)
    assert client.get("/api/v1/weather/dhaka").status_code == 200
    assert client.get("/api/v1/weather/dhaka").status_code == 200
    assert len(fake.calls) == 1  # one forecast call, then cached
    # A different hub is a separate cache entry.
    assert client.get("/api/v1/weather/sylhet").status_code == 200
    assert len(fake.calls) == 2


def test_endpoint_refetches_after_cache_expiry(client, monkeypatch):
    fake = _FakeClient()
    _patch_fetch(monkeypatch, fake)
    assert client.get("/api/v1/weather/dhaka").status_code == 200
    assert len(fake.calls) == 1
    # Age the cache entry past the TTL.
    ts, payload = weather_router._cache["dhaka"]
    weather_router._cache["dhaka"] = (ts - weather_router.CACHE_TTL_S - 1, payload)
    assert client.get("/api/v1/weather/dhaka").status_code == 200
    assert len(fake.calls) == 2


def test_endpoint_does_not_cache_unavailable(client, monkeypatch):
    err = httpx.ConnectError("boom", request=httpx.Request("GET", "https://x"))
    fake = _FakeClient(error=err)
    _patch_fetch(monkeypatch, fake)
    assert client.get("/api/v1/weather/dhaka").json()["available"] is False
    # Service recovers: the next request must see live data, not a stale
    # cached "unavailable".
    fake.error = None
    body = client.get("/api/v1/weather/dhaka").json()
    assert body["available"] is True
    assert body["current"]["temperature_c"] == 28.9
