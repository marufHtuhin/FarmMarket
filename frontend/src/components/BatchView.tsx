import { useState } from "react";
import { ShieldCheck, ShieldAlert, Thermometer, QrCode, Copy, Check } from "lucide-react";
import { twinApi, type BatchPublic } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { Card } from "./ui/core";
import { Badge } from "./ui/misc";
import { SensorTempChart } from "./charts";

function Kv({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
      {k}
      <b className="block break-words text-base font-extrabold text-forest">{v}</b>
    </div>
  );
}

/** Shared public twin view — used by /batches/:code and the public /verify/:code page. */
export function BatchView({ batch, showQr = true }: { batch: BatchPublic; showQr?: boolean }) {
  const { t, fmtDate, fmtDateTime } = useLang();
  const [qrFailed, setQrFailed] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const cc = batch.cold_chain;
  const integrity = batch.integrity;

  const copyVerifyLink = async () => {
    if (!batch.verify_url) return;
    try {
      await navigator.clipboard.writeText(batch.verify_url);
    } catch {
      // Clipboard API unavailable (non-secure context / old browser) — the
      // link text itself stays selectable, so copying still works by hand.
      return;
    }
    setLinkCopied(true);
    window.setTimeout(() => setLinkCopied(false), 2000);
  };

  // The API sends each seal's temp_c as the {min, max, avg} summary object
  // (a plain number is accepted for robustness). The chart plots the avg.
  const tempOf = (ev: { temp_c?: number | { min: number; max: number; avg: number } | null }): number | null =>
    typeof ev.temp_c === "number" ? ev.temp_c : typeof ev.temp_c?.avg === "number" ? ev.temp_c.avg : null;
  const tempPoints = batch.timeline
    .filter((ev) => ev.event === "cold_chain_check")
    .map((ev) => ({ time: fmtDate(ev.time), temp: tempOf(ev) }))
    .filter((p): p is { time: string; temp: number } => p.temp !== null);

  const simulated =
    (cc.simulated_readings ?? 0) > 0 ||
    batch.timeline.some((ev) => String(ev.event).includes("simulat"));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        {integrity.chain_valid ? (
          <Badge tone="green">
            <ShieldCheck className="h-3.5 w-3.5" /> {t("chainValid")}
          </Badge>
        ) : (
          <Badge tone="red">
            <ShieldAlert className="h-3.5 w-3.5" /> {t("chainInvalid")}
          </Badge>
        )}
        {simulated && <Badge tone="amber">{t("simulatedBadge")}</Badge>}
        <Badge tone="gray">
          {t("ti_sensorReadings")}: {cc.n_readings}
        </Badge>
        {integrity.externally_anchored && <Badge tone="blue">Anchored</Badge>}
      </div>

      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
        <Kv k={t("ti_crop")} v={batch.crop} />
        <Kv k={t("ti_origin")} v={batch.origin_district} />
        <Kv k={t("ti_harvested")} v={batch.harvested_at ? fmtDate(batch.harvested_at) : t("ti_na")} />
        <Kv k={t("coldChainStatus")} v={cc.status || t("ti_na")} />
        <Kv
          k={t("ti_sensorReadings")}
          v={String(cc.n_readings)}
        />
        <Kv
          k="Temp (°C)"
          v={cc.temp_c ? `${cc.temp_c.min} – ${cc.temp_c.max} (avg ${cc.temp_c.avg})` : t("ti_na")}
        />
      </div>

      {integrity.note && (
        <div className="rounded-2xl border border-[#f4e4bf] bg-[#fff8e9] px-4 py-3 text-[13px] text-[#80632d]">
          {integrity.note}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="font-display text-lg font-extrabold text-forest">{t("timelineLabel")}</h3>
          <div className="ml-1.5 mt-3 border-l-[3px] border-mint pl-3.5">
            {batch.timeline.length === 0 && <p className="text-sm text-muted">{t("noResults")}</p>}
            {batch.timeline.map((ev, i) => (
              <div key={i} className="my-2.5 text-[13px]">
                <b className="capitalize">{ev.event.replace(/_/g, " ")}</b>{" "}
                <span className="text-muted">{fmtDateTime(ev.time)}</span>
                {ev.status ? ` — ${ev.status}` : ""}
                {ev.readings !== undefined ? `, ${ev.readings} ${t("ti_readingsWord")}` : ""}
                {tempOf(ev) !== null ? ` · ${tempOf(ev)}°C` : ""}
              </div>
            ))}
          </div>
          <p className="mt-4 break-all text-xs text-muted">
            {t("ti_headHash")}: {integrity.head_hash}
          </p>
        </Card>

        <div className="space-y-5">
          <Card className="p-5">
            <h3 className="flex items-center gap-2 font-display text-lg font-extrabold text-forest">
              <Thermometer className="h-5 w-5 text-leaf" /> {t("sensorHistory")}
            </h3>
            {tempPoints.length > 1 ? (
              <div className="mt-3">
                <SensorTempChart data={tempPoints} />
              </div>
            ) : (
              <p className="mt-3 text-sm text-muted">{t("noSensorData")}</p>
            )}
          </Card>

          {showQr && (
            <Card className="p-5">
              <h3 className="flex items-center gap-2 font-display text-lg font-extrabold text-forest">
                <QrCode className="h-5 w-5 text-leaf" /> {t("qrCode")}
              </h3>
              {!qrFailed ? (
                <img
                  src={twinApi.qrUrl(batch.batch_code)}
                  alt={`QR code for batch ${batch.batch_code}`}
                  className="mt-3 h-44 w-44 rounded-2xl border border-line"
                  onError={() => setQrFailed(true)}
                />
              ) : (
                <p className="mt-3 rounded-2xl bg-cream px-4 py-3 font-mono text-sm font-bold">{batch.batch_code}</p>
              )}
              <p className="mt-2 font-mono text-xs text-muted">{batch.batch_code}</p>
              {batch.verify_url && (
                <div className="mt-3 rounded-2xl bg-cream px-3.5 py-3">
                  <p className="text-xs text-muted">{t("qrVerifyLink")}</p>
                  <a
                    href={batch.verify_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 block break-all font-mono text-xs font-bold text-leaf underline"
                  >
                    {batch.verify_url}
                  </a>
                  <button
                    type="button"
                    onClick={copyVerifyLink}
                    className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-line bg-white px-3 py-1 text-xs font-bold text-forest"
                  >
                    {linkCopied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    {linkCopied ? t("linkCopied") : t("copyLink")}
                  </button>
                </div>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
