import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "marigold";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const variants: Record<Variant, string> = {
  primary: "bg-leaf hover:bg-forest text-white shadow-sm",
  secondary: "bg-mint text-forest hover:bg-[#d8ecdc]",
  ghost: "bg-transparent text-forest hover:bg-mint",
  danger: "bg-red-600 hover:bg-red-700 text-white",
  marigold: "bg-marigold hover:bg-[#e0922a] text-[#2e2110]",
};

const sizes: Record<Size, string> = {
  sm: "px-3.5 py-2 text-[13px]",
  md: "px-5 py-2.5 text-sm",
  lg: "px-6 py-3 text-base",
};

export function Button({ variant = "primary", size = "md", loading, disabled, className = "", children, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-full font-bold transition disabled:cursor-not-allowed disabled:opacity-60 ${variants[variant]} ${sizes[size]} ${className}`}
      {...rest}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-3xl border border-line bg-white shadow-card ${className}`}>{children}</div>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-muted" role="status">
      <Loader2 className="h-8 w-8 animate-spin text-leaf" />
      {label && <span className="text-sm font-semibold">{label}</span>}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
}: {
  icon?: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-3xl border border-dashed border-[#d8d2ba] bg-white/60 px-6 py-10 text-center">
      {icon}
      <p className="font-display text-base font-bold text-ink">{title}</p>
      {hint && <p className="max-w-md text-sm text-muted">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-3xl border border-[#f1c4c4] bg-[#fceaea] px-5 py-4 text-sm text-[#a53f3f]">
      <p className="font-bold">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-2 font-bold underline">
          Try again
        </button>
      )}
    </div>
  );
}

export function PageHeader({ title, sub, action }: { title: string; sub?: string; action?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="font-display text-2xl font-extrabold text-forest sm:text-3xl">{title}</h1>
        {sub && <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">{sub}</p>}
      </div>
      {action}
    </div>
  );
}
