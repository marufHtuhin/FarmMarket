import { describe, expect, it } from "vitest";
import { BD_DISTRICTS, districtName, upazilasForDistrict } from "./bd-locations";

// The vendored dataset (bayeziddev/Bangladesh-geocode, MIT): 64 districts,
// 494 upazilas, English + Bangla names. These tests pin the shape the
// register form depends on.
describe("BD_DISTRICTS", () => {
  it("has exactly 64 districts with unique English names", () => {
    expect(BD_DISTRICTS).toHaveLength(64);
    const names = BD_DISTRICTS.map((d) => d.en);
    expect(new Set(names).size).toBe(64);
  });

  it("has 494 upazilas in total, every district has at least one", () => {
    const total = BD_DISTRICTS.reduce((n, d) => n + d.upazilas.length, 0);
    expect(total).toBe(494);
    for (const d of BD_DISTRICTS) {
      expect(d.upazilas.length, `${d.en} has upazilas`).toBeGreaterThan(0);
      const names = d.upazilas.map((u) => u.en);
      expect(new Set(names).size, `${d.en} upazila names unique`).toBe(names.length);
    }
  });

  it("has English and Bangla names everywhere", () => {
    for (const d of BD_DISTRICTS) {
      expect(d.en).not.toBe("");
      expect(d.bn).not.toBe("");
      for (const u of d.upazilas) {
        expect(u.en).not.toBe("");
        expect(u.bn).not.toBe("");
      }
    }
  });

  it("uses the app's hub/district spellings (2018 official renames)", () => {
    const names = BD_DISTRICTS.map((d) => d.en);
    for (const hub of ["Dhaka", "Chattogram", "Rajshahi", "Khulna", "Sylhet"]) {
      expect(names).toContain(hub);
    }
    expect(names).toContain("Barishal");
    expect(names).toContain("Cumilla");
    expect(names).not.toContain("Barisal");
    expect(names).not.toContain("Comilla");
  });

  it("is sorted alphabetically by English name", () => {
    const names = BD_DISTRICTS.map((d) => d.en);
    expect(names).toEqual([...names].sort());
  });
});

describe("upazilasForDistrict", () => {
  it("returns Dhaka's upazilas including Savar", () => {
    const names = upazilasForDistrict("Dhaka").map((u) => u.en);
    expect(names).toContain("Savar");
    expect(names).toContain("Dhamrai");
    expect(names.length).toBe(5);
  });

  it("returns an empty list for an unknown district", () => {
    expect(upazilasForDistrict("Nowhere")).toEqual([]);
  });
});

describe("districtName", () => {
  it("returns the Bangla name in bn mode and English in en mode", () => {
    expect(districtName("Dhaka", "bn")).toBe("ঢাকা");
    expect(districtName("Dhaka", "en")).toBe("Dhaka");
  });

  it("falls back to the input for an unknown district", () => {
    expect(districtName("Nowhere", "bn")).toBe("Nowhere");
  });
});
