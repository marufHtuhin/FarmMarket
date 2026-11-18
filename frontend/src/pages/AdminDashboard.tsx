import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Users, Package, ShoppingBasket, TrendingUp, Database, ScrollText } from "lucide-react";
import { adminApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { apiErrorMessage } from "../utils/format";
import { Button, Card, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { StatCard } from "../components/ui/misc";

export function AdminDashboardPage() {
  const { t, fmtNum } = useLang();
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
