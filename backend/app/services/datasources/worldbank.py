"""World Bank Open Data (API v2) - macro indicators for market-stability context."""
from __future__ import annotations
import statistics
import httpx

BASE = "https://api.worldbank.org/v2"
# The World Bank API is slow from some networks: a population fetch measured
# ~12s and an inflation fetch ~21s (2026-11-17). A 20s timeout turned those
# into spurious ReadTimeouts, so the default is 30s.
TIMEOUT_S = 30
INDICATORS = {
    "inflation_cpi_pct": "FP.CPI.TOTL.ZG",          # Inflation, consumer prices (annual %)
    "agri_value_added_pct_gdp": "NV.AGR.TOTL.ZS",   # Agriculture, forestry, fishing, value added (% of GDP)
}


def fetch_indicator(iso3: str, indicator: str, start: int, end: int,
                    client: httpx.Client | None = None) -> list[tuple[int, float]]:
    """Return [(year, value)] with null values dropped (World Bank returns nulls often).

    Malformed entries (missing/unparseable date or value) are skipped, not
    fatal: a single bad row must not turn /forecast/context/{hub} into a 500
    (that endpoint only catches httpx.HTTPError)."""
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        r = client.get(f"{BASE}/country/{iso3}/indicator/{indicator}",
                       params={"format": "json", "per_page": 200, "date": f"{start}:{end}"})
        r.raise_for_status()
        data = r.json()
    finally:
        if own:
            client.close()
    if not isinstance(data, list) or len(data) < 2 or not data[1]:
        return []
    out: list[tuple[int, float]] = []
    for x in data[1]:
        if not isinstance(x, dict) or x.get("value") is None:
            continue
        try:
            out.append((int(x["date"]), float(x["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out)


def stability_summary(iso3: str, start: int, end: int, client: httpx.Client | None = None) -> dict:
    series = fetch_indicator(iso3, INDICATORS["inflation_cpi_pct"], start, end, client)
    if len(series) < 3:
        return {"iso3": iso3, "available": False, "note": "Not enough World Bank inflation data"}
    vals = [v for _, v in series]
    return {"iso3": iso3, "available": True, "years": [y for y, _ in series],
            "latest_inflation_pct": vals[-1], "mean_inflation_pct": round(statistics.fmean(vals), 2),
            "inflation_volatility_pct": round(statistics.pstdev(vals), 2),
            "source": "World Bank Open Data, FP.CPI.TOTL.ZG"}
