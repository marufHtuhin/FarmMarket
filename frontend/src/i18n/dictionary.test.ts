import { describe, expect, it } from "vitest";
import { dictionaries } from "./LanguageContext";

describe("i18n dictionaries", () => {
  it("bn and en have identical key sets", () => {
    const bnKeys = Object.keys(dictionaries.bn).sort();
    const enKeys = Object.keys(dictionaries.en).sort();
    expect(bnKeys).toEqual(enKeys);
  });

  it("has the ported legacy keys plus new keys", () => {
    expect(Object.keys(dictionaries.bn).length).toBeGreaterThan(400);
    expect(dictionaries.bn.brandTag).toBe("কৃষকের ন্যায্য বাজার");
    expect(dictionaries.en.brandTag).toBe("Fair market for farmers");
    expect(dictionaries.bn.ti_forecastTitle).toBe("দামের পূর্বাভাস");
    expect(dictionaries.bn.navAssistant).toBe("কৃষি বন্ধু");
  });

  it("has no empty translations", () => {
    for (const [lang, dict] of Object.entries(dictionaries)) {
      for (const [key, value] of Object.entries(dict)) {
        expect(value, `${lang}.${key} must not be empty`).not.toBe("");
      }
    }
  });
});
