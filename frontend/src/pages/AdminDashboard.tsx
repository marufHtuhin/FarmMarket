import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Users, Package, ShoppingBasket, TrendingUp, Database, ScrollText } from "lucide-react";
import { adminApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { apiErrorMessage } from "../utils/format";
import { Button, Card, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { StatCard } from "../components/ui/misc";

const activityKindLabel: Record<string, "usersTitle" | "orders" | "products"> = {
  user: "usersTitle",
  order: "orders",
  product: "products",
};

export function AdminDashboardPage() {
  const { t, fmtNum, fmtDate } = useLang();
  const q = useQuery({ queryKey: ["admin-stats"], queryFn: adminApi.stats, retry: false });
  const s = q.data;

  return (
    <div>
      <PageHeader title={t("adminTitle")} sub={t("adminSub")} />
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label={t("totalUsers")} value={fmtNum(s?.total_users, 0)} icon={<Users className="h-5 w-5" />} />
          <StatCard label={t("products")} value={fmtNum(s?.total_products, 0)} icon={<ShoppingBasket className="h-5 w-5" />} tint="bg-sand" />
          <StatCard label={t("orders")} value={fmtNum(s?.total_orders, 0)} icon={<Package className="h-5 w-5" />} tint="bg-[#e6f4f1]" />
          <StatCard label={t("totalRevenue")} value={`৳${fmtNum(s?.total_revenue)}`} icon={<TrendingUp className="h-5 w-5" />} tint="bg-[#f2f8e3]" />
        </div>
      )}
      {s?.users_by_role && (
        <Card className="mt-6 p-5">
          <h2 className="font-display text-lg font-extrabold text-forest">{t("usersTitle")}</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(s.users_by_role).map(([role, count]) => (
              <span key={role} className="rounded-full bg-mint px-3.5 py-1.5 text-sm font-bold capitalize text-forest">
                {role}: {fmtNum(count, 0)}
              </span>
            ))}
          </div>
        </Card>
      )}
      {q.isSuccess && (
        <Card className="mt-6 p-5">
          <h2 className="font-display text-lg font-extrabold text-forest">{t("recentActivity")}</h2>
          {!s?.recent_activity?.length ? (
            <p className="mt-3 text-sm text-muted">{t("noRecentActivity")}</p>
          ) : (
            <ul className="mt-3 divide-y divide-border">
              {s.recent_activity.map((a, i) => (
                <li key={`${a.kind}-${a.title}-${i}`} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <span className="mr-2 rounded-full bg-mint px-2 py-0.5 text-xs font-bold text-forest">
                      {t(activityKindLabel[a.kind] ?? "orders")}
                    </span>
                    <span className="font-bold">{a.title}</span>
                    {a.detail && <span className="text-sm text-muted"> · {a.detail}</span>}
                  </div>
                  {a.created_at && (
                    <span className="shrink-0 text-xs text-muted">{fmtDate(a.created_at)}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      <Card className="mt-6 p-5">
        <h2 className="font-display text-lg font-extrabold text-forest">{t("quickActions")}</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link to="/admin/users">
            <Button variant="secondary">
              <Users className="h-4 w-4" /> {t("navAdminUsers")}
            </Button>
          </Link>
          <Link to="/admin/data-sources">
            <Button variant="secondary">
              <Database className="h-4 w-4" /> {t("navDataSources")}
            </Button>
          </Link>
          <Link to="/admin/audit-logs">
            <Button variant="secondary">
              <ScrollText className="h-4 w-4" /> {t("navAuditLogs")}
            </Button>
          </Link>
        </div>
      </Card>
    </div>
  );
}
