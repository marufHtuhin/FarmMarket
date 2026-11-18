import { useLang } from "../i18n/LanguageContext";
import { timeAgo } from "../utils/format";
import { Badge } from "./ui/misc";

export type PriceLabel = "real" | "demo";

/** REAL (green) vs DEMO (amber) badge. Every price on the site shows one. */
export function PriceLabelBadge({ label }: { label: PriceLabel | string | undefined }) {
  const { t } = useLang();
  if (label === "real") return <Badge tone="green">{t("priceReal")}</Badge>;
  // Unknown / missing label is shown as DEMO: never claim a price is real
  // without the backend saying so.
  return <Badge tone="amber">{t("priceDemo")}</Badge>;
}

/** Warning chip for a real price older than 48h. Renders nothing when fresh. */
export function StaleWarning({ stale }: { stale?: boolean }) {
  const { t } = useLang();
  if (!stale) return null;
  return <Badge tone="red">⚠ {t("priceStale")}</Badge>;
}

/** One line of provenance under a price. The market day (observed_on) and the
 *  entry time (updatedAt/ingested_at) are DIFFERENT things — a price observed
 *  on Sunday may only have been entered on Wednesday — so when both are known
 *  each is labelled explicitly ("Market day: … · Entered: … ago") instead of
 *  the old ambiguous "Updated … ago · <date>". PriceRecord cards have no
 *  market day, so they keep the plain "Updated … ago" form. */
export function PriceProvenance({
  source,
  updatedAt,
  observedOn,
}: {
  source?: string | null;
  updatedAt?: string | null;
  observedOn?: string | null;
}) {
  const { t, fmtDate } = useLang();
  const ago = timeAgo(updatedAt || observedOn, t);
  const enteredAgo = updatedAt ? timeAgo(updatedAt, t) : "";
  const parts: string[] = [];
  if (source) parts.push(`${t("source")}: ${source}`);
  if (observedOn) {
    parts.push(`${t("marketDay")}: ${fmtDate(observedOn)}`);
    if (enteredAgo) parts.push(t("enteredAgo", { ago: enteredAgo }));
  } else if (ago) {
    parts.push(t("updatedAgo", { ago }));
  }
  if (!parts.length) return null;
  return <p className="text-xs leading-relaxed text-[#6e7e72]">{parts.join(" · ")}</p>;
}
