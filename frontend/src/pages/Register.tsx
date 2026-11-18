import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { MailCheck } from "lucide-react";
import { useAuth, roleHome } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { registerSchema, type RegisterForm } from "../utils/validation";
import { BD_DISTRICTS, upazilasForDistrict } from "../data/bd-locations";
import { apiErrorMessage } from "../utils/format";
import { Card, Button } from "../components/ui/core";
import { Field, Input, PasswordInput, Select } from "../components/ui/fields";

export function RegisterPage() {
  const { t, lang } = useLang();
  const { register: doRegister } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  // After signup the user stays on this page with a "check your email"
  // message instead of being bounced straight to the dashboard — the
  // confirmation link is the next step.
  const [registered, setRegistered] = useState<{ email: string; role: string } | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<RegisterForm>({ resolver: zodResolver(registerSchema) });

  // Dependent upazila select: options come from the chosen district, and
  // the upazila resets whenever the district changes.
  const selectedDistrict = watch("district") || "";
  const upazilaOptions = upazilasForDistrict(selectedDistrict);

  const err = (key?: string) => (key ? t(key) : undefined);

  const onSubmit = async (data: RegisterForm) => {
    setSubmitting(true);
    try {
      const { confirmPassword: _cp, ...payload } = data;
      const user = await doRegister(payload);
      setRegistered({ email: user.email, role: user.role });
    } catch (e) {
      toast(apiErrorMessage(e), "error");
    } finally {
      setSubmitting(false);
    }
  };

  if (registered) {
    return (
      <div className="mx-auto max-w-lg py-8">
        <Card className="p-6 text-center sm:p-8">
          <MailCheck className="mx-auto h-12 w-12 text-leaf" />
          <h1 className="mt-4 font-display text-2xl font-extrabold text-forest">{t("checkEmailTitle")}</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            {t("checkEmailBody", { email: registered.email })}
          </p>
          <p className="mt-2 text-xs text-muted">{t("checkEmailNote")}</p>
          <Button
            className="mt-6 w-full"
            size="lg"
            onClick={() => navigate(roleHome(registered.role), { replace: true })}
          >
            {t("continueToApp")}
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg py-8">
      <Card className="p-6 sm:p-8">
        <h1 className="font-display text-2xl font-extrabold text-forest">{t("registerTitle")}</h1>
        <p className="mt-1 text-sm text-muted">{t("registerSubtitle")}</p>
        <form className="mt-6 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <Field label={t("fullName")} required error={err(errors.name?.message)}>
            <Input type="text" autoComplete="name" {...register("name")} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("email")} required error={err(errors.email?.message)}>
              <Input type="email" autoComplete="email" {...register("email")} />
            </Field>
            <Field label={t("phone")}>
              <Input type="tel" autoComplete="tel" {...register("phone")} />
            </Field>
          </div>
          <Field label={t("selectRole")} required error={err(errors.role?.message)}>
            <Select defaultValue="" {...register("role")}>
              <option value="" disabled>
                {t("selectRole")}
              </option>
              <option value="farmer">{t("roleFarmer")}</option>
              <option value="buyer">{t("roleBuyer")}</option>
              <option value="transporter">{t("roleTransporter")}</option>
            </Select>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("password")} required error={err(errors.password?.message)}>
              <PasswordInput
                autoComplete="new-password"
                showLabel={t("showPassword")}
                hideLabel={t("hidePassword")}
                {...register("password")}
              />
            </Field>
            <Field label={t("confirmPassword")} required error={err(errors.confirmPassword?.message)}>
              <PasswordInput
                autoComplete="new-password"
                showLabel={t("showPassword")}
                hideLabel={t("hidePassword")}
                {...register("confirmPassword")}
              />
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("district")} required error={err(errors.district?.message)}>
              <Select
                defaultValue=""
                {...register("district", { onChange: () => setValue("upazila", "") })}
              >
                <option value="" disabled>
                  {t("selectDistrict")}
                </option>
                {BD_DISTRICTS.map((d) => (
                  <option key={d.en} value={d.en}>
                    {lang === "bn" ? d.bn : d.en}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("upazila")} error={err(errors.upazila?.message)}>
              <Select defaultValue="" disabled={!selectedDistrict} {...register("upazila")}>
                <option value="">
                  {selectedDistrict ? t("selectUpazila") : t("selectDistrictFirst")}
                </option>
                {upazilaOptions.map((u) => (
                  <option key={u.en} value={u.en}>
                    {lang === "bn" ? u.bn : u.en}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label={t("business")}>
            <Input type="text" {...register("business_name")} />
          </Field>
          <p className="text-xs leading-relaxed text-muted">{t("privacyNote")}</p>
          <Button type="submit" loading={submitting} className="w-full" size="lg">
            {t("registerLink")}
          </Button>
        </form>
        <p className="mt-6 text-center text-sm text-muted">
          {t("haveAccount")}{" "}
          <Link to="/login" className="font-bold text-leaf hover:underline">
            {t("login")}
          </Link>
        </p>
      </Card>
    </div>
  );
}
