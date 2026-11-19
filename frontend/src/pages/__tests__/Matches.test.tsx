import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { MatchesPage } from "../Matches";

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return { ...actual, matchesApi: { list: vi.fn() } };
});

import { matchesApi, type Match, type User } from "../../services/api";

function seedUser(role: "farmer" | "buyer" | "admin") {
  const user: User = { id: 1, name: "Test", email: "t@x.t", role };
  localStorage.setItem("fm_user", JSON.stringify(user));
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("fm_lang", "en");
  vi.clearAllMocks();
});

const MATCH: Match = {
  demand_id: 1,
  buyer_id: 9,
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

describe("Matches page messaging (19 Nov 2026 farmer->buyer fix)", () => {
  it("a farmer sees a Message buyer button on each match card", async () => {
    seedUser("farmer");
    vi.mocked(matchesApi.list).mockResolvedValue([MATCH]);
    renderWithProviders(<MatchesPage />);
    expect(await screen.findByRole("button", { name: "Message buyer" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Message farmer" })).not.toBeInTheDocument();
  });

  it("a buyer sees a Message farmer button on each match card", async () => {
    seedUser("buyer");
    vi.mocked(matchesApi.list).mockResolvedValue([MATCH]);
    renderWithProviders(<MatchesPage />);
    expect(await screen.findByRole("button", { name: "Message farmer" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Message buyer" })).not.toBeInTheDocument();
  });

  it("other roles see no message button (they are not parties to the match)", async () => {
    seedUser("admin");
    vi.mocked(matchesApi.list).mockResolvedValue([MATCH]);
    renderWithProviders(<MatchesPage />);
    expect(await screen.findByText(/Target quantity:/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Message buyer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Message farmer" })).not.toBeInTheDocument();
  });
});
