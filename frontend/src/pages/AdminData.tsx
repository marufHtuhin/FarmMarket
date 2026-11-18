import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, ScrollText } from "lucide-react";
import { adminApi, forecastApi, pricesApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage, isNotFound } from "../utils/format";
import { FALLBACK_HUBS } from "../utils/geo";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { Field, Input, Select } from "../components/ui/fields";
import { Badge } from "../components/ui/misc";
import { PriceLabelBadge, StaleWarning } from "../components/PriceBadge";

/** Admin form for the daily real-price entry (POST /api/v1/prices/manual).
 *  DAM has no public API, so an admin reads the day's DAM report and records
 *  the price here by hand, with a source note. Re-entering the same day
 *  updates the stored price instead of duplicating it. */
export function ManualPriceForm() {
  const { t, fmtDate } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [hub, setHub] = useState("dhaka");
  const [crop, setCrop] = useState("tomato");
  const [price, setPrice] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState("");

  const hubsQ = useQuery({ queryKey: ["forecast-hubs"], queryFn: forecastApi.hubs, retry: false });
  const recentQ = useQuery({ queryKey: ["manual-prices"], queryFn: () => pricesApi.manualList(10), retry: false });

  const hubs = hubsQ.data?.hubs || FALLBACK_HUBS;
  const crops = hubsQ.data?.crops || [
    { id: "tomato", name: "Tomato" },
    { id: "potato", name: "Potato" },
    { id: "onion", name: "Onion" },
    { id: "banana", name: "Banana" },
    { id: "maize", name: "Maize" },
  ];

  const save = useMutation({
    mutationFn: () =>
      pricesApi.manualEntry({ crop, hub, price: Number(price), date, note: note.trim() || undefined }),
    onSuccess: (r) => {
      toast(r.updated ? t("manualPriceUpdated") : t("manualPriceSaved"), "success");
      qc.invalidateQueries({ queryKey: ["manual-prices"] });
      qc.invalidateQueries({ queryKey: ["prices-latest"] });
      setPrice("");
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  return (
    <Card className="mb-6 p-5">
      <h2 className="font-display text-lg font-extrabold text-forest">{t("manualPriceTitle")}</h2>
      <p className="mt-1 text-sm text-muted">{t("manualPriceHint")}</p>
      <form
        className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label={t("fieldHub")} required>
          <Select value={hub} onChange={(e) => setHub(e.target.value)} aria-label={t("selectHub")}>
            {hubs.map((h) => (
              <option key={h.id} value={h.id}>
                {h.name}, {h.country}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("fieldCrop")} required>
          <Select value={crop} onChange={(e) => setCrop(e.target.value)} aria-label={t("selectCropLabel")}>
            {crops.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("fieldPrice")} required>
          <Input
            type="number"
            min="0.01"
            step="0.01"
            inputMode="decimal"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            required
          />
        </Field>
        <Field label={t("fieldDate")} required>
          <Input type="date" value={date} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setDate(e.target.value)} required />
        </Field>
        <Field label={t("manualPriceNoteLabel")} hint={t("manualPriceNotePlaceholder")}>
          <Input value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} placeholder={t("manualPriceNotePlaceholder")} />
        </Field>
        <div className="flex items-end">
          <Button type="submit" loading={save.isPending} disabled={!price || Number(price) <= 0}>
            {t("save")}
          </Button>
        </div>
      </form>
      <h3 className="mt-6 font-display text-base font-extrabold text-forest">{t("manualPriceRecent")}</h3>
      {recentQ.isLoading ? (
        <Spinner />
      ) : recentQ.isError ? (
        <ErrorState message={apiErrorMessage(recentQ.error)} onRetry={() => recentQ.refetch()} />
      ) : (recentQ.data?.items || []).length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("noLatestPrices")}</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[520px] border-collapse text-[13px]">
            <tbody>
              {(recentQ.data?.items || []).map((p) => (
                <tr key={p.id}>
                  <td className="border-b border-line px-2 py-2 font-bold">
                    {p.hub} · {p.crop}
                  </td>
                  <td className="border-b border-line px-2 py-2">৳{p.price}/kg</td>
                  <td className="border-b border-line px-2 py-2">{p.observed_on ? fmtDate(p.observed_on) : "—"}</td>
                  <td className="border-b border-line px-2 py-2 text-muted">{p.note || p.source}</td>
                  <td className="border-b border-line px-2 py-2">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <PriceLabelBadge label={p.label} />
                      <StaleWarning stale={p.stale} />
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export function AdminDataSourcesPage() {
  const { t, fmtDateTime } = useLang();
  const q = useQuery({ queryKey: ["admin-data-sources"], queryFn: adminApi.dataSources, retry: false });

  return (
    <div>
      <PageHeader title={t("dataSourcesTitle")} sub={t("adminSub")} />
      <ManualPriceForm />
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && isNotFound(q.error) && (
        <EmptyState icon={<Database className="h-10 w-10 text-leaf" />} title={t("dataSourcesNotConfigured")} />
      )}
      {q.isError && !isNotFound(q.error) && (
        <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />
      )}
      {q.isSuccess && q.data.length === 0 && (
        <EmptyState icon={<Database className="h-10 w-10 text-leaf" />} title={t("dataSourcesNotConfigured")} />
      )}
      {q.isSuccess && q.data.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {q.data.map((ds) => (
            <Card key={ds.name} className="p-5">
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-display text-lg font-extrabold text-forest">{ds.name}</h3>
                <Badge tone={ds.status === "ok" || ds.status === "healthy" ? "green" : ds.status === "error" ? "red" : "gray"}>
                  {ds.status || "—"}
                </Badge>
              </div>
              <p className="mt-1 text-sm text-muted">
                {ds.kind}
                {ds.countries?.length ? ` · ${ds.countries.join(", ")}` : ""}
              </p>
              {ds.endpoint && <p className="mt-2 break-all font-mono text-xs text-muted">{ds.endpoint}</p>}
              <p className="mt-2 text-[13px]">
                {t("lastSync")}: <b>{ds.last_sync_at ? fmtDateTime(ds.last_sync_at) : "—"}</b>
              </p>
              {ds.notes && <p className="mt-2 text-[13px] leading-relaxed text-muted">{ds.notes}</p>}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export function AdminAuditLogsPage() {
  const { t, fmtDateTime } = useLang();
  const q = useQuery({ queryKey: ["admin-audit-logs"], queryFn: adminApi.auditLogs, retry: false });

  return (
    <div>
      <PageHeader title={t("auditLogsTitle")} sub={t("adminSub")} />
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && q.data.length === 0 && (
        <EmptyState icon={<ScrollText className="h-10 w-10 text-leaf" />} title={t("noAuditLogs")} />
      )}
      {q.isSuccess && q.data.length > 0 && (
        <div className="overflow-hidden rounded-3xl border border-line bg-white shadow-card">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-line bg-cream text-xs uppercase tracking-wide text-muted">
                  <th className="px-4 py-3">{t("timestampLabel")}</th>
                  <th className="px-4 py-3">{t("actionLabel")}</th>
                  <th className="px-4 py-3">{t("actorLabel")}</th>
                  <th className="px-4 py-3">{t("detailsLabel")}</th>
                </tr>
              </thead>
              <tbody>
                {q.data.map((log) => (
                  <tr key={log.id} className="border-b border-line last:border-0">
                    <td className="whitespace-nowrap px-4 py-3 text-muted">
                      {log.created_at ? fmtDateTime(log.created_at) : "—"}
                    </td>
                    <td className="px-4 py-3 font-bold">{log.action}</td>
                    <td className="px-4 py-3">{log.actor_name || (log.actor_id ? `#${log.actor_id}` : "—")}</td>
                    <td className="max-w-xs truncate px-4 py-3 text-muted">
                      {typeof log.details === "string" ? log.details : log.details ? JSON.stringify(log.details) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
