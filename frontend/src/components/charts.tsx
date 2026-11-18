import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useLang } from "../i18n/LanguageContext";

interface ForecastRow {
  ds: string;
  history?: number | null;
  forecast?: number | null;
  lower?: number | null;
  band?: number | null;
}

/** History (solid leaf line) + forecast (dashed marigold) + 80% confidence band. */
export function ForecastChart({
  history,
  forecast,
  height = 280,
}: {
  history: Array<{ ds: string; y: number }>;
  forecast: Array<{ ds: string; yhat: number; lower: number; upper: number }>;
  height?: number;
}) {
  const { t } = useLang();
  const rows: ForecastRow[] = history.map((h) => ({ ds: h.ds, history: h.y }));
  if (history.length && forecast.length) {
    // Bridge point so the forecast line starts at the last history value.
    const last = history[history.length - 1];
    rows.push({ ds: last.ds, history: last.y, forecast: last.y, lower: last.y, band: 0 });
  }
  forecast.forEach((f) => rows.push({ ds: f.ds, forecast: f.yhat, lower: f.lower, band: f.upper - f.lower }));

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e0cc" />
          <XAxis dataKey="ds" tick={{ fontSize: 11 }} minTickGap={28} />
          <YAxis tick={{ fontSize: 11 }} width={48} domain={["auto", "auto"]} />
          <Tooltip
            formatter={(value, name) => [
              typeof value === "number" ? `৳${value.toFixed(2)}` : value,
              name === "band" ? t("ti_intervalBand") : name,
            ]}
          />
          <Legend />
          <Area
            type="monotone"
            dataKey="lower"
            stackId="band"
            stroke="none"
            fill="transparent"
            name={t("ti_intervalBand")}
            tooltipType="none"
            legendType="none"
          />
          <Area
            type="monotone"
            dataKey="band"
            stackId="band"
            stroke="none"
            fill="rgba(242,163,60,0.25)"
            name={t("ti_intervalBand")}
          />
          <Line
            type="monotone"
            dataKey="history"
            stroke="#1E7A4C"
            strokeWidth={2}
            dot={false}
            name={t("ti_history")}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="forecast"
            stroke="#F2A33C"
            strokeWidth={2.5}
            strokeDasharray="6 4"
            dot={{ r: 2 }}
            name={t("ti_forecast")}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PriceHistoryChart({
  data,
  height = 260,
}: {
  data: Array<{ date: string; price: number }>;
  height?: number;
}) {
  const { t } = useLang();
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e0cc" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={28} />
          <YAxis tick={{ fontSize: 11 }} width={48} domain={["auto", "auto"]} />
          <Tooltip formatter={(value) => [typeof value === "number" ? `৳${value.toFixed(2)}` : value, t("price")]} />
          <Line type="monotone" dataKey="price" stroke="#1E7A4C" strokeWidth={2} dot={{ r: 3 }} name={t("price")} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SensorTempChart({
  data,
  height = 200,
}: {
  data: Array<{ time: string; temp: number }>;
  height?: number;
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e0cc" />
          <XAxis dataKey="time" tick={{ fontSize: 11 }} minTickGap={28} />
          <YAxis tick={{ fontSize: 11 }} width={44} domain={["auto", "auto"]} unit="°C" />
          <Tooltip formatter={(value) => [typeof value === "number" ? `${value.toFixed(1)}°C` : value, "Temp"]} />
          <Line type="monotone" dataKey="temp" stroke="#1E7A4C" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

interface WeatherDayRow {
  date: string;
  temp_max_c: number | null;
  temp_min_c: number | null;
}

/**
 * Past 7 days (solid leaf lines) + forecast incl. today (dashed marigold
 * lines) for daily max/min temperature, with a vertical marker on today.
 * Missing values render as gaps (connectNulls is off) — never interpolated.
 */
export function WeatherChart({
  past,
  forecast,
  height = 280,
}: {
  past: WeatherDayRow[];
  forecast: WeatherDayRow[];
  height?: number;
}) {
  const { t } = useLang();
  const today = forecast[0]?.date;
  const rows = [
    ...past.map((d) => ({ date: d.date, pastMax: d.temp_max_c, pastMin: d.temp_min_c })),
    ...forecast.map((d) => ({ date: d.date, fcMax: d.temp_max_c, fcMin: d.temp_min_c })),
  ];
  const pastLabel = t("weatherPast");
  const fcLabel = t("weatherForecast");
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e0cc" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={28} />
          <YAxis tick={{ fontSize: 11 }} width={44} domain={["auto", "auto"]} unit="°C" />
          <Tooltip
            formatter={(value, name) => [
              typeof value === "number" ? `${value.toFixed(1)}°C` : value,
              name,
            ]}
          />
          <Legend />
          {today && (
            <ReferenceLine x={today} stroke="#80632d" strokeDasharray="3 3" label={{ value: t("weatherToday"), fontSize: 11, fill: "#80632d" }} />
          )}
          <Line
            type="monotone"
            dataKey="pastMax"
            stroke="#1E7A4C"
            strokeWidth={2}
            dot={{ r: 2 }}
            name={`${pastLabel} · ${t("wxTempMax")}`}
          />
          <Line
            type="monotone"
            dataKey="pastMin"
            stroke="#7FB069"
            strokeWidth={2}
            dot={{ r: 2 }}
            name={`${pastLabel} · ${t("wxTempMin")}`}
          />
          <Line
            type="monotone"
            dataKey="fcMax"
            stroke="#F2A33C"
            strokeWidth={2.5}
            strokeDasharray="6 4"
            dot={{ r: 2 }}
            name={`${fcLabel} · ${t("wxTempMax")}`}
          />
          <Line
            type="monotone"
            dataKey="fcMin"
            stroke="#E07B39"
            strokeWidth={2}
            strokeDasharray="6 4"
            dot={{ r: 2 }}
            name={`${fcLabel} · ${t("wxTempMin")}`}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
