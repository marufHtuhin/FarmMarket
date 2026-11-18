import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, PlusCircle, Trash2 } from "lucide-react";
import { productsApi, type Product } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage, unitLabel } from "../utils/format";
import { productPhoto } from "../utils/crops";
import { Button, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { Modal } from "../components/ui/misc";
import { ListingForm } from "../components/ListingForm";

export function MyListingsPage() {
  const { t, fmtNum, lang } = useLang();
  const { user } = useAuth();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<Product | null>(null);
  const [deleting, setDeleting] = useState<Product | null>(null);

  const q = useQuery({ queryKey: ["products"], queryFn: () => productsApi.list() });
  const mine = (q.data || []).filter((p) => p.farmer_id === user?.id);

  const deleteMutation = useMutation({
    mutationFn: (id: number) => productsApi.remove(id),
    onSuccess: () => {
      toast(t("listingDeleted"), "success");
      qc.invalidateQueries({ queryKey: ["products"] });
      setDeleting(null);
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  return (
    <div>
      <PageHeader
        title={t("myListings")}
        sub={t("myListingsSub")}
        action={
          <Link to="/listings/new">
            <Button>
              <PlusCircle className="h-4 w-4" /> {t("newListing")}
            </Button>
          </Link>
        }
      />
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && mine.length === 0 && (
        <EmptyState
          title={t("noListings")}
          action={
            <Link to="/listings/new">
              <Button>{t("publishFirst")}</Button>
            </Link>
          }
        />
      )}
      {q.isSuccess && mine.length > 0 && (
        <div className="overflow-hidden rounded-3xl border border-line bg-white shadow-card">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-line bg-cream text-xs uppercase tracking-wide text-muted">
                  <th className="px-4 py-3">{t("productName")}</th>
                  <th className="px-4 py-3">{t("quantity")}</th>
                  <th className="px-4 py-3">{t("price")}</th>
                  <th className="px-4 py-3">{t("districtLabel")}</th>
                  <th className="px-4 py-3">{t("status")}</th>
                  <th className="px-4 py-3 text-right">{t("edit")}</th>
                </tr>
              </thead>
              <tbody>
                {mine.map((p) => {
                  const img = (p.image_url && /^https?:\/\//i.test(p.image_url) ? p.image_url : null) || productPhoto(p.name);
                  return (
                    <tr key={p.id} className="border-b border-line last:border-0">
                      <td className="px-4 py-3">
                        <Link to={`/marketplace/${p.id}`} className="flex items-center gap-3 font-bold hover:text-leaf">
                          {img ? (
                            <img src={img} alt="" className="h-11 w-11 shrink-0 rounded-xl object-cover" />
                          ) : (
                            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-mint text-xl">🥬</span>
                          )}
                          <span className="min-w-0 truncate">{p.name}</span>
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        {fmtNum(p.quantity)} {unitLabel(p.unit, lang)}
                      </td>
                      <td className="px-4 py-3 font-bold">৳{fmtNum(p.price_per_unit)}</td>
                      <td className="px-4 py-3">{p.district}</td>
                      <td className="px-4 py-3">
                        <span className="capitalize">{p.status || "available"}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            aria-label={t("edit")}
                            onClick={() => setEditing(p)}
                            className="rounded-full p-2 text-muted hover:bg-cream hover:text-ink"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            aria-label={t("delete")}
                            onClick={() => setDeleting(p)}
                            className="rounded-full p-2 text-muted hover:bg-cream hover:text-red-700"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <Modal open={!!editing} onClose={() => setEditing(null)} title={t("editListing")} wide>
        {editing && <ListingForm product={editing} onDone={() => setEditing(null)} />}
      </Modal>
      <Modal open={!!deleting} onClose={() => setDeleting(null)} title={t("delete")}>
        <p className="text-sm text-muted">{t("deleteListingConfirm")}</p>
        <p className="mt-2 font-bold">{deleting?.name}</p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setDeleting(null)}>
            {t("cancel")}
          </Button>
          <Button variant="danger" loading={deleteMutation.isPending} onClick={() => deleting && deleteMutation.mutate(deleting.id)}>
            {t("delete")}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
