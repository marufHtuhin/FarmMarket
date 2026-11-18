import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { EmailVerificationBanner } from "../layout/EmailVerificationBanner";

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

function loginAs(emailVerified: boolean) {
  const user: User = {
    id: 1, name: "Test User", email: "t@x.t", role: "farmer", email_verified: emailVerified,
  };
  localStorage.setItem("fm_access_token", "fake-token");
  localStorage.setItem("fm_user", JSON.stringify(user));
  mocked.me.mockResolvedValue(user);
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem("fm_lang", "en");
  vi.clearAllMocks();
});

describe("EmailVerificationBanner", () => {
  it("shows for a logged-in unverified user and resends on click", async () => {
    loginAs(false);
    mocked.resendVerification.mockResolvedValue({ message: "Verification email sent." });
    renderWithProviders(<EmailVerificationBanner />);

    expect(await screen.findByText("Your email is not verified yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Resend"));
    await waitFor(() => expect(mocked.resendVerification).toHaveBeenCalledTimes(1));
  });

  it("does not show for a verified user", () => {
    loginAs(true);
    renderWithProviders(<EmailVerificationBanner />);
    expect(screen.queryByText("Your email is not verified yet.")).not.toBeInTheDocument();
  });

  it("does not show when logged out", () => {
    renderWithProviders(<EmailVerificationBanner />);
    expect(screen.queryByText("Your email is not verified yet.")).not.toBeInTheDocument();
  });

  it("stays dismissed for the session after dismiss", async () => {
    loginAs(false);
    const { unmount } = renderWithProviders(<EmailVerificationBanner />);
    expect(await screen.findByText("Your email is not verified yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Dismiss"));
    expect(screen.queryByText("Your email is not verified yet.")).not.toBeInTheDocument();
    expect(sessionStorage.getItem("fm_email_banner_dismissed")).toBe("1");
    unmount();
    // A fresh mount in the same session still hides it.
    renderWithProviders(<EmailVerificationBanner />);
    expect(screen.queryByText("Your email is not verified yet.")).not.toBeInTheDocument();
  });
});
