import { useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useAuth, roleHome } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { loginSchema, type LoginForm } from "../utils/validation";
import { apiErrorMessage } from "../utils/format";
import { Card, Button } from "../components/ui/core";
import { Field, Input } from "../components/ui/fields";

export const DEMO_ACCOUNTS = [
  { labelKey: "demoFarmer", email: "farmer@farmmarket.demo", password: "Demo123!" },
  { labelKey: "demoBuyer", email: "buyer@farmmarket.demo", password: "Demo123!" },
];

export function LoginPage() {
  const { t } = useLang();
  const { login } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const [submitting, setSubmitting] = useState(false);
  const expired = params.get("expired") === "1";
  const from = (location.state as { from?: string } | null)?.from;

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<LoginForm>({ resolver: zodResolver(loginSchema) });

  const onSubmit = async (data: LoginForm) => {
    setSubmitting(true);
    try {
      const user = await login(data.email, data.password);
      toast(`${t("welcomeBack")}, ${user.name}`, "success");
      navigate(from || roleHome(user.role), { replace: true });
    } catch (e) {
      toast(apiErrorMessage(e), "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-md py-8">
      <Card className="p-6 sm:p-8">
        <h1 className="font-display text-2xl font-extrabold text-forest">{t("loginTitle")}</h1>
        <p className="mt-1 text-sm text-muted">{t("loginSubtitle")}</p>
        {expired && (
          <div className="mt-4 rounded-2xl border border-[#f4e4bf] bg-[#fff8e9] px-4 py-3 text-[13px] font-semibold text-[#80632d]">
            {t("sessionExpired")}
          </div>
        )}
        <form className="mt-6 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <Field label={t("email")} required error={errors.email ? t(errors.email.message as string) : undefined}>
            <Input type="email" autoComplete="email" placeholder="you@example.com" {...register("email")} />
          </Field>
          <Field label={t("password")} required error={errors.password ? t(errors.password.message as string) : undefined}>
            <Input type="password" autoComplete="current-password" {...register("password")} />
          </Field>
          <Button type="submit" loading={submitting} className="w-full" size="lg">
            {t("login")}
          </Button>
        </form>
        <div className="mt-4 text-center text-sm">
          <Link to="/forgot-password" className="font-bold text-leaf hover:underline">
            {t("forgotPassword")}
          </Link>
        </div>
        <div className="mt-6 border-t border-line pt-5">
          <p className="text-center text-xs font-bold uppercase tracking-wide text-muted">{t("demoAccounts")}</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {DEMO_ACCOUNTS.map((d) => (
              <Button
                key={d.email}
                variant="secondary"
                size="sm"
                onClick={() => {
                  setValue("email", d.email);
                  setValue("password", d.password);
                }}
              >
                {t(d.labelKey)}
              </Button>
            ))}
          </div>
          <p className="mt-2 text-center font-mono text-[11px] text-muted">Demo123!</p>
        </div>
        <p className="mt-6 text-center text-sm text-muted">
          {t("newHere")}{" "}
          <Link to="/register" className="font-bold text-leaf hover:underline">
            {t("registerLink")}
          </Link>
        </p>
      </Card>
    </div>
  );
}
