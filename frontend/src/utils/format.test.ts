import { describe, expect, it } from "vitest";
import {
  apiErrorMessage,
  apiStatus,
  formatPriceTaka,
  isNotFound,
  statusTone,
  unitLabel,
} from "./format";

/** Phase 11 (audit/p11-13): src/utils/format.ts had no tests. Covers unit
 * labels (both languages + unknown units), status tones, and the API
 * error-message/status helpers used across pages. */

describe("unitLabel", () => {
  it("returns English labels", () => {
    expect(unitLabel("kg", "en")).toBe("kg");
    expect(unitLabel("quintal", "en")).toBe("quintal");
    expect(unitLabel("ton", "en")).toBe("ton");
    expect(unitLabel("piece", "en")).toBe("piece");
  });

  it("returns Bangla labels", () => {
    expect(unitLabel("kg", "bn")).toBe("কেজি");
    expect(unitLabel("quintal", "bn")).toBe("কুইন্টাল");
    expect(unitLabel("ton", "bn")).toBe("টন");
    expect(unitLabel("piece", "bn")).toBe("টি");
  });

  it("is case-insensitive", () => {
    expect(unitLabel("KG", "en")).toBe("kg");
    expect(unitLabel("Quintal", "bn")).toBe("কুইন্টাল");
  });

  it("defaults null/undefined/empty to kg", () => {
    expect(unitLabel(null, "en")).toBe("kg");
    expect(unitLabel(undefined, "bn")).toBe("কেজি");
    expect(unitLabel("", "en")).toBe("kg");
  });

  it("passes unknown units through unchanged", () => {
    expect(unitLabel("sack", "en")).toBe("sack");
    expect(unitLabel("crate", "bn")).toBe("crate");
  });
});

describe("statusTone", () => {
  it.each([
    ["pending", "amber"],
    ["accepted", "green"],
    ["completed", "green"],
    ["delivered", "green"],
    ["active", "green"],
    ["ok", "green"],
    ["rejected", "red"],
    ["cancelled", "red"],
    ["failed", "red"],
    ["excursion", "red"],
    ["in_transit", "blue"],
    ["picked_up", "blue"],
    ["assigned", "blue"],
  ] as const)("maps %s to %s", (status, tone) => {
    expect(statusTone(status)).toBe(tone);
  });

  it("is case-insensitive and falls back to gray", () => {
    expect(statusTone("PENDING")).toBe("amber");
    expect(statusTone("Completed")).toBe("green");
    expect(statusTone("something-else")).toBe("gray");
    expect(statusTone("")).toBe("gray");
  });
});

describe("apiErrorMessage", () => {
  it("prefers a string detail from the response", () => {
    expect(
      apiErrorMessage({ response: { data: { detail: "Email already registered" } } })
    ).toBe("Email already registered");
  });

  it("joins FastAPI 422 array details", () => {
    const err = {
      response: {
        status: 422,
        data: {
          detail: [
            { msg: "Field required", loc: ["body", "name"] },
            { msg: "Value error, too short", loc: ["body", "password"] },
          ],
        },
      },
    };
    expect(apiErrorMessage(err)).toBe("Field required, Value error, too short");
  });

  it("falls back to the error message, then a generic string", () => {
    expect(apiErrorMessage(new Error("Network Error"))).toBe("Network Error");
    expect(apiErrorMessage({})).toBe("Request failed");
    expect(apiErrorMessage(null)).toBe("Request failed");
    expect(apiErrorMessage(undefined)).toBe("Request failed");
    expect(apiErrorMessage("oops")).toBe("Request failed");
  });

  it("ignores an empty string detail", () => {
    expect(apiErrorMessage({ response: { data: { detail: "" } }, message: "Boom" })).toBe("Boom");
  });
});

describe("apiStatus / isNotFound", () => {
  it("reads the HTTP status", () => {
    expect(apiStatus({ response: { status: 404 } })).toBe(404);
    expect(apiStatus({ response: { status: 500 } })).toBe(500);
    expect(apiStatus({})).toBeNull();
    expect(apiStatus(null)).toBeNull();
    expect(apiStatus({ response: { status: "404" } })).toBeNull();
  });

  it("detects 404s", () => {
    expect(isNotFound({ response: { status: 404 } })).toBe(true);
    expect(isNotFound({ response: { status: 403 } })).toBe(false);
    expect(isNotFound(null)).toBe(false);
  });
});

describe("formatPriceTaka", () => {
  const fmtNum = (n: number | string | null | undefined) => String(n ?? "—");

  it("prefixes the taka sign", () => {
    expect(formatPriceTaka(30, fmtNum)).toBe("৳30");
    expect(formatPriceTaka("1,250", fmtNum)).toBe("৳1,250");
  });
});
