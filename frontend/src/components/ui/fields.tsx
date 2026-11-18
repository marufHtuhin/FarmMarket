import { useState } from "react";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { Eye, EyeOff } from "lucide-react";

const fieldCls =
  "w-full rounded-xl border border-line bg-white px-3.5 py-2.5 text-ink min-w-0 placeholder:text-[#9aa79d] focus:border-leaf focus:outline-none focus:ring-2 focus:ring-[#d8ecdc] disabled:bg-cream disabled:text-muted";

export function Field({
  label,
  error,
  hint,
  children,
  required,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
  required?: boolean;
}) {
  return (
    <label className="block min-w-0">
      <span className="mb-1.5 block text-[13px] font-bold text-ink">
        {label}
        {required && <span className="ml-1 text-red-600">*</span>}
      </span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-muted">{hint}</span>}
      {error && (
        <span role="alert" className="mt-1 block text-xs font-semibold text-red-700">
          {error}
        </span>
      )}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${fieldCls} ${props.className || ""}`} />;
}

// Password field with a show/hide (eye) toggle. The toggle is type="button"
// so it never submits the form, and toggling only flips the input type —
// the typed value is untouched. Labels come from i18n via the caller.
export function PasswordInput({
  showLabel,
  hideLabel,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { showLabel: string; hideLabel: string }) {
  const [show, setShow] = useState(false);
  return (
    <span className="relative block">
      <Input {...props} type={show ? "text" : "password"} className={`pr-11 ${props.className || ""}`} />
      <button
        type="button"
        aria-label={show ? hideLabel : showLabel}
        aria-pressed={show}
        onClick={() => setShow((s) => !s)}
        className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted hover:text-ink"
      >
        {show ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
      </button>
    </span>
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${fieldCls} ${props.className || ""}`} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${fieldCls} ${props.className || ""}`} />;
}
