import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp } from "lucide-react";
import { forecastApi, pricesApi, type PriceRecord } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { apiErrorMessage, unitLabel } from "../utils/format";
import { FALLBACK_HUBS } from "../utils/geo";
import { Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { PriceLabelBadge, PriceProvenance, StaleWarning } from "../components/PriceBadge";
import { Select } from "../components/ui/fields";
import { ForecastChart, PriceHistoryChart } from "../components/charts";
import { HubsMap } from "../components/HubsMap";

export function PricesPage() {
  const { t, fmtNum, fmtDate, lang } = useLang();
  const [hub, setHub] = useState("dhaka");
  const [crop, setCrop] = useState("tomato");
  const [horizon, setHorizon] = useState(8);

  const pricesQ = useQuery({ queryKey: ["prices"], queryFn: () => pricesApi.list() });
  const latestQ = useQuery({ queryKey: ["prices-latest"], queryFn: () => pricesApi.latest(), retry: false });
  const hubsQ = useQuery({ queryKey: ["forecast-hubs"], queryFn: forecastApi.hubs, retry: false });
  // Trend chart reads the stored PriceObservation series for the SAME hub +
  // crop as the forecast above — one pair of selects drives both, so no
  // redundant product selector. (It used to read PriceRecord: one seeded
  // row per product, i.e. a one-point "trend".)
  const historyQ = useQuery({
    queryKey: ["price-history", hub, crop],
    queryFn: () => pricesApi.history(hub, crop),
    retry: false,
  });
  const forecastQ = useQuery({
    queryKey: ["forecast", hub, crop, horizon],
    queryFn: () => forecastApi.sklearn(hub, crop, horizon),
    retry: false,
  });

  const hubs = hubsQ.data?.hubs || FALLBACK_HUBS;
  const crops = hubsQ.data?.crops || [
    { id: "tomato", name: "Tomato" },
    { id: "potato", name: "Potato" },
    { id: "onion", name: "Onion" },
    { id: "banana", name: "Banana" },
    { id: "maize", name: "Maize" },
  ];

  const historyPoints = historyQ.data?.points || [];
  const chartData = useMemo(
    () =>
      historyPoints.map((p) => ({
        date: fmtDate(p.observed_on),
        price: Number(p.price),
      })),
    [historyPoints, fmtDate]
  );
  const historyHasReal = historyPoints.some((p) => !p.is_synthetic);
  const historyHasSynthetic = historyPoints.some((p) => p.is_synthetic);

  const latestHubPrice = (hubId: string) => {
    const cands = (pricesQ.data || []).filter((p) => {
      const hay = `${p.district} ${p.market_name || ""}`.toLowerCase();
      return hay.includes(hubId) || (hubId === "chattogram" && hay.includes("chittagong"));
    });
    if (!cands.length) return null;
    cands.sort((a, b) => new Date(b.recorded_at || 0).getTime() - new Date(a.recorded_at || 0).getTime());
    return cands[0];
  };

  const fc = forecastQ.data;

  return (
    <div className="space-y-8">
      <PageHeader title={t("marketPrices")} sub={t("priceSub")} />
      <div className="rounded-2xl border border-[#f4e4bf] bg-[#fff8e9] px-4 py-3 text-[13px] text-[#80632d]">
        {t("priceNotice")}
      </div>

      {/* Latest price per hub x crop, with source + freshness */}
      <Card className="p-5">
        <h2 className="font-display text-lg font-extrabold text-forest">{t("latestHubPrices")}</h2>
        <p className="mt-1 text-sm text-muted">{t("latestHubPricesHint")}</p>
        {latestQ.isLoading ? (
          <Spinner />
        ) : latestQ.isError ? (
          <ErrorState message={apiErrorMessage(latestQ.error)} onRetry={() => latestQ.refetch()} />
        ) : (latestQ.data?.prices || []).length === 0 ? (
          <EmptyState title={t("noLatestPrices")} />
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-[13px]">
              <thead>
                <tr>
                  <th className="border-b border-line px-2 py-2 text-left font-bold">{t("fieldHub")}</th>
                  <th className="border-b border-line px-2 py-2 text-left font-bold">{t("fieldCrop")}</th>
                  <th className="border-b border-line px-2 py-2 text-left font-bold">{t("fieldPrice")}</th>
                  <th className="border-b border-line px-2 py-2 text-left font-bold">{t("source")}</th>
                  <th className="border-b border-line px-2 py-2 text-left font-bold">{t("lastUpdated")}</th>
                </tr>
              </thead>
              <tbody>
                {(latestQ.data?.prices || []).map((p) => (
                  <tr key={`${p.hub}-${p.crop}`}>
                    <td className="border-b border-line px-2 py-2 font-bold">{p.hub}</td>
                    <td className="border-b border-line px-2 py-2">{p.crop}</td>
                    <td className="whitespace-nowrap border-b border-line px-2 py-2 font-bold">
                      ৳{fmtNum(p.price)}/{unitLabel(p.unit, lang)}
                    </td>
                    <td className="border-b border-line px-2 py-2">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <PriceLabelBadge label={p.label} />
                        <StaleWarning stale={p.stale} />
                      </span>
                      <span className="mt-1 block text-xs text-muted">
                        {p.source}
                        {p.note ? ` — ${p.note}` : ""}
                      </span>
                    </td>
                    <td className="whitespace-nowrap border-b border-line px-2 py-2">
                      <PriceProvenance source={null} updatedAt={p.ingested_at} observedOn={p.observed_on} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Forecast */}
      <Card className="p-5">
        <h2 className="flex items-center gap-2 font-display text-lg font-extrabold text-forest">
          <TrendingUp className="h-5 w-5 text-leaf" /> {t("forecastSection")}
        </h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <Select value={hub} onChange={(e) => setHub(e.target.value)} aria-label={t("selectHub")}>
            {hubs.map((h) => (
              <option key={h.id} value={h.id}>
                {h.name}, {h.country}
              </option>
            ))}
          </Select>
          <Select value={crop} onChange={(e) => setCrop(e.target.value)} aria-label={t("selectCropLabel")}>
            {crops.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
          <Select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} aria-label={t("horizonWeeks")}>
            {[4, 8, 12, 26].map((h) => (
              <option key={h} value={h}>
                {h} {t("ti_week")}
              </option>
            ))}
          </Select>
        </div>
        {forecastQ.isLoading && <Spinner label={t("ti_fitting")} />}
        {forecastQ.isError && (
          <div className="mt-4">
            <ErrorState message={apiErrorMessage(forecastQ.error)} onRetry={() => forecastQ.refetch()} />
          </div>
        )}
        {fc && (
          <div className="mt-4">
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              <div className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
                {t("ti_modelUsed")}
                <b className="block text-base font-extrabold text-forest">{fc.model || "sklearn"}</b>
              </div>
              <div className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
                {t("ti_signal")}
                <b className="block text-base font-extrabold text-forest">
                  {fc.signal.direction} ({fc.signal.expected_change_pct}%)
                </b>
              </div>
              <div className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
                {t("ti_reliable")}
                <b className="block text-base font-extrabold text-forest">
                  {fc.reliable ? t("ti_reliableYes") : t("ti_reliableNo")}
                </b>
              </div>
              <div className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
                {t("ti_historyPoints")}
                <b className="block text-base font-extrabold text-forest">{fc.series.points}</b>
              </div>
            </div>
            {!fc.reliable && (
              <p className="mt-3 rounded-2xl border border-[#f4e4bf] bg-[#fff8e9] px-4 py-3 text-[13px] text-[#80632d]">
                {t("unreliableNote")}
              </p>
            )}
            <div className="mt-4">
              <ForecastChart history={fc.history} forecast={fc.forecast} />
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[420px] border-collapse text-[13px]">
                <thead>
                  <tr>
                    <th className="border-b border-line px-2 py-2 text-left font-bold">{t("ti_week")}</th>
                    <th className="border-b border-line px-2 py-2 text-left font-bold">{t("ti_forecast")}</th>
                    <th className="border-b border-line px-2 py-2 text-left font-bold">{t("ti_low")}</th>
                    <th className="border-b border-line px-2 py-2 text-left font-bold">{t("ti_high")}</th>
                  </tr>
                </thead>
                <tbody>
                  {fc.forecast.map((p) => (
                    <tr key={p.ds}>
                      <td className="border-b border-line px-2 py-2">{p.ds}</td>
                      <td className="border-b border-line px-2 py-2 font-bold">৳{fmtNum(p.yhat)}</td>
                      <td className="border-b border-line px-2 py-2">৳{fmtNum(p.lower)}</td>
                      <td className="border-b border-line px-2 py-2">৳{fmtNum(p.upper)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {(fc.series.sources || []).length > 0 && (
              <p className="mt-2 text-[13px] text-muted">
                {t("ti_sources")}: {fc.series.sources!.join(", ")}
              </p>
            )}
          </div>
        )}
      </Card>

      {/* Price history chart — the stored series for the hub + crop chosen
          in the forecast section above (no separate selector). */}
      <Card className="p-5">
        <h2 className="font-display text-lg font-extrabold text-forest">{t("priceChartTitle")}</h2>
        <p className="mt-1 text-sm text-muted">{t("priceChartHint")}</p>
        {historyQ.isLoading ? (
          <Spinner />
        ) : historyQ.isError ? (
          <ErrorState message={apiErrorMessage(historyQ.error)} onRetry={() => historyQ.refetch()} />
        ) : historyPoints.length === 0 ? (
          <EmptyState title={t("priceChartEmpty")} />
        ) : (
          <>
            <div className="mt-4 flex flex-wrap items-center gap-1.5">
              {historyHasReal && <PriceLabelBadge label="real" />}
              {historyHasSynthetic && <PriceLabelBadge label="demo" />}
              <span className="text-xs text-muted">
                {t("priceHistoryRange", {
                  count: historyPoints.length,
                  from: fmtDate(historyPoints[0].observed_on),
                  to: fmtDate(historyPoints[historyPoints.length - 1].observed_on),
                })}
              </span>
            </div>
            <div className="mt-3">
              <PriceHistoryChart data={chartData} />
            </div>
            <p className="mt-3 text-[13px] text-muted">{t("priceHistoryAutoHint")}</p>
          </>
        )}
      </Card>

      {/* Hubs map */}
      <Card className="p-5">
        <h2 className="font-display text-lg font-extrabold text-forest">{t("hubsMap")}</h2>
        <p className="mt-1 text-sm text-muted">{t("hubsMapHint")}</p>
        <div className="mt-4">
          <HubsMap
            hubs={hubs}
            popupText={(h) => {
              const p = latestHubPrice(h.id);
              return p
                ? `${t("latestPrice")}: ${p.product_name} — ৳${fmtNum(p.price_per_unit)}/${unitLabel(p.unit, lang)}`
                : t("noPriceData");
            }}
          />
        </div>
      </Card>

      {/* Price records */}
      {pricesQ.isLoading ? (
        <Spinner label={t("loading")} />
      ) : pricesQ.isError ? (
        <ErrorState message={apiErrorMessage(pricesQ.error)} onRetry={() => pricesQ.refetch()} />
      ) : (pricesQ.data || []).length === 0 ? (
        <EmptyState title={t("noPrices")} />
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {(pricesQ.data || []).map((p) => (
            <Card key={p.id} className="p-5 transition hover:-translate-y-0.5 hover:shadow-lift">
              <div className="flex flex-wrap items-center gap-1.5">
                <PriceLabelBadge label={p.label} />
                <StaleWarning stale={p.stale} />
              </div>
              <p className="mt-2 text-xs text-muted">
                📍 {p.market_name || p.district} · {p.district}
              </p>
              <h3 className="my-2 font-display text-xl font-extrabold">{p.product_name}</h3>
              <div className="my-2 font-display text-[30px] font-extrabold text-leaf">
                ৳{fmtNum(p.price_per_unit)} <small className="text-sm font-bold">/{unitLabel(p.unit, lang)}</small>
              </div>
              <PriceProvenance source={p.source} updatedAt={p.recorded_at} />
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
