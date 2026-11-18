import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { RegisterPage } from "../Register";

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return {
    ...actual,
    authApi: {
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      me: vi.fn(),
      forgotPassword: vi.fn(),
      resetPassword: vi.fn(),
      verifyEmail: vi.fn(),
      resendVerification: vi.fn(),
    },
  };
});

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem("fm_lang", "en");
  vi.clearAllMocks();
});

function districtSelect() {
  return screen.getByRole("combobox", { name: /District/ });
}

function upazilaSelect() {
  return screen.getByRole("combobox", { name: /Upazila/ });
}

function districtOptions() {
  return within(districtSelect())
    .getAllByRole("option")
    .filter((o) => (o as HTMLOptionElement).value !== "");
}

describe("RegisterPage location selects", () => {
  it("renders all 64 districts in the district select", () => {
    renderWithProviders(<RegisterPage />, { route: "/register" });
    expect(districtOptions()).toHaveLength(64);
    expect(within(districtSelect()).getByRole("option", { name: "Dhaka" })).toBeInTheDocument();
    expect(within(districtSelect()).getByRole("option", { name: "Chattogram" })).toBeInTheDocument();
  });

  it("keeps the upazila select disabled until a district is chosen", () => {
    renderWithProviders(<RegisterPage />, { route: "/register" });
    expect(upazilaSelect()).toBeDisabled();
    fireEvent.change(districtSelect(), { target: { value: "Dhaka" } });
    expect(upazilaSelect()).not.toBeDisabled();
  });

  it("populates the upazila select from the chosen district", () => {
    renderWithProviders(<RegisterPage />, { route: "/register" });
    fireEvent.change(districtSelect(), { target: { value: "Dhaka" } });
    const options = within(upazilaSelect()).getAllByRole("option");
    // Placeholder + Dhaka's 5 upazilas.
    expect(options).toHaveLength(6);
    expect(within(upazilaSelect()).getByRole("option", { name: "Savar" })).toBeInTheDocument();
  });

  it("resets the upazila when the district changes", () => {
    renderWithProviders(<RegisterPage />, { route: "/register" });
    fireEvent.change(districtSelect(), { target: { value: "Dhaka" } });
    fireEvent.change(upazilaSelect(), { target: { value: "Savar" } });
    expect((upazilaSelect() as HTMLSelectElement).value).toBe("Savar");

    fireEvent.change(districtSelect(), { target: { value: "Khulna" } });
    expect((upazilaSelect() as HTMLSelectElement).value).toBe("");
    expect(
      within(upazilaSelect()).queryByRole("option", { name: "Savar" }),
    ).not.toBeInTheDocument();
  });
});

describe("RegisterPage password visibility toggle", () => {
  it("toggles the password field between hidden and visible, keeping the value", () => {
    const { container } = renderWithProviders(<RegisterPage />, { route: "/register" });
    const password = container.querySelector('input[name="password"]') as HTMLInputElement;
    expect(password.type).toBe("password");

    fireEvent.change(password, { target: { value: "123456" } });
    const toggles = screen.getAllByRole("button", { name: "Show password" });
    expect(toggles).toHaveLength(2); // password + confirm password
    fireEvent.click(toggles[0]);

    expect(password.type).toBe("text");
    expect(password.value).toBe("123456");
    expect(screen.getByRole("button", { name: "Hide password" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password.type).toBe("password");
    expect(password.value).toBe("123456");
  });
});
