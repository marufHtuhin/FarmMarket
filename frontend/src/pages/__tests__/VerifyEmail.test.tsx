import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { VerifyEmailPage } from "../VerifyEmail";

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

import { authApi, type User } from "../../services/api";

const mocked = vi.mocked(authApi);

const USER: User = {
  id: 1, name: "Test User", email: "t@x.t", role: "farmer", email_verified: false,
};

function loginAs(user: User = USER) {
  localStorage.setItem("fm_access_token", "fake-token");
  localStorage.setItem("fm_refresh_token", "fake-refresh");
  localStorage.setItem("fm_user", JSON.stringify(user));
  mocked.me.mockResolvedValue(user);
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem("fm_lang", "en");
  vi.clearAllMocks();
});

describe("VerifyEmailPage", () => {
  it("verifies the token from the URL and shows success", async () => {
    mocked.verifyEmail.mockResolvedValue({ verified: true });
    renderWithProviders(<VerifyEmailPage />, { route: "/verify-email?token=abc123" });

    expect(screen.getByText("Verifying your email…")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Your email has been verified.")).toBeInTheDocument());
    expect(mocked.verifyEmail).toHaveBeenCalledWith("abc123");
    expect(mocked.verifyEmail).toHaveBeenCalledTimes(1);
  });

  it("shows the invalid state when the token is rejected (logged out)", async () => {
    mocked.verifyEmail.mockRejectedValue(new Error("Invalid or expired verification token"));
    renderWithProviders(<VerifyEmailPage />, { route: "/verify-email?token=bad" });

    await waitFor(() =>
      expect(screen.getByText("This verification link is invalid or has expired.")).toBeInTheDocument()
    );
    // Logged out: no resend button, just a way back to login.
    expect(screen.queryByText("Resend verification email")).not.toBeInTheDocument();
    expect(screen.getByText("Back to login")).toBeInTheDocument();
  });

  it("offers resend when logged in and the token is rejected", async () => {
    loginAs();
    mocked.verifyEmail.mockRejectedValue(new Error("Invalid or expired verification token"));
    mocked.resendVerification.mockResolvedValue({ message: "Verification email sent." });
    renderWithProviders(<VerifyEmailPage />, { route: "/verify-email?token=bad" });

    const resend = await screen.findByText("Resend verification email");
    fireEvent.click(resend);
    await waitFor(() => expect(mocked.resendVerification).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByText("Verification email resent. Check your inbox.")).toBeInTheDocument()
    );
  });

  it("shows the no-token state without calling the API", async () => {
    renderWithProviders(<VerifyEmailPage />, { route: "/verify-email" });

    expect(screen.getByText("No verification token was provided.")).toBeInTheDocument();
    expect(mocked.verifyEmail).not.toHaveBeenCalled();
  });
});
