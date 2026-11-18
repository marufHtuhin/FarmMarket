import { Link, useNavigate } from "react-router-dom";
import { BadgeCheck, LogOut, User } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { Button, Card, PageHeader } from "../components/ui/core";
import { Badge } from "../components/ui/misc";
import { LanguageToggle } from "../components/layout/brand";

export function ProfilePage() {
  const { t, fmtDate } = useLang();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  if (!user) return null;

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title={t("profileTitle")} />
      <Card className="p-6">
        <div className="flex items-center gap-4">
          <span className="grid h-16 w-16 place-items-center rounded-full bg-leaf font-display text-2xl font-extrabold text-white">
            {user.name.charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0">
            <h2 className="truncate font-display text-xl font-extrabold text-forest">{user.name}</h2>
            <p className="truncate text-sm text-muted">{user.email}</p>
            <p className="mt-1">
              {user.is_verified ? (
                <Badge tone="green">
                  <BadgeCheck className="h-3.5 w-3.5" /> {t("verifiedBadge")}
                </Badge>
              ) : (
                <Badge tone="gray">{t("notVerified")}</Badge>
              )}
            </p>
          </div>
        </div>
        <dl className="mt-6 grid gap-3 text-sm sm:grid-cols-2">
          <div className="rounded-2xl bg-cream px-4 py-3">
            <dt className="text-xs text-muted">{t("selectRole")}</dt>
            <dd className="font-bold capitalize">{user.role}</dd>
          </div>
          <div className="rounded-2xl bg-cream px-4 py-3">
            <dt className="text-xs text-muted">{t("phone")}</dt>
            <dd className="font-bold">{user.phone || "—"}</dd>
          </div>
          <div className="rounded-2xl bg-cream px-4 py-3">
            <dt className="text-xs text-muted">{t("district")}</dt>
            <dd className="font-bold">{user.district || "—"}</dd>
          </div>
          <div className="rounded-2xl bg-cream px-4 py-3">
            <dt className="text-xs text-muted">{t("upazila")}</dt>
            <dd className="font-bold">{user.upazila || "—"}</dd>
          </div>
          {user.business_name && (
            <div className="rounded-2xl bg-cream px-4 py-3">
              <dt className="text-xs text-muted">{t("business")}</dt>
              <dd className="font-bold">{user.business_name}</dd>
            </div>
          )}
          {user.created_at && (
            <div className="rounded-2xl bg-cream px-4 py-3">
              <dt className="text-xs text-muted">{t("memberSince")}</dt>
              <dd className="font-bold">{fmtDate(user.created_at)}</dd>
            </div>
          )}
        </dl>
      </Card>

      <Card className="mt-5 p-6">
        <h2 className="font-display text-lg font-extrabold text-forest">{t("accountSettings")}</h2>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <span className="text-sm font-bold">{t("changeLanguage")}</span>
          <LanguageToggle />
        </div>
        <div className="mt-5 flex flex-wrap gap-3 border-t border-line pt-5">
          <Link to="/dashboard">
            <Button variant="secondary">
              <User className="h-4 w-4" /> {t("dashboard")}
            </Button>
          </Link>
          <Button
            variant="danger"
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
          >
            <LogOut className="h-4 w-4" /> {t("logout")}
          </Button>
        </div>
      </Card>
    </div>
  );
}
