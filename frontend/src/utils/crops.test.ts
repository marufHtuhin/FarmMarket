import { describe, expect, it } from "vitest";
import { cropCat, filterProducts, paginate, productPhoto } from "../utils/crops";

const PRODUCTS = [
  { id: 1, name: "Tomato", district: "Dhaka", price_per_unit: 38, created_at: "2026-11-10T00:00:00Z" },
  { id: 2, name: "Potato", district: "Rajshahi", price_per_unit: 28, created_at: "2026-11-12T00:00:00Z" },
  { id: 3, name: "Mango", district: "Rajshahi", price_per_unit: 120, created_at: "2026-11-11T00:00:00Z" },
  { id: 4, name: "Rice", district: "Sylhet", price_per_unit: 65, created_at: "2026-11-09T00:00:00Z" },
];

describe("cropCat", () => {
  it("classifies fruit, grain and vegetables", () => {
    expect(cropCat("Mango")).toBe("fruit");
    expect(cropCat("Banana")).toBe("fruit");
    expect(cropCat("Rice")).toBe("grain");
    expect(cropCat("Tomato")).toBe("veg");
    expect(cropCat("Jute")).toBe("other");
  });
});

describe("productPhoto", () => {
  it("returns the verified Unsplash URL for known crops and null otherwise", () => {
    expect(productPhoto("Tomato")).toContain("1592924357228-91a4daadcfea");
    expect(productPhoto("Brinjal")).toContain("1683543122945-513029986574");
    expect(productPhoto("Dragonfruit")).toBeNull();
  });
});

describe("filterProducts", () => {
  it("filters by search text (case-insensitive)", () => {
    expect(filterProducts(PRODUCTS, { search: "tom" })).toHaveLength(1);
    expect(filterProducts(PRODUCTS, { search: "TOMATO" })[0].id).toBe(1);
  });

  it("filters by district and category together", () => {
    const out = filterProducts(PRODUCTS, { district: "rajshahi", category: "fruit" });
    expect(out.map((p) => p.id)).toEqual([3]);
  });

  it("sorts by price ascending and descending", () => {
    expect(filterProducts(PRODUCTS, { sort: "price-asc" }).map((p) => p.id)).toEqual([2, 1, 4, 3]);
    expect(filterProducts(PRODUCTS, { sort: "price-desc" }).map((p) => p.id)).toEqual([3, 4, 1, 2]);
  });

  it("sorts newest first by default", () => {
    expect(filterProducts(PRODUCTS, {}).map((p) => p.id)).toEqual([2, 3, 1, 4]);
  });
});

describe("paginate", () => {
  it("slices pages and clamps out-of-range pages", () => {
    const { pageItems, totalPages } = paginate(PRODUCTS, 2, 3);
    expect(totalPages).toBe(2);
    expect(pageItems).toHaveLength(1);
    expect(paginate(PRODUCTS, 99, 3).pageItems).toHaveLength(1);
  });
});
