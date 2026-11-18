import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Car, PlusCircle, Snowflake, Trash2 } from "lucide-react";
import { vehiclesApi, type Vehicle, type VehicleIn } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { Modal } from "../components/ui/misc";
import { Field, Input } from "../components/ui/fields";

function VehicleForm({ onClose }: { onClose: () => void }) {
  const { t } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [form, setForm] = useState<VehicleIn>({ vehicle_type: "", capacity_kg: 400, plate_number: "", refrigerated: false });

  const mutation = useMutation({
    mutationFn: () => vehiclesApi.create(form),
    onSuccess: () => {
      toast(t("vehicleAdded"), "success");
      qc.invalidateQueries({ queryKey: ["vehicles"] });
      onClose();
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const valid = form.vehicle_type.trim() && form.capacity_kg > 0;
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) mutation.mutate();
      }}
    >
      <Field label={t("vehicleType")} required>
        <Input value={form.vehicle_type} onChange={(e) => setForm((f) => ({ ...f, vehicle_type: e.target.value }))} required />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("capacityKg")} required>
          <Input type="number" min={1} value={form.capacity_kg} onChange={(e) => setForm((f) => ({ ...f, capacity_kg: Number(e.target.value) }))} required />
        </Field>
        <Field label={t("plateNumber")}>
          <Input value={form.plate_number || ""} onChange={(e) => setForm((f) => ({ ...f, plate_number: e.target.value }))} />
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm font-bold">
        <input
          type="checkbox"
          checked={form.refrigerated}
          onChange={(e) => setForm((f) => ({ ...f, refrigerated: e.target.checked }))}
          className="h-5 w-5 accent-[#1E7A4C]"
        />
        {t("refrigerated")}
      </label>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          {t("cancel")}
        </Button>
        <Button type="submit" loading={mutation.isPending} disabled={!valid}>
          {t("addVehicle")}
        </Button>
      </div>
    </form>
  );
}

export function VehiclesPage() {
  const { t, fmtNum } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [deleting, setDeleting] = useState<Vehicle | null>(null);

  const q = useQuery({ queryKey: ["vehicles"], queryFn: vehiclesApi.list, retry: false });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => vehiclesApi.remove(id),
    onSuccess: () => {
      toast(t("vehicleDeleted"), "success");
      qc.invalidateQueries({ queryKey: ["vehicles"] });
      setDeleting(null);
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  return (
    <div>
      <PageHeader
        title={t("vehiclesTitle")}
        sub={t("vehiclesSub")}
        action={
          <Button onClick={() => setFormOpen(true)}>
            <PlusCircle className="h-4 w-4" /> {t("addVehicle")}
          </Button>
        }
      />
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && q.data.length === 0 && (
        <EmptyState
          icon={<Car className="h-10 w-10 text-leaf" />}
          title={t("noVehicles")}
          action={<Button onClick={() => setFormOpen(true)}>{t("addVehicle")}</Button>}
        />
      )}
      {q.isSuccess && q.data.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {q.data.map((v) => (
            <Card key={v.id} className="p-5">
              <div className="flex items-start justify-between gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-2xl bg-mint text-leaf">
                  <Car className="h-5 w-5" />
                </span>
                <button
                  type="button"
                  aria-label={t("delete")}
                  onClick={() => setDeleting(v)}
                  className="rounded-full p-2 text-muted hover:bg-cream hover:text-red-700"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
              <h3 className="mt-3 font-display text-lg font-extrabold text-forest">
                {v.vehicle_type || v.type || `Vehicle #${v.id}`}
              </h3>
              <p className="mt-1 text-sm text-muted">
                {t("capacityKg")}: <b className="text-ink">{fmtNum(v.capacity_kg, 0)} kg</b>
              </p>
              {v.plate_number && <p className="text-sm text-muted">{v.plate_number}</p>}
              {v.refrigerated && (
                <p className="mt-2 inline-flex items-center gap-1 rounded-full bg-[#e3eefc] px-2.5 py-1 text-[11px] font-extrabold text-[#1d4ed8]">
                  <Snowflake className="h-3.5 w-3.5" /> {t("refrigerated")}
                </p>
              )}
            </Card>
          ))}
        </div>
      )}
      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={t("addVehicle")}>
        <VehicleForm onClose={() => setFormOpen(false)} />
      </Modal>
      <Modal open={!!deleting} onClose={() => setDeleting(null)} title={t("delete")}>
        <p className="text-sm text-muted">{t("deleteVehicleConfirm")}</p>
        <p className="mt-2 font-bold">{deleting?.vehicle_type || deleting?.type || `#${deleting?.id}`}</p>
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
