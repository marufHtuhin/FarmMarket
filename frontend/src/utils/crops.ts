// Verified Unsplash photo IDs ported from frontend-legacy/app.js (CROP_PHOTOS).
const U = (id: string) => `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=800&q=70`;

export const CROP_PHOTOS: Array<[RegExp, string]> = [
  [/tomato|টমেটো/, "1592924357228-91a4daadcfea"],
  [/potato|আলু/, "1518977676601-b53f82aba655"],
  [/onion|পেঁয়াজ|পেঁয়াজ/, "1508747703725-719777637510"],
  [/banana|কলা/, "1528825871115-3581a5387919"],
  [/mango|আম/, "1553279768-865429fa0078"],
  [/rice|চাল|ধান/, "1512058564366-18510be2db19"],
  [/brinjal|begun|eggplant|বেগুন/, "1683543122945-513029986574"],
  [/chilli|chili|মরিচ/, "1693664132330-d2c836d44378"],
  [/cauliflower|ফুলকপি/, "1784043437088-c86a43eb695d"],
  [/jute|পাট/, "1777332546462-1622ade436a6"],
];

export const HERO_PHOTO =
  "https://images.unsplash.com/photo-1631209121750-a9f656d28f46?auto=format&fit=crop&w=1200&q=70";

export function productPhoto(name: string | null | undefined): string | null {
  const x = String(name || "").toLowerCase();
  const f = CROP_PHOTOS.find(([re]) => re.test(x));
  return f ? U(f[1]) : null;
}

export function productEmoji(name: string | null | undefined): string {
  const x = String(name || "").toLowerCase();
  if (/tomato|টমেটো/.test(x)) return "🍅";
  if (/potato|আলু/.test(x)) return "🥔";
  if (/rice|চাল|ধান/.test(x)) return "🌾";
  if (/mango|আম/.test(x)) return "🥭";
  if (/banana|কলা/.test(x)) return "🍌";
  if (/onion|পেঁয়াজ|পেঁয়াজ/.test(x)) return "🧅";
  if (/chilli|chili|মরিচ/.test(x)) return "🌶️";
  if (/fish|মাছ/.test(x)) return "🐟";
  if (/brinjal|begun|eggplant|বেগুন/.test(x)) return "🍆";
  return "🥬";
}

export type CropCategory = "all" | "veg" | "fruit" | "grain" | "other";

export function cropCat(name: string | null | undefined): Exclude<CropCategory, "all"> {
  const x = String(name || "").toLowerCase();
  if (/banana|কলা|mango|আম|fruit|ফল/.test(x)) return "fruit";
  if (/rice|চাল|ধান|wheat|গম|maize|ভুট্টা|grain|শস্য/.test(x)) return "grain";
  if (/jute|পাট/.test(x)) return "other";
  return "veg";
}

export const CATEGORIES: Array<{ key: CropCategory; labelKey: string }> = [
  { key: "all", labelKey: "catAll" },
  { key: "veg", labelKey: "catVeg" },
  { key: "fruit", labelKey: "catFruit" },
  { key: "grain", labelKey: "catGrain" },
  { key: "other", labelKey: "catOther" },
];

export interface FilterableProduct {
  id: number;
  name: string;
  district?: string | null;
  price_per_unit: number;
  created_at?: string | null;
}

export interface ProductFilter {
  search?: string;
  district?: string;
  category?: CropCategory;
  sort?: "newest" | "price-asc" | "price-desc";
}

/** Pure, unit-testable marketplace filtering + sorting. */
export function filterProducts<T extends FilterableProduct>(products: T[], f: ProductFilter): T[] {
  const q = (f.search || "").trim().toLowerCase();
  const d = (f.district || "").trim().toLowerCase();
  const cat = f.category || "all";
  const out = products.filter((p) => {
    if (q && !p.name.toLowerCase().includes(q)) return false;
    if (d && !(p.district || "").toLowerCase().includes(d)) return false;
    if (cat !== "all" && cropCat(p.name) !== cat) return false;
    return true;
  });
  const sort = f.sort || "newest";
  if (sort === "price-asc") out.sort((a, b) => a.price_per_unit - b.price_per_unit);
  else if (sort === "price-desc") out.sort((a, b) => b.price_per_unit - a.price_per_unit);
  else
    out.sort((a, b) => {
      const da = a.created_at ? new Date(a.created_at).getTime() : 0;
      const db = b.created_at ? new Date(b.created_at).getTime() : 0;
      return db - da || b.id - a.id;
    });
  return out;
}

export function paginate<T>(items: T[], page: number, pageSize: number): { pageItems: T[]; totalPages: number } {
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  return {
    pageItems: items.slice((safePage - 1) * pageSize, safePage * pageSize),
    totalPages,
  };
}
