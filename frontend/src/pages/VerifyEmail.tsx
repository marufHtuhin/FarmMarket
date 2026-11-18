import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, MailCheck } from "lucide-react";
import { authApi } from "../services/api";
import { useAuth, roleHome } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Card, Button, Spinner } from "../components/ui/core";

type Status = "verifying" | "success" | "error" | "no-token";

// Registration-confirmation page (NOT the Digital Twin /verify/:code
// route — that one verifies a batch QR code). The verification email
// links here with ?token=; the token is submitted automatically on load.
export function VerifyEmailPage() {
  const { t } = useLang();
  const { toast } = useToast();
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [status, setStatus] = useState<Status>(token ? "verifying" : "no-token");
  const attempted = useRef(false);

  useEffect(() => {
    if (!token || attempted.current) return;
    attempted.current = true;
    let cancelled = false;
    authApi
      .verifyEmail(token)
      .then(async () => {
        if (cancelled) return;
        setStatus("success");
        // Refresh /me so the unverified banner disappears immediately.
        await refreshUser().catch(() => undefined);
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [token, refreshUser]);

  const resend = useMutation({
    mutationFn: () => authApi.resendVerification(),
    onSuccess: () => toast(t("verifyEmailResent"), "success"),
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  return (
    <div className="mx-auto max-w-md py-8">
      <Card className="p-6 sm:p-8">
        <h1 className="font-display text-2xl font-extrabold text-forest">{t("verifyEmailTitle")}</h1>

        {status === "verifying" && (
          <div className="mt-6 flex flex-col items-center gap-3 py-6 text-center">
            <Spinner />
            <p className="text-sm text-muted">{t("verifyEmailVerifying")}</p>
          </div>
        )}

        {status === "success" && (
          <div className="mt-6 text-center">
            <CheckCircle2 className="mx-auto h-12 w-12 text-leaf" />
            <p className="mt-4 font-bold">{t("verifyEmailSuccess")}</p>
            <p className="mt-1 text-sm text-muted">{t("verifyEmailSuccessNote")}</p>
            <Button
              className="mt-6 w-full"
              size="lg"
              onClick={() => navigate(user ? roleHome(user.role) : "/login", { replace: true })}
            >
              {user ? t("continueToApp") : t("backToLogin")}
            </Button>
          </div>
        )}

        {status === "error" && (
          <div className="mt-6 text-center">
            <AlertCircle className="mx-auto h-12 w-12 text-[#a53f3f]" />
            <p className="mt-4 font-bold">{t("verifyEmailInvalid")}</p>
            {user ? (
              <>
                <p className="mt-1 text-sm text-muted">{t("emailNotVerifiedAction")}</p>
                <Button
                  className="mt-6 w-full"
                  size="lg"
                  loading={resend.isPending}
                  onClick={() => resend.mutate()}
                >
                  {t("verifyEmailResend")}
                </Button>
              </>
            ) : (
              <p className="mt-4 text-sm">
                <Link to="/login" className="font-bold text-leaf hover:underline">
                  {t("backToLogin")}
                </Link>
              </p>
            )}
          </div>
        )}

        {status === "no-token" && (
          <div className="mt-6 text-center">
            <MailCheck className="mx-auto h-12 w-12 text-muted" />
            <p className="mt-4 font-bold">{t("verifyEmailNoToken")}</p>
            <p className="mt-4 text-sm">
              <Link to="/login" className="font-bold text-leaf hover:underline">
                {t("backToLogin")}
              </Link>
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
