import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Handshake } from "lucide-react";
import { matchesApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { apiErrorMessage, unitLabel } from "../utils/format";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";

export function MatchesPage() {
  const { t, fmtNum, lang } = useLang();
  const q = useQuery({ queryKey: ["matches"], queryFn: matchesApi.list });

  return (
    <div>
      <PageHeader title={t("matchesTitle")} sub={t("matchSub")} />
      <div className="mb-5 rounded-2xl border border-[#f4e4bf] bg-[#fff8e9] px-4 py-3 text-[13px] text-[#80632d]">
        {t("matchNotice")}
      </div>
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && q.data.length === 0 && (
        <EmptyState icon={<Handshake className="h-10 w-10 text-leaf" />} title={t("noMatches")} />
      )}
      {q.isSuccess && q.data.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {q.data.map((m, i) => (
            <Card key={`${m.demand_id}-${m.product_id}-${i}`} className="p-5 transition hover:-translate-y-0.5 hover:shadow-lift">
              <div className="flex items-start justify-between gap-2.5">
                <span className="rounded-full bg-[#e8f6ec] px-2.5 py-1 text-[11px] font-bold text-forest">
                  {t("smartMatches")}
                </span>
                <span className="font-display text-[32px] font-extrabold leading-none text-leaf">{fmtNum(m.score)}%</span>
              </div>
              <h3 className="my-2 font-display text-xl font-extrabold">{m.product_name}</h3>
              <p className="text-xs text-muted">
                {m.farmer_name} → {m.buyer_name} · {m.district}
              </p>
              <div className="my-3 h-2 overflow-hidden rounded-full bg-cream">
                <div className="h-full rounded-full bg-leaf" style={{ width: `${Math.max(0, Math.min(100, m.score))}%` }} />
              </div>
              <div className="grid grid-cols-2 gap-2 text-[13px] text-muted">
                <p>
                  {t("quantityLabel")}: <b className="text-ink">{fmtNum(m.quantity)} {unitLabel(m.unit, lang)}</b>
                </p>
                <p>
                  {t("targetQuantity")}: <b className="text-ink">{fmtNum(m.required_quantity)} {unitLabel(m.unit, lang)}</b>
                </p>
                <p>
                  {t("farmerPrice")}: <b className="text-ink">৳{fmtNum(m.farmer_price)}</b>
                </p>
                <p>
                  {t("budget")}: <b className="text-ink">৳{fmtNum(m.target_price)}</b>
                </p>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-[#6e7e72]">
                <b>{t("matchReasons")}:</b> {m.reasons.join(" · ")}
              </p>
              <Link to={`/marketplace/${m.product_id}`} className="mt-4 block">
                <Button variant="secondary" size="sm" className="w-full">
                  {t("viewProduct")}
                </Button>
              </Link>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
