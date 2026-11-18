import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { ProductCard } from "../ProductCard";
import { USER_KEY, type Product } from "../../services/api";

/** Phase 11 (audit/p11-13): ProductCard had no tests. Covers rendering,
 * the low-stock boundary (qty 0 / 1-5 / 6+), role-gated action buttons,
 * and opening the order/offer modals. */

const BUYER = { id: 2, name: "Dhaka Fresh Mart", email: "buyer@farmmarket.demo", role: "buyer" as const };
const FARMER = { id: 1, name: "Rahim Uddin", email: "farmer@farmmarket.demo", role: "farmer" as const };

function product(overrides: Partial<Product> = {}): Product {
  return {
    id: 3,
    farmer_id: 1,
    farmer_name: "Rahim Uddin",
    name: "Tomato",
    quantity: 100,
    unit: "kg",
    price_per_unit: 30,
    district: "Gazipur",
    description: "Fresh red tomatoes",
    ...overrides,
  };
}

function seedUser(user: typeof BUYER | typeof FARMER | null) {
  localStorage.clear();
  localStorage.setItem("fm_lang", "en");
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
}

beforeEach(() => {
  localStorage.clear();
});

describe("ProductCard rendering", () => {
  it("renders name, price, district, farmer and available quantity", () => {
    seedUser(BUYER);
    renderWithProviders(<ProductCard product={product()} />);
    expect(screen.getByRole("heading", { name: "Tomato" })).toBeInTheDocument();
    expect(screen.getByText(/30/)).toBeInTheDocument();
    expect(screen.getByText("Gazipur")).toBeInTheDocument();
    expect(screen.getByText("Rahim Uddin")).toBeInTheDocument();
    expect(screen.getByText(/Available/)).toBeInTheDocument();
    expect(screen.getByText("Fresh red tomatoes")).toBeInTheDocument();
  });

  it("links the card title to the product detail page", () => {
    seedUser(null);
    renderWithProviders(<ProductCard product={product()} />);
    const link = screen.getByRole("heading", { name: "Tomato" }).closest("a");
    expect(link).toHaveAttribute("href", "/marketplace/3");
  });
});

describe("ProductCard low-stock badge", () => {
  it.each([1, 5])("shows Low stock at quantity %s", (qty) => {
    seedUser(null);
    renderWithProviders(<ProductCard product={product({ quantity: qty })} />);
    expect(screen.getByText("Low stock")).toBeInTheDocument();
  });

  it.each([0, 6, 100])("hides Low stock at quantity %s", (qty) => {
    seedUser(null);
    renderWithProviders(<ProductCard product={product({ quantity: qty })} />);
    expect(screen.queryByText("Low stock")).not.toBeInTheDocument();
  });
});

describe("ProductCard role-gated actions", () => {
  it("shows Order and Make an offer buttons to a buyer with stock", () => {
    seedUser(BUYER);
    renderWithProviders(<ProductCard product={product()} />);
    expect(screen.getByRole("button", { name: /Order/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Make an offer/ })).toBeInTheDocument();
  });

  it("hides the action buttons from a buyer when out of stock", () => {
    seedUser(BUYER);
    renderWithProviders(<ProductCard product={product({ quantity: 0 })} />);
    expect(screen.queryByRole("button", { name: /Order/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Make an offer/ })).not.toBeInTheDocument();
  });

  it("hides the action buttons from a farmer", () => {
    seedUser(FARMER);
    renderWithProviders(<ProductCard product={product()} />);
    expect(screen.queryByRole("button", { name: /Order/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Make an offer/ })).not.toBeInTheDocument();
  });

  it("hides the action buttons from a logged-out visitor", () => {
    seedUser(null);
    renderWithProviders(<ProductCard product={product()} />);
    expect(screen.queryByRole("button", { name: /Order/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Make an offer/ })).not.toBeInTheDocument();
  });

  it("opens the order modal when a buyer clicks Order", () => {
    seedUser(BUYER);
    renderWithProviders(<ProductCard product={product()} />);
    fireEvent.click(screen.getByRole("button", { name: /Order/ }));
    expect(screen.getByRole("dialog", { name: "Order: Tomato" })).toBeInTheDocument();
  });

  it("opens the offer modal when a buyer clicks Make an offer", () => {
    seedUser(BUYER);
    renderWithProviders(<ProductCard product={product()} />);
    fireEvent.click(screen.getByRole("button", { name: /Make an offer/ }));
    expect(screen.getByRole("dialog", { name: "Make an offer: Tomato" })).toBeInTheDocument();
  });
});
