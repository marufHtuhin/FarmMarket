import { afterEach, describe, expect, it, vi } from "vitest";
import { conditionForCode, fetchDirectWeather, transformOpenMeteo } from "./openmeteo";

// Same 15-day fixture shape as backend/tests/test_weather.py (past 7 +
// today + next 7), verified live for Dhaka on 2026-11-17.
const FORECAST_PAYLOAD = {
  timezone: "Asia/Dhaka",
  current: {
    time: "2026-11-17T11:15",
    temperature_2m: 28.9,
    relative_humidity_2m: 51,
    precipitation: 0.0,
    weather_code: 0,
    wind_speed_10m: 6.0,
  },
  daily: {
    time: [
      "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13",
      "2026-11-14", "2026-11-15", "2026-11-16",
      "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20",
      "2026-11-21", "2026-11-22", "2026-11-23", "2026-11-24",
    ],
    temperature_2m_max: [31.2, 31.4, 30.5, 30.3, 29.7, 29.6, 29.4,
      29.8, 29.0, 28.2, 24.9, 28.1, 27.5, 24.8, 27.7],
    temperature_2m_min: [22.7, 22.0, 22.3, 21.9, 21.1, 21.4, 21.9,
      21.7, 19.2, 19.7, 21.9, 22.3, 21.3, 22.0, 20.3],
    precipitation_sum: [1.1, 1.1, 0.0, 0.0, 0.0, 0.0, 0.0,
      0.0, 0.0, 0.1, 16.4, 0.6, 0.0, 17.4, 0.0],
    precipitation_probability_max: [null, null, null, null, null, null, null,
      0, 1, 41, 37, 31, 22, 24, 8],
    weather_code: [53, 51, 0, 0, 0, 3, 3,
      3, 3, 51, 81, 51, 3, 80, 45],
  },
};

const DHAKA = { id: "dhaka", name: "Dhaka", lat: 23.8103, lon: 90.4125 };

describe("conditionForCode", () => {
  it("mirrors the backend WMO groups", () => {
    expect(conditionForCode(0)).toBe("clear");
    expect(conditionForCode(2)).toBe("partly_cloudy");
    expect(conditionForCode(45)).toBe("fog");
    expect(conditionForCode(95)).toBe("thunderstorm");
    expect(conditionForCode(71)).toBe("snow");
    expect(conditionForCode(53)).toBe("drizzle");
    expect(conditionForCode(81)).toBe("rain");
  });

  it("returns unknown for missing or unrecognised codes", () => {
    expect(conditionForCode(null)).toBe("unknown");
    expect(conditionForCode(undefined)).toBe("unknown");
    expect(conditionForCode(999)).toBe("unknown");
  });
});

describe("transformOpenMeteo", () => {
  it("splits past 7 + today + next 7 into the WeatherResponse shape", () => {
    const out = transformOpenMeteo(FORECAST_PAYLOAD, DHAKA, "2026-11-17");
    expect(out.available).toBe(true);
    expect(out.direct).toBe(true);
    expect(out.source).toBe("open-meteo");
    expect(out.hub).toBe("dhaka");
    expect(out.hub_name).toBe("Dhaka");
    expect(out.timezone).toBe("Asia/Dhaka");
    expect(out.fetched_at).toBeTruthy();
    expect(out.notes).toEqual([]);
    expect(out.current).toEqual({
      time: "2026-11-17T11:15",
      temperature_c: 28.9,
      humidity_pct: 51,
      precipitation_mm: 0.0,
      wind_speed_kmh: 6.0,
      weather_code: 0,
      condition: "clear",
    });
    expect(out.past).toHaveLength(7);
    expect(out.past![0]).toEqual({
      date: "2026-11-10",
      temp_max_c: 31.2,
      temp_min_c: 22.7,
      rain_mm: 1.1,
      weather_code: 53,
      condition: "drizzle",
    });
    expect(out.past![6].date).toBe("2026-11-16");
    expect(out.forecast).toHaveLength(8);
    expect(out.forecast![0].date).toBe("2026-11-17");
    expect(out.forecast![3]).toEqual({
      date: "2026-11-20",
      temp_max_c: 24.9,
      temp_min_c: 21.9,
      rain_mm: 16.4,
      rain_probability_pct: 37,
      weather_code: 81,
      condition: "rain",
    });
  });

  it("derives today from the API current.time when not passed", () => {
    const out = transformOpenMeteo(FORECAST_PAYLOAD, DHAKA);
    expect(out.past).toHaveLength(7);
    expect(out.forecast).toHaveLength(8);
    expect(out.forecast![0].date).toBe("2026-11-17");
  });

  it("labels an empty past instead of inventing it", () => {
    const noPast = {
      ...FORECAST_PAYLOAD,
      daily: {
        time: FORECAST_PAYLOAD.daily.time.slice(7),
        temperature_2m_max: FORECAST_PAYLOAD.daily.temperature_2m_max.slice(7),
        temperature_2m_min: FORECAST_PAYLOAD.daily.temperature_2m_min.slice(7),
        precipitation_sum: FORECAST_PAYLOAD.daily.precipitation_sum.slice(7),
        precipitation_probability_max:
          FORECAST_PAYLOAD.daily.precipitation_probability_max.slice(7),
        weather_code: FORECAST_PAYLOAD.daily.weather_code.slice(7),
      },
    };
    const out = transformOpenMeteo(noPast, DHAKA, "2026-11-17");
    expect(out.past).toEqual([]);
    expect(out.notes).toEqual(["past_unavailable"]);
    expect(out.forecast).toHaveLength(8);
  });

  it("turns missing fields into null, never 0", () => {
    const sparse = {
      timezone: "Asia/Dhaka",
      current: { time: "2026-11-17T11:15" },
      daily: { time: ["2026-11-17"], temperature_2m_max: [29.8] },
    };
    const out = transformOpenMeteo(sparse, DHAKA, "2026-11-17");
    expect(out.current!.temperature_c).toBeNull();
    expect(out.current!.condition).toBe("unknown");
    expect(out.forecast![0].temp_min_c).toBeNull();
    expect(out.forecast![0].rain_mm).toBeNull();
    expect(out.forecast![0].rain_probability_pct).toBeNull();
  });
});

describe("fetchDirectWeather", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls the Forecast API with the backend's params and transforms the payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => FORECAST_PAYLOAD,
    });
    vi.stubGlobal("fetch", fetchMock);
    const out = await fetchDirectWeather(DHAKA);
    expect(out).not.toBeNull();
    expect(out!.available).toBe(true);
    expect(out!.past).toHaveLength(7);
    expect(out!.forecast).toHaveLength(8);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("api.open-meteo.com/v1/forecast");
    expect(url).toContain("past_days=7");
    expect(url).toContain("forecast_days=8");
    expect(url).toContain("latitude=23.8103");
    expect(url).not.toContain("archive-api");
  });

  it("returns null on a non-OK response (e.g. 429)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 429 }));
    await expect(fetchDirectWeather(DHAKA)).resolves.toBeNull();
  });

  it("returns null when fetch throws", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    await expect(fetchDirectWeather(DHAKA)).resolves.toBeNull();
  });

  it("returns null on a non-JSON body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => {
        throw new Error("bad json");
      },
    }));
    await expect(fetchDirectWeather(DHAKA)).resolves.toBeNull();
  });
});
