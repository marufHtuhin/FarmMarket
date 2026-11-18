import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, PlusCircle, Sprout, Trash2 } from "lucide-react";
import { farmsApi, metaApi, type Farm, type FarmIn } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage, isNotFound } from "../utils/format";
import { FALLBACK_COUNTRIES } from "../utils/geo";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { Modal } from "../components/ui/misc";
import { Field, Input, Select } from "../components/ui/fields";

function FarmForm({ farm, onClose }: { farm?: Farm | null; onClose: () => void }) {
  const { t } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [form, setForm] = useState<FarmIn>({
    name: farm?.name || "",
    district: farm?.district || "",
    upazila: farm?.upazila || "",
    area_acres: farm?.area_acres ?? undefined,
    country_code: farm?.country_code || "BD",
  });
  const countriesQ = useQuery({ queryKey: ["countries"], queryFn: metaApi.countries, retry: false });
  const countries = countriesQ.data || FALLBACK_COUNTRIES;

  const mutation = useMutation({
    mutationFn: () => (farm ? farmsApi.update(farm.id, form) : farmsApi.create(form)),
    onSuccess: () => {
      toast(t(farm ? "farmUpdated" : "farmCreated"), "success");
      qc.invalidateQueries({ queryKey: ["farms"] });
      onClose();
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const set = (k: keyof FarmIn, v: string | number | undefined) => setForm((f) => ({ ...f, [k]: v }));
  const valid = form.name.trim() && form.district.trim();

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) mutation.mutate();
      }}
    >
      <Field label={t("farmName")} required>
        <Input value={form.name} onChange={(e) => set("name", e.target.value)} required />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("district")} required>
          <Input value={form.district} onChange={(e) => set("district", e.target.value)} required />
        </Field>
        <Field label={t("upazilaLabel")}>
          <Input value={form.upazila || ""} onChange={(e) => set("upazila", e.target.value)} />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("areaAcres")}>
          <Input
            type="number"
            min={0.01}
            step={0.01}
            value={form.area_acres ?? ""}
            onChange={(e) => set("area_acres", e.target.value ? Number(e.target.value) : undefined)}
          />
        </Field>
        <Field label={t("country")}>
          <Select value={form.country_code || "BD"} onChange={(e) => set("country_code", e.target.value)}>
            {countries.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          {t("cancel")}
        </Button>
        <Button type="submit" loading={mutation.isPending} disabled={!valid}>
          {t("save")}
        </Button>
      </div>
    </form>
  );
}

export function FarmsPage() {
  const { t, fmtNum } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Farm | null>(null);
  const [deleting, setDeleting] = useState<Farm | null>(null);

  const q = useQuery({ queryKey: ["farms"], queryFn: farmsApi.list, retry: false });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => farmsApi.remove(id),
    onSuccess: () => {
      toast(t("farmDeleted"), "success");
      qc.invalidateQueries({ queryKey: ["farms"] });
      setDeleting(null);
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  return (
    <div>
      <PageHeader
        title={t("farmsTitle")}
        sub={t("farmsSub")}
        action={
          <Button
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            <PlusCircle className="h-4 w-4" /> {t("addFarm")}
          </Button>
        }
      />
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && (
        <ErrorState
          message={isNotFound(q.error) ? t("errorGeneric") : apiErrorMessage(q.error)}
          onRetry={() => q.refetch()}
        />
      )}
      {q.isSuccess && q.data.length === 0 && (
        <EmptyState
          icon={<Sprout className="h-10 w-10 text-leaf" />}
          title={t("noFarms")}
          action={
            <Button
              onClick={() => {
                setEditing(null);
                setFormOpen(true);
              }}
            >
              {t("addFarm")}
            </Button>
          }
        />
      )}
      {q.isSuccess && q.data.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {q.data.map((f) => (
            <Card key={f.id} className="p-5">
              <div className="flex items-start justify-between gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-2xl bg-mint text-leaf">
                  <Sprout className="h-5 w-5" />
                </span>
                <div className="flex gap-1">
                  <button
                    type="button"
                    aria-label={t("edit")}
                    onClick={() => {
                      setEditing(f);
                      setFormOpen(true);
                    }}
                    className="rounded-full p-2 text-muted hover:bg-cream hover:text-ink"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    aria-label={t("delete")}
                    onClick={() => setDeleting(f)}
                    className="rounded-full p-2 text-muted hover:bg-cream hover:text-red-700"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <h3 className="mt-3 font-display text-lg font-extrabold text-forest">{f.name}</h3>
              <p className="mt-1 text-sm text-muted">
                {f.district}
                {f.upazila ? `, ${f.upazila}` : ""}
                {f.country_code ? ` · ${f.country_code}` : ""}
              </p>
              {f.area_acres !== null && f.area_acres !== undefined && (
                <p className="mt-2 text-sm">
                  {t("areaAcres")}: <b>{fmtNum(f.area_acres)}</b>
                </p>
              )}
            </Card>
          ))}
        </div>
      )}
      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={t(editing ? "editFarm" : "addFarm")}
      >
        <FarmForm farm={editing} onClose={() => setFormOpen(false)} />
      </Modal>
      <Modal open={!!deleting} onClose={() => setDeleting(null)} title={t("delete")}>
        <p className="text-sm text-muted">{t("deleteFarmConfirm")}</p>
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
