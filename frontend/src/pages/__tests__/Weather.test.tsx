import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { WeatherPage } from "../Weather";

// Recharts' ResponsiveContainer needs layout dimensions jsdom cannot give,
// so the chart is stubbed here; the chart itself is covered by the build
// and the live smoke check.
vi.mock("../../components/charts", () => ({
  WeatherChart: () => <div data-testid="weather-chart" />,
}));

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return {
    ...actual,
    weatherApi: { get: vi.fn() },
    forecastApi: { hubs: vi.fn(), sklearn: vi.fn() },
  };
});

// The direct browser fallback is mocked here so the page tests never
// touch the live network; the real fetch + transform are covered by
// utils/openmeteo.test.ts.
vi.mock("../../utils/openmeteo", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../utils/openmeteo")>();
  return { ...actual, fetchDirectWeather: vi.fn() };
});

import { forecastApi, weatherApi, type WeatherResponse } from "../../services/api";
import { fetchDirectWeather } from "../../utils/openmeteo";

const HUBS = {
  profile: "bangladesh",
  hubs: [
    { id: "dhaka", name: "Dhaka", country: "Bangladesh", currency: "BDT", lat: 23.8103, lon: 90.4125 },
    { id: "sylhet", name: "Sylhet", country: "Bangladesh", currency: "BDT", lat: 24.8949, lon: 91.8687 },
  ],
  crops: [],
};

const SUCCESS: WeatherResponse = {
  hub: "dhaka",
  hub_name: "Dhaka",
  available: true,
  source: "open-meteo",
  fetched_at: "2026-11-17T05:15:00+00:00",
  timezone: "Asia/Dhaka",
  current: {
    time: "2026-11-17T11:15",
    temperature_c: 28.9,
    humidity_pct: 51,
    precipitation_mm: 0,
    wind_speed_kmh: 6,
    weather_code: 0,
    condition: "clear",
  },
  past: [
    { date: "2026-11-16", temp_max_c: 29.4, temp_min_c: 21.9, rain_mm: 0, weather_code: 3, condition: "overcast" },
  ],
  forecast: [
    {
      date: "2026-11-17",
      temp_max_c: 29.8,
      temp_min_c: 21.7,
      rain_mm: 0,
      rain_probability_pct: 0,
      weather_code: 3,
      condition: "overcast",
    },
    {
      date: "2026-11-18",
      temp_max_c: 29.0,
      temp_min_c: 19.2,
      rain_mm: 0,
      rain_probability_pct: 1,
      weather_code: 3,
      condition: "overcast",
    },
  ],
  notes: [],
};

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("fm_lang", "en");
  vi.mocked(forecastApi.hubs).mockResolvedValue(HUBS);
  // Default: the direct fallback is unavailable, so each test exercises
  // the backend path unless it opts into the fallback explicitly.
  vi.mocked(fetchDirectWeather).mockResolvedValue(null);
});

describe("WeatherPage", () => {
  it("shows current conditions, chart, past and forecast on success", async () => {
    vi.mocked(weatherApi.get).mockResolvedValueOnce(SUCCESS);
    renderWithProviders(<WeatherPage />, { route: "/weather" });

    await waitFor(() => {
      expect(screen.getByText("Current conditions")).toBeInTheDocument();
    });
    expect(screen.getByText("28.9°C")).toBeInTheDocument();
    expect(screen.getByText("Clear sky")).toBeInTheDocument();
    expect(screen.getByTestId("weather-chart")).toBeInTheDocument();
    expect(screen.getByText("Past 7 days")).toBeInTheDocument();
    expect(screen.getByText("Next 7 days")).toBeInTheDocument();
    expect(screen.getByText(/Source: Open-Meteo/)).toBeInTheDocument();
    expect(vi.mocked(weatherApi.get)).toHaveBeenCalledWith("dhaka");
  });

  it("shows a labelled unavailable state and no weather values when Open-Meteo is down", async () => {
    vi.mocked(weatherApi.get).mockResolvedValueOnce({
      hub: "dhaka",
      hub_name: "Dhaka",
      available: false,
      note: "Open-Meteo weather service is unreachable right now; no weather data is available.",
      source: "open-meteo",
      fetched_at: "2026-11-17T05:15:00+00:00",
    });
    renderWithProviders(<WeatherPage />, { route: "/weather" });

    await waitFor(() => {
      expect(screen.getByText("Weather data is unavailable")).toBeInTheDocument();
    });
    expect(screen.getByText(/Open-Meteo weather service is unreachable/)).toBeInTheDocument();
    expect(screen.queryByText("Current conditions")).not.toBeInTheDocument();
    expect(screen.queryByTestId("weather-chart")).not.toBeInTheDocument();
  });

  it("shows an error state with retry when the request fails", async () => {
    vi.mocked(weatherApi.get).mockRejectedValueOnce({
      response: { data: { detail: "Server exploded" }, status: 500 },
      message: "Request failed with status code 500",
    });
    renderWithProviders(<WeatherPage />, { route: "/weather" });

    await waitFor(() => {
      expect(screen.getByText(/Server exploded/)).toBeInTheDocument();
    });
    expect(screen.getByText("Try again")).toBeInTheDocument();
  });

  it("shows the past-unavailable note when only the archive failed", async () => {
    vi.mocked(weatherApi.get).mockResolvedValueOnce({ ...SUCCESS, past: [], notes: ["past_unavailable"] });
    renderWithProviders(<WeatherPage />, { route: "/weather" });

    await waitFor(() => {
      expect(screen.getByText(/Past-day data is unavailable right now/)).toBeInTheDocument();
    });
    // Today + forecast still render.
    expect(screen.getByText("28.9°C")).toBeInTheDocument();
  });

  it("falls back to a direct browser fetch when the backend reports unavailable", async () => {
    vi.mocked(weatherApi.get).mockResolvedValueOnce({
      hub: "dhaka",
      hub_name: "Dhaka",
      available: false,
      note: "Open-Meteo weather service is unreachable right now; no weather data is available.",
      source: "open-meteo",
      fetched_at: "2026-11-17T05:15:00+00:00",
    });
    vi.mocked(fetchDirectWeather).mockResolvedValueOnce({ ...SUCCESS, direct: true });
    renderWithProviders(<WeatherPage />, { route: "/weather" });

    await waitFor(() => {
      expect(screen.getByText("Current conditions")).toBeInTheDocument();
    });
    expect(screen.getByText("28.9°C")).toBeInTheDocument();
    expect(screen.queryByText("Weather data is unavailable")).not.toBeInTheDocument();
    // The direct payload is labelled as such in the source line.
    expect(screen.getByText(/fetched directly in your browser/)).toBeInTheDocument();
    expect(vi.mocked(fetchDirectWeather)).toHaveBeenCalledWith(
      expect.objectContaining({ id: "dhaka", lat: 23.8103, lon: 90.4125 }),
    );
  });
});
