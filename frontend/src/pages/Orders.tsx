import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Package } from "lucide-react";
import { ordersApi } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage, unitLabel } from "../utils/format";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { StatusBadge } from "../components/ui/misc";

export function OrdersPage() {
  const { t, fmtNum, fmtDateTime, lang } = useLang();
  const { user } = useAuth();
  const { toast } = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["orders"], queryFn: ordersApi.listMine });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => ordersApi.setStatus(id, status),
    onSuccess: () => {
      toast(t("updated"), "success");
      qc.invalidateQueries({ queryKey: ["orders"] });
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  return (
    <div>
      <PageHeader title={t("myOrders")} sub={t("orderSub")} />
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && q.data.length === 0 && (
        <EmptyState
          icon={<Package className="h-10 w-10 text-leaf" />}
          title={t("noOrders")}
          action={
            user?.role === "buyer" ? (
              <Link to="/marketplace">
                <Button>{t("exploreMarket")}</Button>
              </Link>
            ) : undefined
          }
        />
      )}
      {q.isSuccess && q.data.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {q.data.map((o) => (
            <Card key={o.id} className="p-5 transition hover:-translate-y-0.5 hover:shadow-lift">
              <div className="flex items-start justify-between gap-2.5">
                <Link to={`/orders/${o.id}`} className="font-bold hover:text-leaf">
                  #{o.id} · {o.product_name}
                </Link>
                <StatusBadge status={o.status} label={t(o.status)} />
              </div>
              <p className="mt-2 text-xs text-muted">
                {fmtNum(o.quantity)} {unitLabel(o.unit, lang)} × ৳{fmtNum(o.unit_price)}
                {o.created_at ? ` · ${fmtDateTime(o.created_at)}` : ""}
              </p>
              <h3 className="my-2 font-display text-xl font-extrabold">৳{fmtNum(o.total_amount)}</h3>
              {user?.role === "farmer" && o.status === "pending" && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" loading={statusMutation.isPending} onClick={() => statusMutation.mutate({ id: o.id, status: "accepted" })}>
                    {t("accept")}
                  </Button>
                  <Button variant="secondary" size="sm" loading={statusMutation.isPending} onClick={() => statusMutation.mutate({ id: o.id, status: "rejected" })}>
                    {t("reject")}
                  </Button>
                </div>
              )}
              {user?.role === "farmer" && o.status === "accepted" && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" loading={statusMutation.isPending} onClick={() => statusMutation.mutate({ id: o.id, status: "completed" })}>
                    {t("complete")}
                  </Button>
                </div>
              )}
              {user?.role === "buyer" && o.status === "pending" && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button variant="secondary" size="sm" loading={statusMutation.isPending} onClick={() => statusMutation.mutate({ id: o.id, status: "cancelled" })}>
                    {t("cancel")}
                  </Button>
                </div>
              )}
              <Link to={`/orders/${o.id}`} className="mt-3 block text-sm font-bold text-leaf hover:underline">
                {t("orderDetail")} →
              </Link>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
