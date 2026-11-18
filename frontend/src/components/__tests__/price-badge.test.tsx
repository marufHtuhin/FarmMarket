import { describe, expect, it, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { dictionaries } from "../../i18n/LanguageContext";
import { timeAgo } from "../../utils/format";
import { PriceLabelBadge, PriceProvenance, StaleWarning } from "../PriceBadge";

beforeEach(() => {
  localStorage.clear(); // default language is Bangla
  localStorage.setItem("fm_lang", "en");
});

const tEn = (key: string, vars?: Record<string, string | number>) => {
  let s = (dictionaries.en as Record<string, string>)[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
  return s;
};

describe("timeAgo", () => {
  const now = new Date("2026-11-17T12:00:00Z").getTime();
  it("says just now under a minute, then minutes / hours / days", () => {
    expect(timeAgo("2026-11-17T11:59:30Z", tEn, now)).toBe("just now");
    expect(timeAgo("2026-11-17T11:30:00Z", tEn, now)).toBe("30 min ago");
    expect(timeAgo("2026-11-17T09:00:00Z", tEn, now)).toBe("3 hours ago");
    expect(timeAgo("2026-11-14T12:00:00Z", tEn, now)).toBe("3 days ago");
  });
  it("returns empty for a missing or unparseable timestamp (no faked age)", () => {
    expect(timeAgo(null, tEn, now)).toBe("");
    expect(timeAgo(undefined, tEn, now)).toBe("");
    expect(timeAgo("not-a-date", tEn, now)).toBe("");
  });
});

describe("PriceLabelBadge", () => {
  it("shows REAL for a real price", () => {
    renderWithProviders(<PriceLabelBadge label="real" />);
    expect(screen.getByText("REAL")).toBeInTheDocument();
  });
  it("shows DEMO for a demo price", () => {
    renderWithProviders(<PriceLabelBadge label="demo" />);
    expect(screen.getByText("DEMO")).toBeInTheDocument();
  });
  it("falls back to DEMO when the label is missing — never claims REAL", () => {
    renderWithProviders(<PriceLabelBadge label={undefined} />);
    expect(screen.getByText("DEMO")).toBeInTheDocument();
  });
});

describe("StaleWarning", () => {
  it("shows the stale warning only when stale", () => {
    const { rerender } = renderWithProviders(<StaleWarning stale={false} />);
    expect(screen.queryByText(/Stale/)).not.toBeInTheDocument();
    rerender(<StaleWarning stale />);
    expect(screen.getByText(/Stale — older than 48h/)).toBeInTheDocument();
  });
});

describe("PriceProvenance", () => {
  it("shows source and updated-ago, and omits what is missing", () => {
    renderWithProviders(<PriceProvenance source="manual" updatedAt={new Date(Date.now() - 30 * 60000).toISOString()} />);
    expect(screen.getByText(/Source: manual/)).toBeInTheDocument();
    expect(screen.getByText(/Updated 30 min ago/)).toBeInTheDocument();
  });
  it("labels market day and entry time separately when both are known", () => {
    // A price observed on Sunday but entered on Wednesday must not read as
    // the ambiguous "Updated 3 days ago · 11/15/2026".
    renderWithProviders(
      <PriceProvenance
        source={null}
        updatedAt="2026-11-18T05:41:33Z"
        observedOn="2026-11-15"
      />
    );
    expect(screen.getByText(/Market day: 11\/15\/2026/)).toBeInTheDocument();
    expect(screen.getByText(/Entered:/)).toBeInTheDocument();
    expect(screen.queryByText(/Updated/)).not.toBeInTheDocument();
  });
  it("shows only the market day when the entry time is missing", () => {
    renderWithProviders(<PriceProvenance source={null} updatedAt={null} observedOn="2026-11-15" />);
    expect(screen.getByText(/Market day: 11\/15\/2026/)).toBeInTheDocument();
    expect(screen.queryByText(/Entered/)).not.toBeInTheDocument();
  });
  it("renders nothing when there is no provenance at all", () => {
    const { container } = renderWithProviders(<PriceProvenance source={null} updatedAt={null} />);
    expect(container.querySelector("p")).toBeNull();
  });
});
