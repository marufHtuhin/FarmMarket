import type { ReactNode } from "react";
import { X } from "lucide-react";
import { statusTone } from "../../utils/format";

export function Badge({
  children,
  tone = "gray",
  className = "",
}: {
  children: ReactNode;
  tone?: "green" | "amber" | "red" | "gray" | "blue" | "marigold";
  className?: string;
}) {
  const tones: Record<string, string> = {
    green: "bg-[#e5f4e9] text-[#267041]",
    amber: "bg-[#fdf3d7] text-[#8a5a12]",
    red: "bg-[#fceaea] text-[#a53f3f]",
    gray: "bg-[#f0f3f0] text-[#526155]",
    blue: "bg-[#e3eefc] text-[#1d4ed8]",
    marigold: "bg-marigold text-[#2e2110]",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-extrabold ${tones[tone]} ${className}`}>
      {children}
    </span>
  );
}

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return <Badge tone={statusTone(status)}>{label ?? status}</Badge>;
}

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[90] flex items-end justify-center bg-black/45 p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-label={title}>
      <div
        className={`max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-white shadow-lift sm:rounded-3xl ${wide ? "sm:max-w-2xl" : "sm:max-w-lg"}`}
      >
        <div className="sticky top-0 flex items-center justify-between gap-3 border-b border-line bg-white px-5 py-4">
          <h2 className="font-display text-lg font-extrabold text-forest">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-full bg-cream p-2 text-muted hover:text-ink"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Drawer({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[90] bg-black/45" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-y-0 left-0 flex w-[85vw] max-w-sm flex-col bg-white shadow-lift">
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 className="font-display text-lg font-extrabold text-forest">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-full bg-cream p-2 text-muted hover:text-ink"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="thin-scroll flex-1 overflow-y-auto p-5">{children}</div>
      </div>
      <button type="button" aria-label="Close drawer" className="absolute inset-y-0 right-0 w-[15vw]" onClick={onClose} />
    </div>
  );
}

export function StatCard({
  label,
  value,
  icon,
  tint = "bg-mint",
}: {
  label: string;
  value: string;
  icon: ReactNode;
  tint?: string;
}) {
  return (
    <div className={`${tint} flex items-start justify-between gap-3 rounded-3xl p-4 sm:p-5`}>
      <div className="min-w-0">
        <span className="block text-[13px] font-semibold text-muted">{label}</span>
        <b className="mt-1 block truncate font-display text-[26px] leading-tight font-extrabold text-forest">{value}</b>
      </div>
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-leaf text-2xl text-white shadow-sm">{icon}</span>
    </div>
  );
}
