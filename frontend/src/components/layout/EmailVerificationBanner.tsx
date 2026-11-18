import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { MailWarning, X } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { useLang } from "../../i18n/LanguageContext";
import { useToast } from "../../contexts/ToastContext";
import { authApi } from "../../services/api";
import { apiErrorMessage } from "../../utils/format";

const DISMISSED_KEY = "fm_email_banner_dismissed";

// Small banner for logged-in users whose email is not verified yet.
// Shows only when /me explicitly reports email_verified === false (older
// cached sessions without the field get it on the next refreshUser).
// Dismissible once per session; the resend button requests a fresh link.
export function EmailVerificationBanner() {
  const { user } = useAuth();
  const { t } = useLang();
  const { toast } = useToast();
  const [dismissed, setDismissed] = useState(
    () => sessionStorage.getItem(DISMISSED_KEY) === "1"
  );

  const resend = useMutation({
    mutationFn: () => authApi.resendVerification(),
    onSuccess: () => toast(t("verifyEmailResent"), "success"),
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  if (!user || user.email_verified !== false || dismissed) return null;

  return (
    <div
      role="status"
      className="mb-4 flex items-start gap-3 rounded-2xl border border-[#ecd28a] bg-[#fdf3d0] px-4 py-3 text-sm text-[#5c4710]"
    >
      <MailWarning className="mt-0.5 h-5 w-5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="font-bold">{t("emailNotVerified")}</p>
        <p className="mt-0.5 text-[13px] leading-relaxed">{t("emailNotVerifiedAction")}</p>
      </div>
      <button
        type="button"
        disabled={resend.isPending}
        onClick={() => resend.mutate()}
        className="shrink-0 rounded-full bg-[#5c4710] px-3 py-1.5 text-xs font-bold text-white hover:opacity-90 disabled:opacity-60"
      >
        {t("resendVerification")}
      </button>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => {
          sessionStorage.setItem(DISMISSED_KEY, "1");
          setDismissed(true);
        }}
        className="shrink-0 rounded-full p-1 hover:bg-black/5"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
