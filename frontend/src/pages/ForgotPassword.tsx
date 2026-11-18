import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { authApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage, apiStatus } from "../utils/format";
import { Card, Button } from "../components/ui/core";
import { Field, Input } from "../components/ui/fields";

export function ForgotPasswordPage() {
  const { t } = useLang();
  const { toast } = useToast();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [devToken, setDevToken] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => authApi.forgotPassword(email),
    onSuccess: (res) => {
      setSent(true);
      if (res.reset_token) setDevToken(res.reset_token);
      toast(t("resetSent"), "success");
    },
    onError: (e) => {
      if (apiStatus(e) === 404) toast(t("errorGeneric"), "error");
      else toast(apiErrorMessage(e), "error");
    },
  });

  return (
    <div className="mx-auto max-w-md py-8">
      <Card className="p-6 sm:p-8">
        <h1 className="font-display text-2xl font-extrabold text-forest">{t("forgotPassword")}</h1>
        <p className="mt-1 text-sm text-muted">{t("forgotSubtitle")}</p>
        {sent ? (
          <div className="mt-6 space-y-4">
            <div className="rounded-2xl bg-mint px-4 py-3 text-sm font-semibold text-forest">{t("resetSent")}</div>
            {devToken && (
              <div className="rounded-2xl border border-dashed border-line bg-cream px-4 py-3 text-[13px] text-muted">
                <p className="font-bold text-ink">Dev only — reset token returned by the API:</p>
                <Link to={`/reset-password?token=${encodeURIComponent(devToken)}`} className="font-bold text-leaf hover:underline">
                  {t("resetPassword")} →
                </Link>
              </div>
            )}
            <Link to="/login">
              <Button variant="secondary" className="w-full">
                {t("backToLogin")}
              </Button>
            </Link>
          </div>
        ) : (
          <form
            className="mt-6 space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (email) mutation.mutate();
            }}
          >
            <Field label={t("email")} required>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </Field>
            <Button type="submit" loading={mutation.isPending} className="w-full" size="lg">
              {t("sendResetLink")}
            </Button>
          </form>
        )}
      </Card>
    </div>
  );
}
