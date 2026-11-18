import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CloudSun, Droplets, Umbrella, Wind } from "lucide-react";
import { forecastApi, weatherApi, type WeatherDay, type WeatherResponse } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { apiErrorMessage } from "../utils/format";
import { FALLBACK_HUBS } from "../utils/geo";
import { fetchDirectWeather } from "../utils/openmeteo";
import { conditionGlyph, conditionLabelKey } from "../utils/weather";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { Select } from "../components/ui/fields";
import { WeatherChart } from "../components/charts";

function DayRow({ day, showChance }: { day: WeatherDay; showChance?: boolean }) {
  const { t, fmtNum, fmtDate } = useLang();
  return (
    <div className="flex items-center gap-2 border-b border-line px-1 py-2.5 text-sm last:border-0 sm:gap-3">
      <span className="w-20 shrink-0 font-bold text-forest sm:w-24">{fmtDate(day.date)}</span>
      <span className="flex min-w-0 flex-1 items-center gap-1.5 truncate">
        <span aria-hidden>{conditionGlyph(day.condition)}</span>
        <span className="truncate">{t(conditionLabelKey(day.condition))}</span>
      </span>
      <span className="shrink-0 text-muted">
        {day.temp_min_c != null ? `${fmtNum(day.temp_min_c, 1)}°` : "—"}
        {" – "}
        {day.temp_max_c != null ? `${fmtNum(day.temp_max_c, 1)}°C` : "—"}
      </span>
      <span className="flex w-16 shrink-0 items-center justify-end gap-1 text-muted">
        <Umbrella className="h-3.5 w-3.5" />
        {day.rain_mm != null ? `${fmtNum(day.rain_mm, 1)}` : "—"}
      </span>
      {showChance && (
        // Rain-chance column hidden on narrow phones: the five fixed columns
        // overflowed the card at 360px (measured scrollWidth 388px).
        <span className="hidden w-12 shrink-0 text-right text-muted min-[420px]:block">
          {day.rain_probability_pct != null ? `${fmtNum(day.rain_probability_pct, 0)}%` : "—"}
        </span>
      )}
    </div>
  );
}

export function WeatherPage() {
  const { t, fmtNum, fmtDateTime, lang } = useLang();
  const [hub, setHub] = useState("dhaka");

  const hubsQ = useQuery({ queryKey: ["forecast-hubs"], queryFn: forecastApi.hubs, retry: false });
  const hubs = hubsQ.data?.hubs || FALLBACK_HUBS;
  const wxQ = useQuery({
    queryKey: ["weather", hub],
    queryFn: async () => {
      // Backend first (10-minute server cache). If the server cannot
      // reach Open-Meteo — e.g. the host's shared IP hit Open-Meteo's
      // free per-IP rate limit — fall back to a direct browser call,
      // which comes from the visitor's own IP (utils/openmeteo.ts).
      let backend: WeatherResponse | null = null;
      let backendError: unknown = null;
      try {
        backend = await weatherApi.get(hub);
        if (backend.available) return backend;
      } catch (err) {
        backendError = err;
        // fall through to the direct call
      }
      const info = hubs.find((h) => h.id === hub);
      if (info) {
        const direct = await fetchDirectWeather({
          id: info.id,
          name: info.name,
          lat: info.lat,
          lon: info.lon,
        });
        if (direct) return direct;
      }
      // Both paths failed: keep the backend's labelled unavailable
      // payload when we have one, so the page shows "unavailable",
      // never a crash. Otherwise rethrow the backend's own error so
      // the error state still names the real cause.
      if (backend) return backend;
      if (backendError) throw backendError;
      throw new Error("weather unavailable");
    },
    retry: false,
    // The backend caches for 10 minutes; refetching sooner would just
    // return the same payload.
    staleTime: 10 * 60 * 1000,
  });

  const wx = wxQ.data;
  const pastUnavailable = (wx?.notes || []).includes("past_unavailable");

  return (
    <div className="space-y-8">
      <PageHeader title={t("weatherTitle")} sub={t("weatherSub")} />

      <div className="max-w-xs">
        <Select value={hub} onChange={(e) => setHub(e.target.value)} aria-label={t("selectHub")}>
          {hubs.map((h) => (
            <option key={h.id} value={h.id}>
              {h.name}, {h.country}
            </option>
          ))}
        </Select>
      </div>

      {wxQ.isLoading && <Spinner label={t("loading")} />}
      {wxQ.isError && (
        <ErrorState message={apiErrorMessage(wxQ.error)} onRetry={() => wxQ.refetch()} />
      )}

      {/* Labelled unavailable state: Open-Meteo unreachable. No weather
          values are shown here — nothing is estimated or filled in. */}
      {wx && !wx.available && (
        <Card className="p-5">
          <h2 className="font-display text-lg font-extrabold text-forest">{t("weatherUnavailable")}</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">{wx.note || t("weatherUnavailableNote")}</p>
          <p className="mt-2 text-xs text-muted">
            {t("weatherSource")} · {t("lastUpdated")}: {fmtDateTime(wx.fetched_at)}
          </p>
          <div className="mt-4">
            <Button onClick={() => wxQ.refetch()}>{t("retry")}</Button>
          </div>
        </Card>
      )}

      {wx && wx.available && wx.current && (
        <>
          {/* Current conditions */}
          <Card className="p-5">
            <h2 className="flex items-center gap-2 font-display text-lg font-extrabold text-forest">
              <CloudSun className="h-5 w-5 text-leaf" /> {t("weatherCurrent")}
              <span className="text-sm font-bold text-muted">— {wx.hub_name}</span>
            </h2>
            <div className="mt-4 flex flex-wrap items-center gap-x-8 gap-y-3">
              <div>
                <span className="text-4xl" aria-hidden>
                  {conditionGlyph(wx.current.condition)}
                </span>
                <span className="ml-2 font-display text-[40px] font-extrabold leading-none text-forest">
                  {wx.current.temperature_c != null ? `${fmtNum(wx.current.temperature_c, 1)}°C` : "—"}
                </span>
                <p className="mt-1 text-sm font-bold text-muted">
                  {t(conditionLabelKey(wx.current.condition))}
                </p>
              </div>
              <div className="grid grid-cols-3 gap-2.5 text-[13px] text-muted">
                <div className="rounded-2xl bg-mint px-3.5 py-3">
                  <span className="flex items-center gap-1">
                    <Droplets className="h-3.5 w-3.5" /> {t("wxHumidity")}
                  </span>
                  <b className="block text-base font-extrabold text-forest">
                    {wx.current.humidity_pct != null ? `${fmtNum(wx.current.humidity_pct, 0)}%` : "—"}
                  </b>
                </div>
                <div className="rounded-2xl bg-mint px-3.5 py-3">
                  <span className="flex items-center gap-1">
                    <Wind className="h-3.5 w-3.5" /> {t("wxWind")}
                  </span>
                  <b className="block text-base font-extrabold text-forest">
                    {wx.current.wind_speed_kmh != null
                      ? `${fmtNum(wx.current.wind_speed_kmh, 1)} km/h`
                      : "—"}
                  </b>
                </div>
                <div className="rounded-2xl bg-mint px-3.5 py-3">
                  <span className="flex items-center gap-1">
                    <Umbrella className="h-3.5 w-3.5" /> {t("wxPrecipitation")}
                  </span>
                  <b className="block text-base font-extrabold text-forest">
                    {wx.current.precipitation_mm != null
                      ? `${fmtNum(wx.current.precipitation_mm, 1)} mm`
                      : "—"}
                  </b>
                </div>
              </div>
            </div>
            <p className="mt-3 text-xs text-muted">
              {t("wxObservedAt")}: {wx.current.time ? fmtDateTime(wx.current.time) : "—"}
            </p>
          </Card>

          {/* Temperature chart: past + forecast */}
          {(wx.past?.length || wx.forecast?.length) && (
            <Card className="p-5">
              <h2 className="font-display text-lg font-extrabold text-forest">{t("wxChartTitle")}</h2>
              <div className="mt-3">
                <WeatherChart past={wx.past || []} forecast={wx.forecast || []} />
              </div>
            </Card>
          )}

          {pastUnavailable && (
            <div className="rounded-2xl border border-[#f4e4bf] bg-[#fff8e9] px-4 py-3 text-[13px] text-[#80632d]">
              {t("wxPastUnavailable")}
            </div>
          )}

          {/* Past 7 days */}
          <Card className="p-5">
            <h2 className="font-display text-lg font-extrabold text-forest">{t("weatherPast")}</h2>
            {(wx.past || []).length === 0 ? (
              <div className="mt-3">
                <EmptyState title={t("weatherUnavailable")} />
              </div>
            ) : (
              <div className="mt-2">
                <div className="flex gap-2 px-1 pb-1 text-xs font-bold text-muted sm:gap-3">
                  <span className="w-20 shrink-0 sm:w-24">{t("wxDate")}</span>
                  <span className="flex-1" />
                  <span className="shrink-0">
                    {t("wxTempMin")} – {t("wxTempMax")}
                  </span>
                  <span className="w-16 shrink-0 text-right">{t("wxRain")} (mm)</span>
                </div>
                {(wx.past || []).map((d) => (
                  <DayRow key={d.date} day={d} />
                ))}
              </div>
            )}
          </Card>

          {/* Forecast: today + next 7 days */}
          <Card className="p-5">
            <h2 className="font-display text-lg font-extrabold text-forest">{t("weatherForecast")}</h2>
            {(wx.forecast || []).length === 0 ? (
              <div className="mt-3">
                <EmptyState title={t("weatherUnavailable")} />
              </div>
            ) : (
              <div className="mt-2">
                <div className="flex gap-2 px-1 pb-1 text-xs font-bold text-muted sm:gap-3">
                  <span className="w-20 shrink-0 sm:w-24">{t("wxDate")}</span>
                  <span className="flex-1" />
                  <span className="shrink-0">
                    {t("wxTempMin")} – {t("wxTempMax")}
                  </span>
                  <span className="w-16 shrink-0 text-right">{t("wxRain")} (mm)</span>
                  {/* Short label: "Rain chance" (~70px) overflows its w-12
                      column; "Rain %" fits in both languages. */}
                  <span className="hidden w-12 shrink-0 text-right min-[420px]:block">{t("wxRain")} %</span>
                </div>
                {(wx.forecast || []).map((d, i) => (
                  <div key={d.date} className={i === 0 ? "rounded-xl bg-mint/60" : undefined}>
                    <DayRow day={d} showChance />
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Source + fetch time on every view: no value is shown without
              its provenance. */}
          <p className="text-xs text-muted" lang={lang === "bn" ? "en" : undefined}>
            {t("weatherSource")} · {t("lastUpdated")}: {fmtDateTime(wx.fetched_at)}
            {wx.direct ? ` · ${t("wxDirect")}` : ""}
          </p>
        </>
      )}
    </div>
  );
}
