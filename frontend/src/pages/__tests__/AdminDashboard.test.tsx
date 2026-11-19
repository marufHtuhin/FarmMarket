import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { AdminDashboardPage } from "../AdminDashboard";

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return { ...actual, adminApi: { stats: vi.fn() } };
});

import { adminApi, type AdminStats } from "../../services/api";

const never = () => new Promise<never>(() => {});

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("fm_lang", "en");
  vi.clearAllMocks();
});

// The live-site counts from the 19 Nov 2026 QA: the dashboard showed 0
// for every one of these before the stats-contract fix.
const STATS: AdminStats = {
  total_users: 16,
  total_products: 10,
  total_orders: 1,
  total_revenue: 20400,
  pending_orders: 1,
  users_by_role: { farmer: 7, buyer: 3, transporter: 1, admin: 1 },
  recent_activity: [
    { kind: "order", title: "#1", detail: "Rice · 500 kg", created_at: "2026-11-18T18:00:00" },
    { kind: "product", title: "Tomato", detail: "Gazipur", created_at: "2026-11-18T17:00:00" },
    { kind: "user", title: "Rahim Uddin", detail: "farmer", created_at: "2026-11-18T16:00:00" },
  ],
};

describe("Admin dashboard (19 Nov 2026 live QA)", () => {
  it("shows real counts from /admin/stats instead of zeros", async () => {
    vi.mocked(adminApi.stats).mockResolvedValue(STATS);
    renderWithProviders(<AdminDashboardPage />);
    expect(await screen.findByText("Total users")).toBeInTheDocument();
    expect(screen.getByText("16")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("৳20,400")).toBeInTheDocument();
    expect(screen.getByText(/farmer: 7/)).toBeInTheDocument();
  });

  it("renders the recent activity feed, newest first", async () => {
    vi.mocked(adminApi.stats).mockResolvedValue(STATS);
    renderWithProviders(<AdminDashboardPage />);
    expect(await screen.findByText("Recent activity")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText(/Rice · 500 kg/)).toBeInTheDocument();
    expect(screen.getByText("Tomato")).toBeInTheDocument();
    expect(screen.getByText("Rahim Uddin")).toBeInTheDocument();
    // Newest (the order) renders before the older product entry.
    const items = screen.getAllByRole("listitem");
    expect(items[0].textContent).toContain("#1");
  });

  it("shows a spinner — never zero counters — while loading", async () => {
    vi.mocked(adminApi.stats).mockImplementation(never);
    renderWithProviders(<AdminDashboardPage />);
    expect(await screen.findByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("Total users")).not.toBeInTheDocument();
    expect(screen.queryByText("Recent activity")).not.toBeInTheDocument();
  });

  it("shows the empty-activity message when the feed is empty", async () => {
    vi.mocked(adminApi.stats).mockResolvedValue({ ...STATS, recent_activity: [] });
    renderWithProviders(<AdminDashboardPage />);
    expect(await screen.findByText("Recent activity")).toBeInTheDocument();
    expect(screen.getByText("No recent activity yet.")).toBeInTheDocument();
  });
});
