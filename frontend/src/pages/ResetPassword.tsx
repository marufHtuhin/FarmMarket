import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { authApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Card, Button } from "../components/ui/core";
import { Field, PasswordInput } from "../components/ui/fields";

export function ResetPasswordPage() {
  const { t } = useLang();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const mutation = useMutation({
    mutationFn: () => authApi.resetPassword(token, password),
    onSuccess: () => {
      toast(t("passwordResetDone"), "success");
      navigate("/login", { replace: true });
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const valid = token.length > 0 && password.length >= 6 && password === confirm;

  return (
    <div className="mx-auto max-w-md py-8">
      <Card className="p-6 sm:p-8">
        <h1 className="font-display text-2xl font-extrabold text-forest">{t("resetPassword")}</h1>
        <p className="mt-1 text-sm text-muted">{t("resetSubtitle")}</p>
        {!token && (
          <div className="mt-4 rounded-2xl border border-[#f1c4c4] bg-[#fceaea] px-4 py-3 text-[13px] font-semibold text-[#a53f3f]">
            {t("invalidResetLink")}
          </div>
        )}
        <form
          className="mt-6 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid) mutation.mutate();
          }}
        >
          <Field label={t("newPassword")} required error={password && password.length < 6 ? t("minChars6") : undefined}>
            <PasswordInput
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              showLabel={t("showPassword")}
              hideLabel={t("hidePassword")}
              required
            />
          </Field>
          <Field
            label={t("confirmPassword")}
            required
            error={confirm && password !== confirm ? t("passwordsMismatch") : undefined}
          >
            <PasswordInput
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              showLabel={t("showPassword")}
              hideLabel={t("hidePassword")}
              required
            />
          </Field>
          <Button type="submit" loading={mutation.isPending} disabled={!valid} className="w-full" size="lg">
            {t("resetPassword")}
          </Button>
        </form>
        <p className="mt-6 text-center text-sm">
          <Link to="/login" className="font-bold text-leaf hover:underline">
            {t("backToLogin")}
          </Link>
        </p>
      </Card>
    </div>
  );
}
