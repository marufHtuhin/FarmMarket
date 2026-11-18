export function unitLabel(unit: string | null | undefined, lang: string): string {
  const u = (unit || "kg").toLowerCase();
  const map: Record<string, { bn: string; en: string }> = {
    kg: { bn: "কেজি", en: "kg" },
    quintal: { bn: "কুইন্টাল", en: "quintal" },
    ton: { bn: "টন", en: "ton" },
    piece: { bn: "টি", en: "piece" },
  };
  const m = map[u];
  return m ? (lang === "bn" ? m.bn : m.en) : unit || "";
}

export function statusTone(status: string): "amber" | "green" | "red" | "gray" | "blue" {
  const s = (status || "").toLowerCase();
  if (s === "pending") return "amber";
  if (s === "accepted" || s === "completed" || s === "delivered" || s === "active" || s === "ok") return "green";
  if (s === "rejected" || s === "cancelled" || s === "failed" || s === "excursion") return "red";
  if (s === "in_transit" || s === "picked_up" || s === "assigned") return "blue";
  return "gray";
}

export function apiErrorMessage(err: unknown): string {
  if (err && typeof err === "object") {
    const e = err as { response?: { data?: { detail?: unknown }; status?: number }; message?: string };
    const detail = e.response?.data?.detail;
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail)) {
      const msgs = detail.map((x) => (typeof x === "object" && x ? (x as { msg?: string }).msg : String(x))).filter(Boolean);
      if (msgs.length) return msgs.join(", ");
    }
    if (e.message) return e.message;
  }
  return "Request failed";
}

export function apiStatus(err: unknown): number | null {
  if (err && typeof err === "object") {
    const e = err as { response?: { status?: number } };
    if (typeof e.response?.status === "number") return e.response.status;
  }
  return null;
}

export function isNotFound(err: unknown): boolean {
  return apiStatus(err) === 404;
}

export function formatPriceTaka(n: number | string | null | undefined, fmtNum: (n: number | string | null | undefined) => string): string {
  return `৳${fmtNum(n)}`;
}

/** Human "X ago" for a timestamp, using the i18n translate function. Returns
 *  "" when the timestamp is missing or unparseable — never a made-up age. */
export function timeAgo(
  iso: string | null | undefined,
  t: (key: string, vars?: Record<string, string | number>) => string,
  nowMs: number = Date.now()
): string {
  if (!iso) return "";
  const ms = new Date(iso).getTime();
  if (Number.isNaN(ms)) return "";
  const mins = Math.max(0, Math.floor((nowMs - ms) / 60000));
  if (mins < 1) return t("timeJustNow");
  if (mins < 60) return t("timeMinutesAgo", { n: mins });
  const hours = Math.floor(mins / 60);
  if (hours < 24) return t("timeHoursAgo", { n: hours });
  return t("timeDaysAgo", { n: Math.floor(hours / 24) });
}
