import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Handshake } from "lucide-react";
import { offersApi } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { StatusBadge } from "../components/ui/misc";
import { MessageButton } from "../components/MessageButton";

type Tab = "incoming" | "mine";

export function OffersPage() {
  const { t, fmtNum, fmtDateTime } = useLang();
  const { user } = useAuth();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>(user?.role === "farmer" ? "incoming" : "mine");

  const q = useQuery({ queryKey: ["offers"], queryFn: offersApi.my, retry: false });

  const mutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "accepted" | "rejected" | "cancelled" }) =>
      offersApi.setStatus(id, status),
    onSuccess: (_d, vars) => {
      toast(
        t(vars.status === "accepted" ? "offerAccepted" : vars.status === "rejected" ? "offerRejected" : "offerCancelled"),
        "success"
      );
      qc.invalidateQueries({ queryKey: ["offers"] });
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const offers = q.data || [];
  // The contract's /offers/my returns the caller's offers; incoming offers for a
  // farmer are those on their products (farmer_id === me) and "mine" are the
  // ones the buyer placed (buyer_id === me). Fall back to showing all when the
  // backend does not split them.
  const incoming = offers.filter((o) => o.farmer_id === user?.id || (user?.role === "farmer" && o.buyer_id !== user?.id));
  const mine = offers.filter((o) => o.buyer_id === user?.id);
  const visible = tab === "incoming" ? (incoming.length ? incoming : user?.role === "farmer" ? offers : []) : mine.length ? mine : user?.role === "buyer" ? offers : [];

  return (
    <div>
      <PageHeader title={t("offersTitle")} sub={t("offersSub")} />
      <div className="mb-5 flex gap-2">
        {(
          [
            ["incoming", "incomingOffers"],
            ["mine", "myOffers"],
          ] as Array<[Tab, string]>
        ).map(([key, labelKey]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            aria-pressed={tab === key}
            className={`rounded-full px-4 py-2.5 text-sm font-bold shadow-sm transition ${
              tab === key ? "bg-forest text-white" : "border border-line bg-white text-[#506057] hover:border-leaf hover:text-forest"
            }`}
          >
            {t(labelKey)}
          </button>
        ))}
      </div>
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && visible.length === 0 && (
        <EmptyState icon={<Handshake className="h-10 w-10 text-leaf" />} title={t("noOffers")} />
      )}
      {q.isSuccess && visible.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((o) => (
            <Card key={o.id} className="p-5">
              <div className="flex items-start justify-between gap-2">
                <span className="text-xs text-muted">
                  {t("offerFor")} <b className="text-ink">{o.product_name || `#${o.product_id}`}</b>
                </span>
                <StatusBadge status={o.status} label={t(o.status)} />
              </div>
              <Link to={`/marketplace/${o.product_id}`} className="mt-2 block font-display text-xl font-extrabold hover:text-leaf">
                {o.product_name || `Product #${o.product_id}`}
              </Link>
              <p className="mt-1 text-xs text-muted">
                {t("offeredBy")}: {o.buyer_name || `#${o.buyer_id}`} · {o.created_at ? fmtDateTime(o.created_at) : ""}
              </p>
              <p className="mt-3 text-sm">
                {t("quantityLabel")}: <b>{fmtNum(o.quantity)}</b>
              </p>
              <p className="mt-1 font-display text-2xl font-extrabold text-leaf">৳{fmtNum(o.offered_price)}</p>
              {o.message && <p className="mt-2 text-[13px] leading-relaxed text-muted">{o.message}</p>}
              {((user?.role === "farmer" && o.buyer_id) || (user?.role === "buyer" && o.farmer_id)) && (
                <div className="mt-3">
                  <MessageButton
                    size="sm"
                    otherUserId={(user?.role === "farmer" ? o.buyer_id : o.farmer_id) as number}
                    listingId={o.product_id}
                    offerId={o.id}
                    label={t(user?.role === "farmer" ? "messageBuyer" : "messageFarmer")}
                  />
                </div>
              )}
              {o.status === "pending" && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {tab === "incoming" ? (
                    <>
                      <Button
                        size="sm"
                        loading={mutation.isPending}
                        onClick={() => mutation.mutate({ id: o.id, status: "accepted" })}
                      >
                        {t("acceptOffer")}
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={mutation.isPending}
                        onClick={() => mutation.mutate({ id: o.id, status: "rejected" })}
                      >
                        {t("rejectOffer")}
                      </Button>
                    </>
                  ) : (
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={mutation.isPending}
                      onClick={() => mutation.mutate({ id: o.id, status: "cancelled" })}
                    >
                      {t("cancelOffer")}
                    </Button>
                  )}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
