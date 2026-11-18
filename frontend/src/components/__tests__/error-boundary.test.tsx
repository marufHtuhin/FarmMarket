import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { ErrorBoundary } from "../ErrorBoundary";

// React logs caught render errors to console.error; silence that noise here.
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  localStorage.clear(); // default language is Bangla
  shouldThrow = true;
});
afterEach(() => {
  vi.restoreAllMocks();
});

let shouldThrow = true;

function Exploding() {
  if (shouldThrow) throw new Error("boom");
  return <div>Recovered content</div>;
}

describe("ErrorBoundary", () => {
  it("shows a friendly fallback when a child crashes, and recovers on retry", () => {
    renderWithProviders(
      <ErrorBoundary>
        <Exploding />
      </ErrorBoundary>
    );

    // Default language is Bangla (errorTitle / retry dictionary keys).
    expect(screen.getByText("কিছু ভুল হয়েছে")).toBeInTheDocument();
    expect(screen.getByText("আবার চেষ্টা করুন")).toBeInTheDocument();
    expect(screen.queryByText("Recovered content")).not.toBeInTheDocument();

    shouldThrow = false;
    // fireEvent (unlike a raw .click()) flushes React state updates via act,
    // so the boundary's reset re-renders before the assertions below.
    fireEvent.click(screen.getByText("আবার চেষ্টা করুন"));
    expect(screen.getByText("Recovered content")).toBeInTheDocument();
    expect(screen.queryByText("কিছু ভুল হয়েছে")).not.toBeInTheDocument();
  });

  it("resets when resetKey changes (navigating away from a crashed page)", () => {
    const { rerender } = renderWithProviders(
      <ErrorBoundary resetKey="/crashed-page">
        <Exploding />
      </ErrorBoundary>
    );
    expect(screen.getByText("কিছু ভুল হয়েছে")).toBeInTheDocument();

    shouldThrow = false;
    rerender(
      <ErrorBoundary resetKey="/another-page">
        <Exploding />
      </ErrorBoundary>
    );
    expect(screen.getByText("Recovered content")).toBeInTheDocument();
  });

  it("renders children normally when nothing throws", () => {
    shouldThrow = false;
    renderWithProviders(
      <ErrorBoundary>
        <div>Healthy content</div>
      </ErrorBoundary>
    );
    expect(screen.getByText("Healthy content")).toBeInTheDocument();
  });
});
