import { useLang } from "../../i18n/LanguageContext";

export function LanguageToggle() {
  const { lang, setLang } = useLang();
  return (
    <div className="flex rounded-full border border-line bg-white p-0.5 text-[13px] font-bold" role="group" aria-label="Language">
      <button
        type="button"
        onClick={() => setLang("bn")}
        aria-pressed={lang === "bn"}
        className={`rounded-full px-3 py-1.5 transition ${lang === "bn" ? "bg-forest text-white" : "text-muted hover:text-ink"}`}
      >
        বাংলা
      </button>
      <button
        type="button"
        onClick={() => setLang("en")}
        aria-pressed={lang === "en"}
        className={`rounded-full px-3 py-1.5 transition ${lang === "en" ? "bg-forest text-white" : "text-muted hover:text-ink"}`}
      >
        EN
      </button>
    </div>
  );
}

/**
 * Compact logo for the app topbar: on narrow phones the "FarmMarket"
 * wordmark would push the user menu past the viewport edge (measured
 * scrollWidth 414px at a 390px viewport), so only the icon shows below
 * 420px. The sidebar / public header / footer keep the full wordmark.
 */
export function Logo({ light = false, compact = false }: { light?: boolean; compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <img src="/icon.svg" alt="" className="h-9 w-9 rounded-xl" />
      <span
        className={`font-display text-xl font-extrabold tracking-tight ${light ? "text-white" : "text-forest"} ${
          compact ? "hidden min-[420px]:inline" : ""
        }`}
      >
        Farm<span className="text-leaf">Market</span>
      </span>
    </span>
  );
}
