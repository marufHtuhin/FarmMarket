import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { PricesPage } from "../Prices";

// Recharts' ResponsiveContainer needs layout dimensions jsdom cannot give,
// so the charts are stubbed; the stubs expose the data they were handed so
// the wiring (history endpoint -> chart) is still asserted.
vi.mock("../../components/charts", () => ({
  PriceHistoryChart: ({ data }: { data: Array<{ date: string; price: number }> }) => (
    <div
      data-testid="price-history-chart"
      data-points={data.length}
      data-first-date={data[0]?.date ?? ""}
      data-last-date={data[data.length - 1]?.date ?? ""}
      data-first-price={data[0]?.price ?? ""}
    />
  ),
  ForecastChart: () => <div data-testid="forecast-chart" />,
}));

// Leaflet cannot render in jsdom.
vi.mock("../../components/HubsMap", () => ({
  HubsMap: () => <div data-testid="hubs-map" />,
}));

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return {
    ...actual,
    pricesApi: { list: vi.fn(), latest: vi.fn(), history: vi.fn() },
    forecastApi: { hubs: vi.fn(), sklearn: vi.fn() },
  };
});

import {
  forecastApi,
  pricesApi,
  type ForecastResponse,
  type LatestPrice,
  type PriceRecord,
} from "../../services/api";

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("fm_lang", "en");
  vi.clearAllMocks();
});

const HUBS = {
  profile: "bangladesh",
  hubs: [
    { id: "dhaka", name: "Dhaka", country: "Bangladesh", currency: "BDT", lat: 23.81, lon: 90.41 },
    { id: "chattogram", name: "Chattogram", country: "Bangladesh", currency: "BDT", lat: 22.35, lon: 91.78 },
  ],
  crops: [
    { id: "tomato", name: "Tomato" },
    { id: "potato", name: "Potato" },
  ],
};

// One PriceRecord per product — the old chart source, which gave a 1-point chart.
const RECORDS: PriceRecord[] = [
  { id: 1, product_name: "Tomato", district: "Gazipur", market_name: "Gazipur demo market",
    price_per_unit: 38, unit: "kg", source: "Illustrative demo data", recorded_at: "2026-11-18T05:41:32",
    label: "demo", stale: false },
];

const point = (observed_on: string, price: number, synthetic = true): LatestPrice => ({
  id: 1, hub: "dhaka", crop: "tomato", price, currency: "BDT", unit: "kg",
  source: synthetic ? "synthetic-demo" : "manual", note: null, observed_on,
  ingested_at: "2026-11-18T05:41:33Z", is_synthetic: synthetic,
  label: synthetic ? "demo" : "real", stale: false, age_hours: 77.7,
});

const HISTORY = {
  hub: "dhaka",
  crop: "tomato",
  points: [point("2024-11-24", 83.07), point("2026-11-08", 81.2), point("2026-11-15", 79.4)],
  count: 3,
};

const LATEST = {
  prices: [point("2026-11-15", 79.4)],
  count: 1,
  as_of: "2026-11-18T05:41:37+00:00",
};

const FORECAST: ForecastResponse = {
  model: "sklearn-random-forest",
  hub: { id: "dhaka", name: "Dhaka", country: "Bangladesh", currency: "BDT" },
  crop: "tomato", unit: "kg", horizon: 8,
  series: { points: 104, sources: ["synthetic-demo"], synthetic_share: 1 },
  history: [{ ds: "2026-11-15", y: 79.4 }],
  forecast: [{ ds: "2026-11-22", yhat: 80.1, lower: 74.0, upper: 86.7 }],
  signal: { direction: "up", expected_change_pct: 1.2 },
  reliable: true,
};

function mockAll() {
  vi.mocked(pricesApi.list).mockResolvedValue(RECORDS);
  vi.mocked(pricesApi.latest).mockResolvedValue(LATEST);
  vi.mocked(pricesApi.history).mockResolvedValue(HISTORY);
  vi.mocked(forecastApi.hubs).mockResolvedValue(HUBS);
  vi.mocked(forecastApi.sklearn).mockResolvedValue(FORECAST);
}

describe("PricesPage trend chart (WS3)", () => {
  it("draws the trend from the PriceObservation history, not the single PriceRecord", async () => {
    mockAll();
    renderWithProviders(<PricesPage />);
    const chart = await screen.findByTestId("price-history-chart");
    // 3 history points — not the 1 PriceRecord row the old chart plotted.
    expect(chart).toHaveAttribute("data-points", "3");
    expect(chart).toHaveAttribute("data-first-date", "11/24/2024");
    expect(chart).toHaveAttribute("data-last-date", "11/15/2026");
    expect(chart).toHaveAttribute("data-first-price", "83.07");
    expect(pricesApi.history).toHaveBeenCalledWith("dhaka", "tomato");
  });

  it("labels a synthetic series DEMO and shows the point range", async () => {
    mockAll();
    renderWithProviders(<PricesPage />);
    await screen.findByTestId("price-history-chart");
    expect(screen.getByText("3 points · 11/24/2024 – 11/15/2026")).toBeInTheDocument();
    // DEMO badge appears for the synthetic series (and for the demo record card).
    expect(screen.getAllByText("DEMO").length).toBeGreaterThan(0);
  });

  it("answers the auto-update question under the chart", async () => {
    mockAll();
    renderWithProviders(<PricesPage />);
    await screen.findByTestId("price-history-chart");
    expect(
      screen.getByText(
        "Real prices come from admin daily entry — each new entry adds a point to this chart. Weather updates itself, but prices don't."
      )
    ).toBeInTheDocument();
  });

  it("shows market day and entry time separately in the latest table", async () => {
    mockAll();
    renderWithProviders(<PricesPage />);
    await screen.findByText(/Market day: 11\/15\/2026/);
    expect(screen.getByText(/Entered:/)).toBeInTheDocument();
  });

  it("keeps the PriceRecord cards as-is", async () => {
    mockAll();
    renderWithProviders(<PricesPage />);
    // The record card heading (the crop <option> also says "Tomato").
    expect(await screen.findByRole("heading", { name: "Tomato" })).toBeInTheDocument();
    expect(screen.getByText(/Gazipur demo market/)).toBeInTheDocument();
  });

  it("shows an empty state when the series has no points", async () => {
    mockAll();
    vi.mocked(pricesApi.history).mockResolvedValue({ hub: "dhaka", crop: "tomato", points: [], count: 0 });
    renderWithProviders(<PricesPage />);
    expect(await screen.findByText("Not enough price records to draw a chart.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId("price-history-chart")).not.toBeInTheDocument());
  });
});
