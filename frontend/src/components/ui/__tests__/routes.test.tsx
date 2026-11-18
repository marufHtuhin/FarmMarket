import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router-dom";
import { renderWithProviders } from "../../../test/test-utils";
import { ProtectedRoute } from "../../layout/ProtectedRoute";
import { MarketplacePage } from "../../../pages/Marketplace";
import { ErrorState } from "../core";

// Mock the API module for the marketplace error test.
vi.mock("../../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../services/api")>();
  return {
    ...actual,
    productsApi: {
      list: vi.fn(),
    },
  };
});

import { productsApi } from "../../../services/api";

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="location">{loc.pathname}</div>;
}

describe("ProtectedRoute", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("redirects unauthenticated users to /login", async () => {
    renderWithProviders(
      <Routes>
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <div>Secret dashboard</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<div>Login page</div>} />
        <Route path="*" element={<LocationProbe />} />
      </Routes>,
      { route: "/dashboard" }
    );
    await waitFor(() => {
      expect(screen.getByText("Login page")).toBeInTheDocument();
    });
    expect(screen.queryByText("Secret dashboard")).not.toBeInTheDocument();
  });
});

describe("MarketplacePage error state", () => {
  it("renders a friendly error state when the products API fails", async () => {
    vi.mocked(productsApi.list).mockRejectedValueOnce({
      response: { data: { detail: "Server exploded" }, status: 500 },
      message: "Request failed with status code 500",
    });
    renderWithProviders(<MarketplacePage />, { route: "/marketplace" });
    await waitFor(() => {
      expect(screen.getByText("Server exploded")).toBeInTheDocument();
    });
    expect(screen.getByText("Try again")).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("renders the message and a retry button", () => {
    const onRetry = vi.fn();
    renderWithProviders(<ErrorState message="Boom" onRetry={onRetry} />);
    expect(screen.getByText("Boom")).toBeInTheDocument();
    screen.getByText("Try again").click();
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
