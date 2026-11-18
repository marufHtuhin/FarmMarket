"""Open-Meteo weather (past 7 days + current + next 7 days) per hub.

Free, no API key required. A SINGLE Forecast API call with ``past_days=7``
returns the past 7 days, today, and the next 7 days in one response — the
Archive API is deliberately NOT used: it is ERA5 reanalysis with a ~2-day
delay, while the Forecast API's past days are available immediately.

Returns None when the Forecast API is unreachable — callers must surface
the "unavailable" state, never substitute invented values. Every value in
the returned payload carries its source ("open-meteo") and fetch timestamp.

fetch_daily_outlook() is the keyless replacement for the retired
OpenWeather adapter (datasources/openweather.py, legacy since 2026-11-17):
same return shape, so the logistics derating, forecast context and
advisor weather all work with ZERO API keys.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "open-meteo"
TIMEOUT_S = 15
PAST_DAYS = 7
FORECAST_DAYS = 8  # today + next 7 days

# WMO weather codes (https://open-meteo.com/en/docs#weathervariables) grouped
# into plain-language condition slugs used by the UI.
_WMO_CONDITIONS: dict[int, str] = {
    0: "clear",
    1: "partly_cloudy",
    2: "partly_cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "drizzle",
    57: "drizzle",
    61: "rain",
    63: "rain",
    65: "rain",
    66: "rain",
    67: "rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "rain",
    81: "rain",
    82: "rain",
    85: "snow",
    86: "snow",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}


def condition_for_code(code: int | None) -> str:
    """Map a WMO weather code to a condition slug, or "unknown"."""
    if code is None:
        return "unknown"
    return _WMO_CONDITIONS.get(int(code), "unknown")


def _round(value, digits: int = 1):
    """Round a numeric API value, preserving None for missing data."""
    if value is None:
        return None
    try:
        rounded = round(float(value), digits)
    except (TypeError, ValueError):
        return None
    return int(rounded) if digits == 0 else rounded


def _daily_rows(data: dict, include_probability: bool) -> list[dict]:
    """Parse Open-Meteo's parallel daily arrays into per-day dicts.

    Arrays may be shorter than the date list (or a variable absent) when the
    API has no value for a day — those fields become None, never 0 or a
    guessed value.
    """
    daily = data.get("daily") or {}
    dates = daily.get("time") or []

    def col(name: str) -> list:
        values = daily.get(name)
        return values if isinstance(values, list) else []

    temp_max = col("temperature_2m_max")
    temp_min = col("temperature_2m_min")
    rain = col("precipitation_sum")
    codes = col("weather_code")
    prob = col("precipitation_probability_max")

    def at(values: list, i: int):
        return values[i] if i < len(values) else None

    rows = []
    for i, day in enumerate(dates):
        code = at(codes, i)
        row = {
            "date": day,
            "temp_max_c": _round(at(temp_max, i)),
            "temp_min_c": _round(at(temp_min, i)),
            "rain_mm": _round(at(rain, i)),
            "weather_code": code,
            "condition": condition_for_code(code),
        }
        if include_probability:
            row["rain_probability_pct"] = _round(at(prob, i), 0)
        rows.append(row)
    return rows


def _get_json(client: httpx.Client, url: str, params: dict) -> dict:
    r = client.get(url, params=params)
    r.raise_for_status()
    return r.json()  # may raise ValueError on a non-JSON body; caller handles it


def fetch_weather(lat: float, lon: float, client: httpx.Client | None = None,
                  today: date | None = None) -> dict | None:
    """Fetch past + current + forecast weather for one hub.

    One Forecast API call with ``past_days=7`` covers all three windows.
    Returns None when the API is unreachable. If the response contains no
    past days at all, ``past`` is an empty list and a ``past_unavailable``
    note is recorded — the missing past is labelled, never filled in. A
    short (but non-empty) past is shown as-is; every row carries its date,
    so no false impression of completeness is created.
    """
    today = today or date.today()
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        try:
            forecast = _get_json(client, FORECAST_URL, {
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                         "precipitation_probability_max,weather_code",
                "past_days": PAST_DAYS,
                "forecast_days": FORECAST_DAYS,
                "timezone": "auto",
            })
        except httpx.HTTPError:
            return None
        except ValueError:  # non-JSON body: same "unavailable" outcome, never a 500
            return None
    finally:
        if own:
            client.close()

    today_iso = today.isoformat()
    rows = _daily_rows(forecast, include_probability=True)
    past: list[dict] = []
    future: list[dict] = []
    for row in rows:
        if row["date"] < today_iso:
            # Rain probability is meaningless for days already past.
            row.pop("rain_probability_pct", None)
            past.append(row)
        else:
            future.append(row)
    notes: list[str] = []
    if not past:
        notes.append("past_unavailable")

    current = forecast.get("current") or {}
    code = current.get("weather_code")
    return {
        "source": SOURCE,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "timezone": forecast.get("timezone"),
        "current": {
            "time": current.get("time"),
            "temperature_c": _round(current.get("temperature_2m")),
            "humidity_pct": _round(current.get("relative_humidity_2m"), 0),
            "precipitation_mm": _round(current.get("precipitation")),
            "wind_speed_kmh": _round(current.get("wind_speed_10m")),
            "weather_code": code,
            "condition": condition_for_code(code),
        },
        "past": past,
        "forecast": future,
        "notes": notes,
    }


def fetch_daily_outlook(lat: float, lon: float, client: httpx.Client | None = None,
                        today: date | None = None) -> list[dict] | None:
    """Daily outlook for today + the next 7 days, in the EXACT shape the
    retired OpenWeather adapter returned — a list of {date, temp_min_c,
    temp_max_c, rain_mm, rain_probability} — but from keyless Open-Meteo,
    so the logistics derating, forecast context and advisor weather no
    longer need OPENWEATHER_API_KEY (deprecated 2026-11-17; ignored if
    present in .env).

    rain_probability is precipitation_probability_max / 100 (0.0-1.0).
    A missing rain value becomes 0.0 (no rain data -> no derating, the
    same outcome as 'weather unknown' for the speed factor); missing
    temps stay None. Returns None when the API is unreachable, the body
    is not JSON, or the JSON is not an object; returns [] when the
    response is well-formed but has no daily rows. Callers treat any
    falsy value as 'weather unknown' and must never 500 on it.
    """
    today = today or date.today()
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        try:
            data = _get_json(client, FORECAST_URL, {
                "latitude": lat, "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                         "precipitation_probability_max",
                "forecast_days": FORECAST_DAYS,
                "timezone": "auto",
            })
        except httpx.HTTPError:
            return None
        except ValueError:  # non-JSON body: same "unavailable" outcome, never a 500
            return None
    finally:
        if own:
            client.close()
    if not isinstance(data, dict):
        return None
    today_iso = today.isoformat()
    out: list[dict] = []
    for row in _daily_rows(data, include_probability=True):
        if row["date"] < today_iso:
            continue  # the API returns today onwards; ignore any past rows
        prob = row.get("rain_probability_pct")
        out.append({
            "date": row["date"],
            "temp_min_c": row["temp_min_c"],
            "temp_max_c": row["temp_max_c"],
            "rain_mm": row["rain_mm"] if row["rain_mm"] is not None else 0.0,
            "rain_probability": round(prob / 100, 2) if prob is not None else 0.0,
        })
        if len(out) >= FORECAST_DAYS:
            break
    return out


def speed_factor(outlook: list[dict] | None, heavy_rain_mm: float = 10.0) -> tuple[float, str]:
    """Travel-speed multiplier (<1 slows trucks). Heuristic: heavy rain -> 0.75, rain -> 0.9.
    Unknown weather -> 1.0 with an explicit note. (Moved here from the
    retired openweather adapter 2026-11-17; behaviour unchanged.)"""
    if not outlook:
        return 1.0, "weather unavailable; no derating applied"
    today = outlook[0]
    if today["rain_mm"] >= heavy_rain_mm:
        return 0.75, f"heavy rain expected ({today['rain_mm']} mm); speeds derated 25%"
    if today["rain_mm"] >= 2.0:
        return 0.9, f"rain expected ({today['rain_mm']} mm); speeds derated 10%"
    return 1.0, "no significant rain expected"
