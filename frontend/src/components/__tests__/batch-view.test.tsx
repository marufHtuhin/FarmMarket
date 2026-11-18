import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { BatchView } from "../BatchView";
import type { BatchPublic } from "../../services/api";

// Recharts' ResponsiveContainer needs layout dimensions jsdom cannot give,
// so the chart is stubbed; the point under test is that BatchView builds
// chart points from the API payload at all.
vi.mock("../../components/charts", () => ({
  SensorTempChart: ({ data }: { data: Array<{ time: string; temp: number }> }) => (
    <div data-testid="sensor-chart" data-points={data.length} data-temps={data.map((d) => d.temp).join(",")} />
  ),
}));

function batch(over: Partial<BatchPublic> = {}): BatchPublic {
  return {
    batch_code: "FM-TEST123456",
    crop: "tomato",
    origin_district: "Gazipur",
    harvested_at: "2026-11-01T06:00:00",
    timeline: [
      { time: "2026-11-01T06:00:00", event: "harvested" },
      { time: "2026-11-02T12:00:00", event: "cold_chain_check", readings: 3, status: "ok", temp_c: { min: 12, max: 14, avg: 13 } },
      { time: "2026-11-03T12:00:00", event: "cold_chain_check", readings: 3, status: "ok", temp_c: { min: 13, max: 16, avg: 14.5 } },
    ],
    cold_chain: {
      n_readings: 6,
      simulated_readings: 0,
      status: "ok",
      temp_c: { min: 12, max: 16, avg: 13.8 },
    },
    integrity: {
      chain_valid: true,
      blocks: 3,
      head_hash: "ab".repeat(32),
      unsealed_readings: 0,
      externally_anchored: false,
      note: "Hash-chained and signature-checked. Not yet anchored to an external ledger.",
    },
    ...over,
  };
}

describe("BatchView sensor chart (audit p7-8)", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("fm_lang", "en");
  });

  it("renders the sensor chart from seal summary objects (temp_c {min,max,avg})", () => {
    // Regression test: the API sends temp_c as an object, but BatchView used
    // to expect a number, so tempPoints was always empty and the chart never
    // rendered — every batch showed 'No sensor readings yet.'
    const { container } = renderWithProviders(<BatchView batch={batch()} showQr={false} />);
    const chart = screen.getByTestId("sensor-chart");
    expect(chart).toBeInTheDocument();
    expect(chart.getAttribute("data-points")).toBe("2");
    expect(chart.getAttribute("data-temps")).toBe("13,14.5");
    expect(screen.queryByText("No sensor readings yet.")).not.toBeInTheDocument();
    // Timeline shows the per-seal average temperature.
    expect(container.textContent).toContain("13°C");
    expect(container.textContent).toContain("14.5°C");
  });

  it("shows the empty state when there are no sealed readings", () => {
    renderWithProviders(
      <BatchView
        batch={batch({ timeline: [{ time: "2026-11-01T06:00:00", event: "harvested" }], cold_chain: { n_readings: 0, status: "no_data" } })}
        showQr={false}
      />
    );
    expect(screen.getByText("No sensor readings yet.")).toBeInTheDocument();
    expect(screen.queryByTestId("sensor-chart")).not.toBeInTheDocument();
  });

  it("shows the SIMULATED badge when readings are simulated", () => {
    renderWithProviders(
      <BatchView batch={batch({ cold_chain: { n_readings: 6, simulated_readings: 6, status: "ok" } })} showQr={false} />
    );
    expect(screen.getByText("Simulated")).toBeInTheDocument();
  });
});

describe("BatchView QR verify link", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("fm_lang", "en");
  });

  it("shows the exact URL the QR encodes, as a copyable link under the QR", () => {
    const url = "https://farm-5173.inc1.devtunnels.ms/verify/FM-TEST123456";
    renderWithProviders(<BatchView batch={batch({ verify_url: url })} />);
    expect(screen.getByText("Scanning the QR opens this link")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: url });
    expect(link).toHaveAttribute("href", url);
    expect(screen.getByRole("button", { name: /Copy link/ })).toBeInTheDocument();
  });

  it("shows nothing extra when the API sent no verify_url", () => {
    renderWithProviders(<BatchView batch={batch()} />);
    expect(screen.queryByText("Scanning the QR opens this link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Copy link/ })).not.toBeInTheDocument();
  });

  it("copies the verify link to the clipboard", async () => {
    const url = "https://farm-5173.inc1.devtunnels.ms/verify/FM-TEST123456";
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderWithProviders(<BatchView batch={batch({ verify_url: url })} />);
    screen.getByRole("button", { name: /Copy link/ }).click();
    expect(writeText).toHaveBeenCalledWith(url);
    // The button flips to "Copied" once the async write resolves.
    expect(await screen.findByRole("button", { name: /Copied/ })).toBeInTheDocument();
  });
});
