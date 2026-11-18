import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Truck } from "lucide-react";
import { ordersApi, transportersApi } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage, unitLabel } from "../utils/format";
import { Button, Card, EmptyState, ErrorState, Spinner } from "../components/ui/core";
import { StatusBadge } from "../components/ui/misc";
import { Field, Select } from "../components/ui/fields";
import { MessageButton } from "../components/MessageButton";

export function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const orderId = Number(id);
  const { t, fmtNum, fmtDateTime, lang } = useLang();
  const { user } = useAuth();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [transporterId, setTransporterId] = useState("");

  // GET /orders/{id} is in the shared contract; fall back to /orders/my.
  const q = useQuery({
    queryKey: ["order", orderId],
    queryFn: async () => {
      try {
        return await ordersApi.get(orderId);
      } catch (e) {
        const status = (e as { response?: { status?: number } }).response?.status;
        if (status === 404) {
          const mine = await ordersApi.listMine();
          const found = mine.find((o) => o.id === orderId);
          if (found) return found;
        }
        throw e;
      }
    },
    enabled: Number.isFinite(orderId),
    retry: false,
  });

  // Public transporter directory (no contact details) — the backend lets the
  // order's farmer or an admin assign, so the picker must work for both.
  const transportersQ = useQuery({
    queryKey: ["transporters"],
    queryFn: () => transportersApi.list(),
    enabled: user?.role === "admin" || user?.role === "farmer",
    retry: false,
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => ordersApi.setStatus(orderId, status),
    onSuccess: () => {
      toast(t("updated"), "success");
      qc.invalidateQueries({ queryKey: ["order", orderId] });
      qc.invalidateQueries({ queryKey: ["orders"] });
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const assignMutation = useMutation({
    mutationFn: () => ordersApi.assign(orderId, Number(transporterId)),
    onSuccess: () => {
      toast(t("transporterAssigned"), "success");
      qc.invalidateQueries({ queryKey: ["order", orderId] });
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  if (q.isLoading) return <Spinner label={t("loading")} />;
  if (q.isError) return <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />;
  const o = q.data;
  if (!o)
    return (
      <EmptyState
        title={t("orderNotFound")}
        action={
          <Link to="/orders">
            <Button variant="secondary">{t("back")}</Button>
          </Link>
        }
      />
    );

  const transporters = transportersQ.data || [];
  const canAssign = (user?.role === "farmer" || user?.role === "admin") && o.status === "accepted";
  // The order's other party (nested buyer/farmer objects from GET /orders/{id}).
  const otherParty =
    user?.role === "farmer" ? o.buyer : user?.role === "buyer" ? o.farmer : undefined;

  return (
    <div className="mx-auto max-w-2xl">
      <Link to="/orders" className="mb-4 inline-flex items-center gap-2 text-sm font-bold text-leaf hover:underline">
        <ArrowLeft className="h-4 w-4" /> {t("back")}
      </Link>
      <Card className="p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl font-extrabold text-forest">
              {t("orderId")} #{o.id}
            </h1>
            <p className="mt-1 text-sm text-muted">
              {o.product_name} · {o.created_at ? fmtDateTime(o.created_at) : ""}
            </p>
          </div>
          <StatusBadge status={o.status} label={t(o.status)} />
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-2xl bg-cream px-4 py-3">
            <dt className="text-xs text-muted">{t("quantityLabel")}</dt>
            <dd className="font-bold">
              {fmtNum(o.quantity)} {unitLabel(o.unit, lang)}
            </dd>
          </div>
          <div className="rounded-2xl bg-cream px-4 py-3">
            <dt className="text-xs text-muted">{t("pricePerUnit")}</dt>
            <dd className="font-bold">৳{fmtNum(o.unit_price)}</dd>
          </div>
          <div className="rounded-2xl bg-cream px-4 py-3">
            <dt className="text-xs text-muted">{t("totalAmount")}</dt>
            <dd className="font-display text-lg font-extrabold text-leaf">৳{fmtNum(o.total_amount)}</dd>
          </div>
          <div className="rounded-2xl bg-cream px-4 py-3">
            <dt className="text-xs text-muted">{t("deliveryStatus")}</dt>
            <dd className="font-bold capitalize">{(o.delivery_status || "—").replace(/_/g, " ")}</dd>
          </div>
          {o.buyer?.name && (
            <div className="rounded-2xl bg-cream px-4 py-3">
              <dt className="text-xs text-muted">{t("buyerName")}</dt>
              <dd className="font-bold">{o.buyer.name}</dd>
            </div>
          )}
          {o.farmer?.name && (
            <div className="rounded-2xl bg-cream px-4 py-3">
              <dt className="text-xs text-muted">{t("farmerLabel")}</dt>
              <dd className="font-bold">{o.farmer.name}</dd>
            </div>
          )}
          {o.transporter?.name && (
            <div className="rounded-2xl bg-cream px-4 py-3">
              <dt className="text-xs text-muted">{t("transporterLabel")}</dt>
              <dd className="font-bold">{o.transporter.name}</dd>
            </div>
          )}
        </dl>
        {o.delivery_address && (
          <p className="mt-4 text-sm">
            {t("deliveryAddress")}: <b>{o.delivery_address}</b>
          </p>
        )}
        {o.product_id && (
          <Link to={`/marketplace/${o.product_id}`} className="mt-4 block text-sm font-bold text-leaf hover:underline">
            {t("viewProduct")} →
          </Link>
        )}

        <div className="mt-6 flex flex-wrap gap-2">
          {user?.role === "farmer" && o.status === "pending" && (
            <>
              <Button loading={statusMutation.isPending} onClick={() => statusMutation.mutate("accepted")}>
                {t("accept")}
              </Button>
              <Button variant="secondary" loading={statusMutation.isPending} onClick={() => statusMutation.mutate("rejected")}>
                {t("reject")}
              </Button>
            </>
          )}
          {user?.role === "farmer" && o.status === "accepted" && (
            <Button loading={statusMutation.isPending} onClick={() => statusMutation.mutate("completed")}>
              {t("complete")}
            </Button>
          )}
          {user?.role === "buyer" && o.status === "pending" && (
            <Button variant="secondary" loading={statusMutation.isPending} onClick={() => statusMutation.mutate("cancelled")}>
              {t("cancel")}
            </Button>
          )}
          {otherParty && (
            <MessageButton
              otherUserId={otherParty.id}
              listingId={o.product_id}
              offerId={o.offer_id}
              label={t(user?.role === "farmer" ? "messageBuyer" : "messageFarmer")}
            />
          )}
        </div>

        {canAssign && (
          <div className="mt-6 border-t border-line pt-5">
            <h2 className="flex items-center gap-2 font-display font-bold text-forest">
              <Truck className="h-5 w-5 text-leaf" /> {t("assignTransporter")}
            </h2>
            {transportersQ.isLoading ? (
              <Spinner />
            ) : transporters.length === 0 ? (
              <p className="mt-2 text-sm text-muted">{t("noTransporters")}</p>
            ) : (
              <div className="mt-3 flex flex-wrap items-end gap-3">
                <div className="min-w-[220px] flex-1">
                  <Field label={t("selectTransporter")}>
                    <Select value={transporterId} onChange={(e) => setTransporterId(e.target.value)}>
                      <option value="">{t("selectTransporter")}</option>
                      {transporters.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.name}
                          {u.district ? ` — ${u.district}` : ""}
                          {u.business_name ? ` (${u.business_name})` : ""}
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
                <Button loading={assignMutation.isPending} disabled={!transporterId} onClick={() => assignMutation.mutate()}>
                  {t("assignTransporter")}
                </Button>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
