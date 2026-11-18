import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PackageCheck } from "lucide-react";
import { deliveriesApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { Modal, StatusBadge } from "../components/ui/misc";
import { Field, Textarea } from "../components/ui/fields";

// Allowed transitions mirror the backend (deliveries.ALLOWED_TRANSITIONS):
// assigned -> picked_up; picked_up -> in_transit | delivered; in_transit -> delivered.
const NEXT_STATUS: Record<string, { status: string; labelKey: string }[]> = {
  assigned: [{ status: "picked_up", labelKey: "markPickedUp" }],
  picked_up: [
    { status: "in_transit", labelKey: "markInTransit" },
    { status: "delivered", labelKey: "markDelivered" },
  ],
  in_transit: [{ status: "delivered", labelKey: "markDelivered" }],
};

export function DeliveriesPage() {
  const { t, fmtNum } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [proofFor, setProofFor] = useState<{ orderId: number; status: string } | null>(null);
  const [proofNote, setProofNote] = useState("");

  const q = useQuery({ queryKey: ["deliveries"], queryFn: deliveriesApi.list, retry: false });

  const mutation = useMutation({
    mutationFn: ({ orderId, status, note }: { orderId: number; status: string; note?: string }) =>
      deliveriesApi.setStatus(orderId, status, note),
    onSuccess: () => {
      toast(t("updatedMsg"), "success");
      qc.invalidateQueries({ queryKey: ["deliveries"] });
      setProofFor(null);
      setProofNote("");
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  return (
    <div>
      <PageHeader title={t("deliveriesTitle")} sub={t("deliveriesSub")} />
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && q.data.length === 0 && (
        <EmptyState icon={<PackageCheck className="h-10 w-10 text-leaf" />} title={t("noDeliveries")} />
      )}
      {q.isSuccess && q.data.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {q.data.map((d) => (
            <Card key={d.order_id} className="p-5">
              <div className="flex items-start justify-between gap-2">
                <b>
                  #{d.order_id} · {d.product_name || ""}
                </b>
                <StatusBadge status={d.delivery_status} label={d.delivery_status.replace(/_/g, " ")} />
              </div>
              <p className="mt-2 text-sm text-muted">
                {d.quantity !== undefined ? `${fmtNum(d.quantity)} ${d.unit || ""}` : ""}
                {d.district ? ` · ${d.district}` : ""}
              </p>
              {(d.farmer_name || d.buyer_name) && (
                <p className="mt-1 text-xs text-muted">
                  {d.farmer_name ? `${t("farmerLabel")}: ${d.farmer_name}` : ""}
                  {d.buyer_name ? ` → ${t("buyerLabel")}: ${d.buyer_name}` : ""}
                </p>
              )}
              {d.delivery_address && <p className="mt-2 text-[13px]">{d.delivery_address}</p>}
              {d.proof_note && (
                <p className="mt-2 rounded-2xl bg-cream px-3 py-2 text-[13px] text-muted">
                  {t("proofNote")}: {d.proof_note}
                </p>
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                {(NEXT_STATUS[d.delivery_status] || []).map((n) => (
                  <Button
                    key={n.status}
                    size="sm"
                    variant={n.status === "delivered" ? "primary" : "secondary"}
                    loading={mutation.isPending}
                    onClick={() => {
                      if (n.status === "delivered") {
                        setProofFor({ orderId: d.order_id, status: n.status });
                      } else {
                        mutation.mutate({ orderId: d.order_id, status: n.status });
                      }
                    }}
                  >
                    {t(n.labelKey)}
                  </Button>
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
      <Modal open={!!proofFor} onClose={() => setProofFor(null)} title={t("markDelivered")}>
        <Field label={t("proofNote")}>
          <Textarea
            rows={3}
            value={proofNote}
            onChange={(e) => setProofNote(e.target.value)}
            placeholder={t("proofNote")}
          />
        </Field>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setProofFor(null)}>
            {t("cancel")}
          </Button>
          <Button
            loading={mutation.isPending}
            onClick={() =>
              proofFor && mutation.mutate({ orderId: proofFor.orderId, status: proofFor.status, note: proofNote || undefined })
            }
          >
            {t("markDelivered")}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
