import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { MatchesPage } from "../Matches";

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return { ...actual, matchesApi: { list: vi.fn() } };
});

import { matchesApi, type Match } from "../../services/api";

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("fm_lang", "en");
  vi.clearAllMocks();
});

const MATCH: Match = {
  demand_id: 1,
  buyer_name: "Dhaka Fresh Mart",
  product_id: 2,
  product_name: "Tomato",
  farmer_id: 3,
  farmer_name: "Rahim Uddin",
  quantity: 600,
  required_quantity: 500,
  unit: "kg",
  farmer_price: 35,
  target_price: 38,
  district: "Dhaka",
  score: 95.71,
  reasons: ["Full quantity available", "Same district"],
};

describe("Matches page (19 Nov 2026 live QA)", () => {
  it("labels the required quantity as quantity, not price", async () => {
    vi.mocked(matchesApi.list).mockResolvedValue([MATCH]);
    renderWithProviders(<MatchesPage />);
    // The 500 kg the buyer needs is a quantity — the old label said
    // "Target price: 500 kg".
    expect(await screen.findByText(/Target quantity:/)).toBeInTheDocument();
    expect(screen.queryByText(/Target price:/)).not.toBeInTheDocument();
    // The real price figures keep their own labels.
    expect(screen.getByText(/Buyer budget:/)).toBeInTheDocument();
    expect(screen.getByText(/Farmer price:/)).toBeInTheDocument();
  });
});
