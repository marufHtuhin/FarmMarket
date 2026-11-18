import { describe, expect, it } from "vitest";
import { conditionGlyph, conditionLabelKey } from "./weather";

describe("conditionLabelKey", () => {
  it("maps every backend condition slug to an i18n key", () => {
    expect(conditionLabelKey("clear")).toBe("wxClear");
    expect(conditionLabelKey("partly_cloudy")).toBe("wxPartlyCloudy");
    expect(conditionLabelKey("overcast")).toBe("wxOvercast");
    expect(conditionLabelKey("fog")).toBe("wxFog");
    expect(conditionLabelKey("drizzle")).toBe("wxDrizzle");
    expect(conditionLabelKey("rain")).toBe("wxRainCond");
    expect(conditionLabelKey("snow")).toBe("wxSnow");
    expect(conditionLabelKey("thunderstorm")).toBe("wxThunder");
  });

  it("falls back to wxUnknown for missing or unrecognised slugs", () => {
    expect(conditionLabelKey(null)).toBe("wxUnknown");
    expect(conditionLabelKey(undefined)).toBe("wxUnknown");
    expect(conditionLabelKey("")).toBe("wxUnknown");
    expect(conditionLabelKey("hailstorm")).toBe("wxUnknown");
  });
});

describe("conditionGlyph", () => {
  it("returns a glyph per condition and ❓ for unknown", () => {
    expect(conditionGlyph("clear")).toBe("☀️");
    expect(conditionGlyph("rain")).toBe("🌧️");
    expect(conditionGlyph(null)).toBe("❓");
    expect(conditionGlyph("nope")).toBe("❓");
  });
});
