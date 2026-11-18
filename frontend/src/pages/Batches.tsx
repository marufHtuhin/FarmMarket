import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PlusCircle, QrCode } from "lucide-react";
import { forecastApi, twinApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { Modal } from "../components/ui/misc";
import { Field, Input, Select } from "../components/ui/fields";

function BatchForm({ onClose }: { onClose: () => void }) {
  const { t } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    crop: "tomato",
    origin_district: "",
    quantity_kg: 1,
    variety: "",
    harvested_at: "",
  });
  const hubsQ = useQuery({ queryKey: ["forecast-hubs"], queryFn: forecastApi.hubs, retry: false });
  const crops = hubsQ.data?.crops || [
    { id: "tomato", name: "Tomato" },
    { id: "potato", name: "Potato" },
    { id: "onion", name: "Onion" },
    { id: "banana", name: "Banana" },
    { id: "maize", name: "Maize" },
  ];

  const mutation = useMutation({
    mutationFn: () =>
      twinApi.create({
        crop: form.crop,
        origin_district: form.origin_district,
        quantity_kg: form.quantity_kg,
        variety: form.variety || undefined,
        harvested_at: form.harvested_at ? new Date(form.harvested_at).toISOString() : undefined,
      }),
    onSuccess: (res) => {
      toast(t("batchCreated"), "success");
      qc.invalidateQueries({ queryKey: ["batches-mine"] });
      onClose();
      navigate(`/batches/${res.batch_code}`);
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const valid = form.origin_district.trim() && form.quantity_kg > 0;
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) mutation.mutate();
      }}
    >
      <Field label={t("ti_crop")} required>
        <Select value={form.crop} onChange={(e) => setForm((f) => ({ ...f, crop: e.target.value }))}>
          {crops.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("ti_origin")} required>
          <Input value={form.origin_district} onChange={(e) => setForm((f) => ({ ...f, origin_district: e.target.value }))} required />
        </Field>
        <Field label={t("quantityKg")} required>
          <Input type="number" min={0.1} step={0.1} value={form.quantity_kg} onChange={(e) => setForm((f) => ({ ...f, quantity_kg: Number(e.target.value) }))} required />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("variety")}>
          <Input value={form.variety} onChange={(e) => setForm((f) => ({ ...f, variety: e.target.value }))} />
        </Field>
        <Field label={t("ti_harvested")}>
          <Input type="date" value={form.harvested_at} onChange={(e) => setForm((f) => ({ ...f, harvested_at: e.target.value }))} />
        </Field>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          {t("cancel")}
        </Button>
        <Button type="submit" loading={mutation.isPending} disabled={!valid}>
          {t("createBatch")}
        </Button>
      </div>
    </form>
  );
}

export function BatchesPage() {
  const { t, fmtNum, fmtDate } = useLang();
  const [formOpen, setFormOpen] = useState(false);
  const q = useQuery({ queryKey: ["batches-mine"], queryFn: twinApi.mine, retry: false });

  return (
    <div>
      <PageHeader
        title={t("batchesTitle")}
        sub={t("batchesSub")}
        action={
          <Button onClick={() => setFormOpen(true)}>
            <PlusCircle className="h-4 w-4" /> {t("createBatch")}
          </Button>
        }
      />
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && q.data.length === 0 && (
        <EmptyState
          icon={<QrCode className="h-10 w-10 text-leaf" />}
          title={t("noBatches")}
          action={<Button onClick={() => setFormOpen(true)}>{t("createBatch")}</Button>}
        />
      )}
      {q.isSuccess && q.data.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {q.data.map((b) => (
            <Link key={b.batch_code} to={`/batches/${b.batch_code}`}>
              <Card className="p-5 transition hover:-translate-y-0.5 hover:shadow-lift">
                <p className="font-mono text-xs font-bold text-leaf">{b.batch_code}</p>
                <h3 className="mt-2 font-display text-xl font-extrabold capitalize">{b.crop}</h3>
                <p className="mt-1 text-sm text-muted">
                  {fmtNum(b.quantity_kg)} kg · {b.created_at ? fmtDate(b.created_at) : ""}
                </p>
                <p className="mt-3 text-sm font-bold text-leaf">{t("view")} →</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={t("createBatch")}>
        <BatchForm onClose={() => setFormOpen(false)} />
      </Modal>
    </div>
  );
}
