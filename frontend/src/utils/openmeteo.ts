// Direct Open-Meteo fetch from the visitor's browser.
//
// Why this exists: the backend calls Open-Meteo from the server's IP.
// On shared cloud hosts (e.g. Render free) that IP is shared with many
// other services, and Open-Meteo's free limits are counted per IP — so
// the server call can answer 429 even though the API itself is healthy
// (seen live on Render 2026-11-18: /api/v1/weather/dhaka returned
// available:false while the identical request from another network
// returned 200). A browser call comes from the visitor's own IP, so it
// is not affected by the server's shared-IP limit. Open-Meteo sends
// Access-Control-Allow-Origin: *, so a direct browser fetch works with
// no key and no proxy.
//
// This is a FALLBACK, not the primary path: the Weather page tries the
// backend first (10-minute server cache, one shared request per hub)
// and only calls this when the backend reports unavailable. The
// request, the parsing and the returned WeatherResponse shape mirror
// backend/app/services/datasources/openmeteo.py exactly, so the page
// renders either source identically; `direct: true` marks the payload
// so the UI can say where the data came from. Returns null on ANY
// failure — the caller keeps the backend's labelled "unavailable"
// state, never invented values.

import type { WeatherCurrent, WeatherDay, WeatherResponse } from "../services/api";

export const OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast";
export const DIRECT_TIMEOUT_MS = 15_000;

// WMO weather codes grouped into the same condition slugs the backend
// uses (backend/app/services/datasources/openmeteo.py).
const WMO_CONDITIONS: Record<number, string> = {
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
};

export function conditionForCode(code: number | null | undefined): string {
  if (code == null) return "unknown";
  return WMO_CONDITIONS[code] ?? "unknown";
}

/** Round a numeric API value, preserving null for missing data. */
function round(value: unknown, digits = 1): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  const rounded = Number(n.toFixed(digits));
  return digits === 0 ? Math.round(rounded) : rounded;
}

export interface DirectHub {
  id: string;
  name: string;
  lat: number;
  lon: number;
}

interface OpenMeteoPayload {
  timezone?: string;
  current?: Record<string, unknown>;
  daily?: {
    time?: string[];
    temperature_2m_max?: unknown[];
    temperature_2m_min?: unknown[];
    precipitation_sum?: unknown[];
    precipitation_probability_max?: unknown[];
    weather_code?: unknown[];
  };
}

function dailyRows(daily: NonNullable<OpenMeteoPayload["daily"]>): WeatherDay[] {
  const dates = Array.isArray(daily.time) ? daily.time : [];
  const col = (name: keyof NonNullable<OpenMeteoPayload["daily"]>): unknown[] => {
    const values = daily[name];
    return Array.isArray(values) ? values : [];
  };
  const tempMax = col("temperature_2m_max");
  const tempMin = col("temperature_2m_min");
  const rain = col("precipitation_sum");
  const codes = col("weather_code");
  const prob = col("precipitation_probability_max");
  const at = (values: unknown[], i: number): unknown => (i < values.length ? values[i] : null);
  return dates.map((date, i) => {
    const codeRaw = at(codes, i);
    const code = typeof codeRaw === "number" ? codeRaw : null;
    return {
      date,
      temp_max_c: round(at(tempMax, i)),
      temp_min_c: round(at(tempMin, i)),
      rain_mm: round(at(rain, i)),
      rain_probability_pct: round(at(prob, i), 0),
      weather_code: code,
      condition: conditionForCode(code),
    };
  });
}

/**
 * Turn a raw Open-Meteo forecast payload into the WeatherResponse the
 * Weather page renders. Pure function, exported for tests.
 *
 * "Today" comes from the API's own `current.time` (hub-local clock),
 * falling back to the browser's local date — the past/forecast split
 * must follow the hub's day, not the server's UTC day.
 */
export function transformOpenMeteo(
  payload: OpenMeteoPayload,
  hub: DirectHub,
  todayIso?: string,
): WeatherResponse {
  const current = payload.current ?? {};
  const today =
    todayIso ?? (typeof current.time === "string" ? current.time.slice(0, 10) : null) ?? new Date().toISOString().slice(0, 10);
  const rows = dailyRows(payload.daily ?? {});
  const past: WeatherDay[] = [];
  const forecast: WeatherDay[] = [];
  for (const row of rows) {
    if (row.date < today) {
      // Rain probability is meaningless for days already past.
      const { rain_probability_pct: _dropped, ...pastRow } = row;
      past.push(pastRow);
    } else {
      forecast.push(row);
    }
  }
  const notes: string[] = [];
  if (past.length === 0) notes.push("past_unavailable");

  const codeRaw = current.weather_code;
  const code = typeof codeRaw === "number" ? codeRaw : null;
  const currentOut: WeatherCurrent = {
    time: typeof current.time === "string" ? current.time : null,
    temperature_c: round(current.temperature_2m),
    humidity_pct: round(current.relative_humidity_2m, 0),
    precipitation_mm: round(current.precipitation),
    wind_speed_kmh: round(current.wind_speed_10m),
    weather_code: code,
    condition: conditionForCode(code),
  };
  return {
    hub: hub.id,
    hub_name: hub.name,
    available: true,
    source: "open-meteo",
    fetched_at: new Date().toISOString(),
    timezone: payload.timezone ?? null,
    current: currentOut,
    past,
    forecast,
    notes,
    direct: true,
  };
}

/**
 * Fetch past 7 days + current + next 7 days for one hub, directly from
 * the visitor's browser. Same single Forecast API call the backend
 * makes (past_days=7, forecast_days=8). Returns null on any failure.
 */
export async function fetchDirectWeather(hub: DirectHub): Promise<WeatherResponse | null> {
  const params = new URLSearchParams({
    latitude: String(hub.lat),
    longitude: String(hub.lon),
    current: "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
    daily:
      "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code",
    past_days: "7",
    forecast_days: "8",
    timezone: "auto",
  });
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DIRECT_TIMEOUT_MS);
  try {
    const res = await fetch(`${OPEN_METEO_FORECAST_URL}?${params}`, { signal: controller.signal });
    if (!res.ok) return null;
    const payload = (await res.json()) as OpenMeteoPayload;
    if (!payload || typeof payload !== "object") return null;
    return transformOpenMeteo(payload, hub);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
