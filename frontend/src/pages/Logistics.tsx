import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { MapPin, Plus, Trash2, Truck } from "lucide-react";
import { logisticsApi, type LogisticsPlan, type LogisticsPlanIn } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage, apiStatus } from "../utils/format";
import { BD_LOCATIONS, DEFAULT_DEPOT } from "../utils/geo";
import { Button, Card, PageHeader } from "../components/ui/core";
import { Field, Input, Select } from "../components/ui/fields";
import { RouteMap, type RouteStopPoint } from "../components/RouteMap";

interface StopDraft {
  key: number;
  preset: string;
  lat: number;
  lon: number;
  load_kg: number;
  max_transit_min: string;
}

const DEFAULT_STOPS: StopDraft[] = [
  { key: 1, preset: "Gazipur", lat: 23.9999, lon: 90.4203, load_kg: 120, max_transit_min: "240" },
  { key: 2, preset: "Savar", lat: 23.8583, lon: 90.2629, load_kg: 200, max_transit_min: "" },
  { key: 3, preset: "Narayanganj", lat: 23.6238, lon: 90.5, load_kg: 150, max_transit_min: "" },
];

export function LogisticsPage() {
  const { t, fmtNum } = useLang();
  const { toast } = useToast();
  const [depotPreset, setDepotPreset] = useState("Dhaka");
  const [depot, setDepot] = useState(DEFAULT_DEPOT);
  const [stops, setStops] = useState<StopDraft[]>(DEFAULT_STOPS);
  const [capacity, setCapacity] = useState(400);
  const [refrigerated, setRefrigerated] = useState(false);
  const [mode, setMode] = useState<"heuristic" | "optimized">("heuristic");
  const [result, setResult] = useState<LogisticsPlan | null>(null);
  const [usedFallback, setUsedFallback] = useState(false);
  const [lastScenario, setLastScenario] = useState<LogisticsPlanIn | null>(null);

  const mutation = useMutation({
    mutationFn: async (body: LogisticsPlanIn) => {
      setUsedFallback(false);
      if (mode === "optimized") {
        try {
          return await logisticsApi.optimize(body);
        } catch (e) {
          // 404 = endpoint not deployed; 503 = OR-Tools not installed.
          // Either way, fall back to the heuristic planner with a note.
          if (apiStatus(e) === 404 || apiStatus(e) === 503) {
            setUsedFallback(true);
            return await logisticsApi.plan(body);
          }
          throw e;
        }
      }
      return await logisticsApi.plan(body);
    },
    onSuccess: (res) => setResult(res),
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const plan = () => {
    const body: LogisticsPlanIn = {
      depot,
      mode: "delivery",
      stops: stops.map((s) => ({
        id: s.preset || `stop-${s.key}`,
        lat: s.lat,
        lon: s.lon,
        load_kg: s.load_kg,
        ...(s.max_transit_min ? { max_transit_min: Number(s.max_transit_min) } : {}),
      })),
      vehicles: [{ id: "truck-1", capacity_kg: capacity, refrigerated }],
      road_provider: "haversine",
      carbon_tradeoff: [0, 4, 20],
    };
    setLastScenario(body);
    mutation.mutate(body);
  };

  const updateStop = (key: number, patch: Partial<StopDraft>) =>
    setStops((prev) => prev.map((s) => (s.key === key ? { ...s, ...patch } : s)));

  const routeData = useMemo(() => {
    if (!result || !lastScenario) return [];
    const coords = new Map(lastScenario.stops.map((s) => [s.id, [s.lat, s.lon] as [number, number]]));
    return result.routes.map((rt) => {
      const pts: Array<[number, number]> = [[lastScenario.depot.lat, lastScenario.depot.lon]];
      const stopPts: RouteStopPoint[] = [];
      rt.stops.forEach((s, j) => {
        const c = coords.get(s.stop_id);
        if (!c) return;
        pts.push(c);
        stopPts.push({ id: s.stop_id, lat: c[0], lon: c[1], order: j + 1, vehicleId: rt.vehicle_id, arriveMin: s.arrive_min });
      });
      return { vehicleId: rt.vehicle_id, points: pts, stops: stopPts };
    });
  }, [result, lastScenario]);

  const totals = result?.totals;
  const improvement = result?.improvement_vs_baseline;
  const isStraightLine = result?.road_provider === "haversine";

  return (
    <div className="space-y-6">
      <PageHeader title={t("logisticsTitle")} sub={t("logisticsSub")} />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <Card className="h-fit p-5">
          <h2 className="font-display text-lg font-extrabold text-forest">{t("scenario")}</h2>
          <div className="mt-4 space-y-4">
            <Field label={t("depotLabel")} hint={t("depotHint")}>
              <Select
                value={depotPreset}
                onChange={(e) => {
                  setDepotPreset(e.target.value);
                  const loc = BD_LOCATIONS.find((l) => l.name === e.target.value);
                  if (loc) setDepot({ lat: loc.lat, lon: loc.lon });
                }}
              >
                {BD_LOCATIONS.map((l) => (
                  <option key={l.name} value={l.name}>
                    {l.name}
                  </option>
                ))}
              </Select>
            </Field>
            <div>
              <div className="grid grid-cols-2 gap-3">
                <Field label={t("latitude")}>
                  <Input type="number" step={0.0001} value={depot.lat} onChange={(e) => setDepot((d) => ({ ...d, lat: Number(e.target.value) }))} />
                </Field>
                <Field label={t("longitude")}>
                  <Input type="number" step={0.0001} value={depot.lon} onChange={(e) => setDepot((d) => ({ ...d, lon: Number(e.target.value) }))} />
                </Field>
              </div>
              <p className="mt-1 text-xs text-muted">{t("coordsHint")}</p>
            </div>
            <div>
              <p className="mb-2 flex items-center gap-2 text-[13px] font-bold">
                <MapPin className="h-4 w-4 text-leaf" /> {t("stopsLabel")}
              </p>
              <div className="space-y-3">
                {stops.map((s) => (
                  <div key={s.key} className="rounded-2xl border border-line bg-cream/60 p-3">
                    <div className="grid gap-2 sm:grid-cols-[1fr_90px_40px]">
                      <Field label={t("stopPlace")}>
                        <Select
                          value={s.preset}
                          onChange={(e) => {
                            const loc = BD_LOCATIONS.find((l) => l.name === e.target.value);
                            updateStop(s.key, { preset: e.target.value, lat: loc?.lat ?? s.lat, lon: loc?.lon ?? s.lon });
                          }}
                          aria-label={t("presetLocation")}
                        >
                          {BD_LOCATIONS.map((l) => (
                            <option key={l.name} value={l.name}>
                              {l.name}
                            </option>
                          ))}
                        </Select>
                      </Field>
                      <Field label={t("loadKg")}>
                        <Input
                          type="number"
                          min={1}
                          value={s.load_kg}
                          onChange={(e) => updateStop(s.key, { load_kg: Number(e.target.value) })}
                          aria-label={t("loadKg")}
                        />
                      </Field>
                      <div className="flex flex-col">
                        {/* Blank label spacer so the button lines up with the inputs, not the labels. */}
                        <span className="mb-1.5 hidden text-[13px] font-bold sm:block" aria-hidden="true">
                          &nbsp;
                        </span>
                        <button
                          type="button"
                          aria-label={t("removeStop")}
                          onClick={() => setStops((prev) => prev.filter((x) => x.key !== s.key))}
                          className="grid flex-1 place-items-center rounded-xl bg-white text-muted hover:text-red-700"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2">
                      <Field label={t("latitude")}>
                        <Input type="number" step={0.0001} value={s.lat} onChange={(e) => updateStop(s.key, { lat: Number(e.target.value) })} aria-label={t("latitude")} />
                      </Field>
                      <Field label={t("longitude")}>
                        <Input type="number" step={0.0001} value={s.lon} onChange={(e) => updateStop(s.key, { lon: Number(e.target.value) })} aria-label={t("longitude")} />
                      </Field>
                      <Field label={t("maxTransit")} hint={t("maxTransitHint")}>
                        <Input
                          type="number"
                          min={1}
                          placeholder={t("ti_spoilage")}
                          value={s.max_transit_min}
                          onChange={(e) => updateStop(s.key, { max_transit_min: e.target.value })}
                          aria-label={t("maxTransit")}
                        />
                      </Field>
                    </div>
                  </div>
                ))}
              </div>
              <Button
                variant="secondary"
                size="sm"
                className="mt-3"
                onClick={() =>
                  setStops((prev) => [
                    ...prev,
                    { key: Date.now(), preset: "Tongi", lat: 23.8905, lon: 90.4013, load_kg: 90, max_transit_min: "" },
                  ])
                }
              >
                <Plus className="h-4 w-4" /> {t("addStop")}
              </Button>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("vehicleCapacity")}>
                <Input type="number" min={1} value={capacity} onChange={(e) => setCapacity(Number(e.target.value))} />
              </Field>
              <label className="flex items-end gap-2 pb-2.5 text-sm font-bold">
                <input
                  type="checkbox"
                  checked={refrigerated}
                  onChange={(e) => setRefrigerated(e.target.checked)}
                  className="h-5 w-5 accent-[#1E7A4C]"
                />
                {t("refrigerated")}
              </label>
            </div>
            <div className="flex gap-2">
              {(
                [
                  ["heuristic", "heuristic"],
                  ["optimized", "optimized"],
                ] as Array<["heuristic" | "optimized", string]>
              ).map(([key, labelKey]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setMode(key)}
                  aria-pressed={mode === key}
                  className={`flex-1 rounded-full px-4 py-2.5 text-sm font-bold transition ${
                    mode === key ? "bg-forest text-white" : "border border-line bg-white text-muted hover:text-ink"
                  }`}
                >
                  {t(labelKey)}
                </button>
              ))}
            </div>
            <Button className="w-full" size="lg" loading={mutation.isPending} disabled={stops.length === 0} onClick={plan}>
              <Truck className="h-5 w-5" /> {mutation.isPending ? t("planning") : t("planRoutes")}
            </Button>
          </div>
        </Card>

        <div className="space-y-5">
          {result && totals && (
            <>
              {usedFallback && (
                <div className="rounded-2xl border border-[#f4e4bf] bg-[#fff8e9] px-4 py-3 text-[13px] text-[#80632d]">
                  {t("orToolsFallback")}
                </div>
              )}
              <Card className="p-5">
                <h2 className="font-display text-lg font-extrabold text-forest">{t("results")}</h2>
                <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
                  {[
                    [t("ti_vehicles"), fmtNum(totals.vehicles_used, 0)],
                    [t("ti_distanceKm"), `${fmtNum(totals.distance_km)} km`],
                    [t("ti_minutes"), fmtNum(totals.minutes, 0)],
                    [t("ti_co2"), `${fmtNum(totals.co2_kg)} kg`],
                    [t("ti_lateMin"), fmtNum(totals.late_min, 0)],
                    [t("ti_spoilage"), fmtNum(totals.spoilage_risk_min, 0)],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
                      {k}
                      <b className="block text-lg font-extrabold text-forest">{v}</b>
                    </div>
                  ))}
                </div>
                {isStraightLine && <p className="mt-3 text-xs text-muted">{t("straightLineNote")}</p>}
                {improvement && (
                  <p className="mt-2 text-[13px] text-muted">
                    {t("ti_baselineVs")}: {t("ti_objective")} {improvement.objective_pct}% · CO₂ {improvement.co2_pct}% ·{" "}
                    {t("ti_timeWord")} {improvement.minutes_pct}% {t("ti_negativeWorse")}
                  </p>
                )}
                {(result.notes || []).map((n, i) => (
                  <p key={i} className="mt-2 text-xs text-muted">
                    {n}
                  </p>
                ))}
              </Card>
              <Card className="p-5">
                <h2 className="font-display text-lg font-extrabold text-forest">{t("ti_routeMapTitle")}</h2>
                <div className="mt-3">
                  <RouteMap depot={lastScenario?.depot || DEFAULT_DEPOT} routes={routeData} />
                </div>
              </Card>
              {result.routes.map((rt) => (
                <Card key={rt.vehicle_id} className="p-5">
                  <h3 className="font-display font-bold text-forest">
                    {rt.vehicle_id} {rt.refrigerated ? "❄" : ""} — {fmtNum(rt.load_kg, 0)}/{fmtNum(rt.capacity_kg, 0)} kg ·{" "}
                    {fmtNum(rt.distance_km)} km · {fmtNum(rt.co2_kg)} kg CO₂e
                  </h3>
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full min-w-[320px] border-collapse text-[13px]">
                      <thead>
                        <tr>
                          <th className="border-b border-line px-2 py-2 text-left font-bold">#</th>
                          <th className="border-b border-line px-2 py-2 text-left font-bold">{t("ti_stop")}</th>
                          <th className="border-b border-line px-2 py-2 text-left font-bold">{t("ti_arriveMin")}</th>
                          <th className="border-b border-line px-2 py-2 text-left font-bold">{t("ti_late")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rt.stops.map((s, j) => (
                          <tr key={s.stop_id}>
                            <td className="border-b border-line px-2 py-2">{j + 1}</td>
                            <td className="border-b border-line px-2 py-2">{s.stop_id}</td>
                            <td className="border-b border-line px-2 py-2">{s.arrive_min}</td>
                            <td className="border-b border-line px-2 py-2">{s.late_min}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              ))}
              {result.carbon_tradeoff && result.carbon_tradeoff.length > 0 && (
                <Card className="p-5">
                  <h3 className="font-display font-bold text-forest">{t("ti_tradeoff")}</h3>
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full min-w-[320px] border-collapse text-[13px]">
                      <thead>
                        <tr>
                          <th className="border-b border-line px-2 py-2 text-left font-bold">{t("ti_co2Weight")}</th>
                          <th className="border-b border-line px-2 py-2 text-left font-bold">{t("ti_minutes")}</th>
                          <th className="border-b border-line px-2 py-2 text-left font-bold">{t("ti_co2")}</th>
                          <th className="border-b border-line px-2 py-2 text-left font-bold">{t("ti_km")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.carbon_tradeoff.map((x) => (
                          <tr key={x.co2_per_kg_weight}>
                            <td className="border-b border-line px-2 py-2">{x.co2_per_kg_weight}</td>
                            <td className="border-b border-line px-2 py-2">{x.minutes}</td>
                            <td className="border-b border-line px-2 py-2">{x.co2_kg}</td>
                            <td className="border-b border-line px-2 py-2">{x.distance_km}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}
            </>
          )}
          {!result && !mutation.isPending && (
            <Card className="flex h-full min-h-[300px] flex-col items-center justify-center gap-3 p-8 text-center">
              <Truck className="h-12 w-12 text-leaf" />
              <p className="font-display font-bold text-forest">{t("logisticsTitle")}</p>
              <p className="max-w-sm text-sm text-muted">{t("logisticsSub")}</p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
