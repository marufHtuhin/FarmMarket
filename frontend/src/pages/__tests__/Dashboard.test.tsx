import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { DashboardPage } from "../Dashboard";

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return {
    ...actual,
    dashboardApi: { get: vi.fn() },
    ordersApi: { listMine: vi.fn() },
    demandsApi: { list: vi.fn(), create: vi.fn() },
    deliveriesApi: { list: vi.fn() },
    vehiclesApi: { list: vi.fn() },
    productsApi: { list: vi.fn() },
  };
});

import {
  dashboardApi,
  demandsApi,
  deliveriesApi,
  ordersApi,
  vehiclesApi,
  type DashboardData,
  type Demand,
  type Delivery,
  type Order,
  type User,
  type Vehicle,
} from "../../services/api";

const never = () => new Promise<never>(() => {});

function seedUser(role: "buyer" | "transporter") {
  const user: User = { id: 1, name: "Test", email: "t@x.t", role };
  localStorage.setItem("fm_user", JSON.stringify(user));
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("fm_lang", "en");
  vi.clearAllMocks();
});

const BUYER_DASH: DashboardData = {
  role: "buyer",
  total_orders: 1,
  open_demands: 4,
  total_spent: 20400,
  recent_orders: 1,
};

const ORDERS: Order[] = [
  { id: 1, product_name: "Rice", quantity: 500, unit: "kg", unit_price: 40.8,
    total_amount: 20400, status: "accepted" },
];

const DEMANDS: Demand[] = [
  { id: 1, product_name: "Tomato", required_quantity: 500, unit: "kg",
    target_price: 38, district: "Dhaka" },
];

describe("Dashboard loading states (19 Nov 2026 live QA)", () => {
  it("buyer: shows spinners — never 'No orders yet' / empty demands — while loading", async () => {
    seedUser("buyer");
    vi.mocked(dashboardApi.get).mockResolvedValue(BUYER_DASH);
    vi.mocked(ordersApi.listMine).mockImplementation(never);
    vi.mocked(demandsApi.list).mockImplementation(never);
    renderWithProviders(<DashboardPage />);
    // Wait for the buyer dashboard to mount (auth loading cleared).
    await screen.findByText("Recent orders");
    // Both cards spin while their queries are pending…
    expect(screen.getAllByRole("status").length).toBeGreaterThanOrEqual(2);
    // …and neither misleading empty state flashes.
    expect(screen.queryByText("No orders yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("There are no open demands yet.")).not.toBeInTheDocument();
  });

  it("buyer: renders orders and demands once they arrive", async () => {
    seedUser("buyer");
    vi.mocked(dashboardApi.get).mockResolvedValue(BUYER_DASH);
    vi.mocked(ordersApi.listMine).mockResolvedValue(ORDERS);
    vi.mocked(demandsApi.list).mockResolvedValue(DEMANDS);
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText(/#1 · Rice/)).toBeInTheDocument();
    expect(await screen.findByText("Tomato")).toBeInTheDocument();
    expect(screen.queryByText("No orders yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("There are no open demands yet.")).not.toBeInTheDocument();
  });

  it("transporter: shows a spinner — never 0-count stat cards — while loading", async () => {
    seedUser("transporter");
    vi.mocked(deliveriesApi.list).mockImplementation(never);
    vi.mocked(vehiclesApi.list).mockImplementation(never);
    renderWithProviders(<DashboardPage />);
    await screen.findByText("Deliveries");
    expect(screen.getAllByRole("status").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Active deliveries")).not.toBeInTheDocument();
    expect(screen.queryByText("My vehicles")).not.toBeInTheDocument();
    expect(screen.queryByText("No deliveries yet.")).not.toBeInTheDocument();
  });

  it("transporter: renders stat counts once data arrives", async () => {
    seedUser("transporter");
    const deliveries: Delivery[] = [
      { order_id: 1, product_name: "Rice", delivery_status: "in_transit" },
      { order_id: 2, product_name: "Tomato", delivery_status: "delivered" },
    ];
    const vehicles: Vehicle[] = [
      { id: 1, vehicle_type: "Truck", capacity_kg: 1000 },
    ];
    vi.mocked(deliveriesApi.list).mockResolvedValue(deliveries);
    vi.mocked(vehiclesApi.list).mockResolvedValue(vehicles);
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText("Active deliveries")).toBeInTheDocument();
    expect(screen.getByText("My vehicles")).toBeInTheDocument();
    expect(await screen.findByText(/#1 · Rice/)).toBeInTheDocument();
  });
});
