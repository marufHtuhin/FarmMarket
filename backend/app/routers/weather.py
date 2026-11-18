"""Public hub weather from Open-Meteo (past 7 days + current + next 7 days).

No API key is needed. Responses are cached in memory for 10 minutes per hub.
When Open-Meteo is unreachable the endpoint still returns 200 with
``available: false`` and a note — the UI must show that labelled
unavailable state, never invented weather values.
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..config import get_hub
from ..services.datasources import openmeteo

router = APIRouter(prefix="/api/v1/weather", tags=["weather"])

CACHE_TTL_S = 600  # 10 minutes
_cache: dict[str, tuple[float, dict]] = {}


def clear_weather_cache() -> None:
    """Drop all cached weather (used by tests)."""
    _cache.clear()


@router.get("/{hub}")
def weather(hub: str):
    h = get_hub(hub.strip().lower())
    if h is None:
        raise HTTPException(404, f"Unknown hub '{hub}'")
    now = time.time()
    hit = _cache.get(h.id)
    if hit and now - hit[0] < CACHE_TTL_S:
        return hit[1]
    data = openmeteo.fetch_weather(h.lat, h.lon)
    if data is None:
        # Deliberately NOT cached: a transient outage should recover on the
        # next request instead of serving "unavailable" for 10 minutes.
        return {
            "hub": h.id,
            "hub_name": h.name,
            "available": False,
            "note": "Open-Meteo weather service is unreachable right now; "
                    "no weather data is available.",
            "source": openmeteo.SOURCE,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    payload = {"hub": h.id, "hub_name": h.name, "available": True, **data}
    _cache[h.id] = (now, payload)
    return payload
