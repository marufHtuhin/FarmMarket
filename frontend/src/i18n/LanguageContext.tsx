import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { legacyBn, legacyEn } from "./legacy";
import { newBn, newEn } from "./dictionary";

export const dictionaries = {
  bn: { ...legacyBn, ...newBn },
  en: { ...legacyEn, ...newEn },
} as const;

export type Lang = keyof typeof dictionaries;
export type DictKey = keyof (typeof dictionaries)["bn"];

export function dictKeyCounts() {
  return { bn: Object.keys(dictionaries.bn).length, en: Object.keys(dictionaries.en).length };
}

interface LangCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  fmtNum: (n: number | string | null | undefined, digits?: number) => string;
  fmtDate: (d: string | Date | null | undefined) => string;
  fmtDateTime: (d: string | Date | null | undefined) => string;
  locale: string;
}

const LanguageContext = createContext<LangCtx | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const saved = localStorage.getItem("fm_lang");
    return saved === "en" ? "en" : "bn";
  });

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    localStorage.setItem("fm_lang", l);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const dict = dictionaries[lang] as Record<string, string>;
      let s = dict[key] ?? (dictionaries.en as Record<string, string>)[key] ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
      }
      return s;
    },
    [lang]
  );

  const locale = lang === "bn" ? "bn-BD" : "en-US";

  const fmtNum = useCallback(
    (n: number | string | null | undefined, digits = 2) => {
      const num = Number(n ?? 0);
      if (Number.isNaN(num)) return "—";
      return num.toLocaleString(locale, { maximumFractionDigits: digits });
    },
    [locale]
  );

  const fmtDate = useCallback(
    (d: string | Date | null | undefined) => {
      if (!d) return "—";
      const dt = d instanceof Date ? d : new Date(d);
      if (Number.isNaN(dt.getTime())) return String(d);
      return dt.toLocaleDateString(locale);
    },
    [locale]
  );

  const fmtDateTime = useCallback(
    (d: string | Date | null | undefined) => {
      if (!d) return "—";
      const dt = d instanceof Date ? d : new Date(d);
      if (Number.isNaN(dt.getTime())) return String(d);
      return dt.toLocaleString(locale);
    },
    [locale]
  );

  const value = useMemo(
    () => ({ lang, setLang, t, fmtNum, fmtDate, fmtDateTime, locale }),
    [lang, setLang, t, fmtNum, fmtDate, fmtDateTime, locale]
  );
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLang(): LangCtx {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLang must be used within LanguageProvider");
  return ctx;
}
