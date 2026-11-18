"""OpenWeatherMap 5-day / 3-hour forecast (free tier) summarised per day.

LEGACY — retired 2026-11-17. No router uses this module any more: the
logistics derating, forecast context and advisor weather all use the
keyless Open-Meteo adapter (openmeteo.fetch_daily_outlook, same return
shape), so OPENWEATHER_API_KEY is IGNORED by the app now — an old .env
line does nothing and never breaks anything. This module is kept only
so existing imports and its own unit tests keep working; do not add new
callers. Historical weather needs OpenWeather's paid history/timemachine
products, which were never wired in here. Without an API key this module
returns None - callers must treat weather as "unknown", never as "clear".
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
import httpx

# speed_factor moved to openmeteo (the only weather source routers use
# now); re-exported here so existing imports keep working.
from .openmeteo import speed_factor  # noqa: F401

URL = "https://api.openweathermap.org/data/2.5/forecast"


def fetch_daily_outlook(lat: float, lon: float, api_key: str,
                        client: httpx.Client | None = None) -> list[dict] | None:
    if not api_key:
        return None
    own = client is None
    client = client or httpx.Client(timeout=20)
    try:
        r = client.get(URL, params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"})
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError:
        return None
    except ValueError:  # invalid JSON body
        return None
    finally:
        if own:
            client.close()
    # A 200 with a malformed body (missing "list"/"dt"/"main") must degrade to
    # "weather unknown", not raise: callers in /forecast/context and
    # /logistics/* call this outside their try blocks, so a KeyError here
    # used to become a 500. Malformed items are skipped; an empty result
    # still returns [] (callers treat falsy as unavailable).
    days: dict[str, dict] = defaultdict(lambda: {"temps": [], "rain_mm": 0.0, "pop": 0.0})
    items = data.get("list") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    for item in items:
        try:
            day = datetime.fromtimestamp(item["dt"], tz=timezone.utc).date().isoformat()
            temp = float(item["main"]["temp"])
            rain = float((item.get("rain") or {}).get("3h", 0.0))
            pop = float(item.get("pop", 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        d = days[day]
        d["temps"].append(temp)
        d["rain_mm"] += rain
        d["pop"] = max(d["pop"], pop)
    return [{"date": k, "temp_min_c": round(min(v["temps"]), 1), "temp_max_c": round(max(v["temps"]), 1),
             "rain_mm": round(v["rain_mm"], 1), "rain_probability": round(v["pop"], 2)}
            for k, v in sorted(days.items())]
