import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ImagePlus, X } from "lucide-react";
import { farmsApi, forecastApi, metaApi, productsApi, type Product, type ProductIn } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { listingSchema, type ListingForm as ListingFormValues } from "../utils/validation";
import { apiErrorMessage, apiStatus } from "../utils/format";
import { Button } from "../components/ui/core";
import { Field, Input, Select, Textarea } from "../components/ui/fields";

const FALLBACK_CROPS = ["tomato", "potato", "onion", "banana", "maize", "rice", "mango", "brinjal", "chili", "cauliflower", "jute"];

const MAX_IMAGES = 5;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

export function ListingForm({
  product,
  onDone,
}: {
  product?: Product | null;
  onDone: () => void;
}) {
  const { t } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [customCrop, setCustomCrop] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const cropsQ = useQuery({ queryKey: ["crops"], queryFn: metaApi.crops, retry: false });
  const hubsQ = useQuery({
    queryKey: ["forecast-hubs"],
    queryFn: forecastApi.hubs,
    enabled: !cropsQ.data && cropsQ.isError,
    retry: false,
  });
  const farmsQ = useQuery({ queryKey: ["farms"], queryFn: farmsApi.list, retry: false });

  const cropOptions: Array<{ id: string; name: string }> = cropsQ.data
    ? cropsQ.data.map((c) => ({ id: c.id, name: c.name }))
    : hubsQ.data
      ? hubsQ.data.crops.map((c) => ({ id: c.id, name: c.name }))
      : FALLBACK_CROPS.map((c) => ({ id: c, name: c.charAt(0).toUpperCase() + c.slice(1) }));

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<ListingFormValues>({
    resolver: zodResolver(listingSchema),
    defaultValues: product
      ? {
          name: product.name,
          quantity: product.quantity,
          unit: (product.unit as ListingFormValues["unit"]) || "kg",
          price_per_unit: product.price_per_unit,
          district: product.district,
          harvest_date: product.harvest_date || "",
          available_until: product.available_until || "",
          description: product.description || "",
          image_url: product.image_url || "",
        }
      : { unit: "kg" },
  });

  const nameValue = watch("name");
  useEffect(() => {
    if (product && !cropOptions.some((c) => c.name.toLowerCase() === product.name.toLowerCase() || c.id === product.name.toLowerCase())) {
      setCustomCrop(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product]);

  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);

  const mutation = useMutation({
    mutationFn: async (values: ListingFormValues) => {
      const payload: ProductIn = {
        name: values.name.trim(),
        quantity: values.quantity,
        unit: values.unit,
        price_per_unit: values.price_per_unit,
        district: values.district.trim(),
        harvest_date: values.harvest_date || null,
        available_until: values.available_until || null,
        description: values.description || "",
        image_url: values.image_url || "",
        farm_id: values.farm_id || undefined,
      };
      let id: number;
      if (product) {
        await productsApi.update(product.id, payload);
        id = product.id;
      } else {
        const res = await productsApi.create(payload);
        id = res.id;
      }
      if (files.length > 0) {
        try {
          setUploadPct(0);
          await productsApi.uploadImages(id, files, setUploadPct);
        } catch (e) {
          if (apiStatus(e) === 404) {
            toast(t("errorGeneric"), "error");
          } else {
            toast(apiErrorMessage(e), "error");
          }
        } finally {
          setUploadPct(null);
        }
      }
      return id;
    },
    onSuccess: () => {
      toast(t(product ? "listingUpdated" : "listingCreated"), "success");
      qc.invalidateQueries({ queryKey: ["products"] });
      onDone();
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const onFiles = (list: FileList | null) => {
    if (!list) return;
    const picked = [...list];
    if (files.length + picked.length > MAX_IMAGES) {
      toast(t("maxImages"), "error");
      return;
    }
    for (const f of picked) {
      if (!ALLOWED_TYPES.includes(f.type)) {
        toast(t("imageTypeError"), "error");
        return;
      }
      if (f.size > MAX_IMAGE_BYTES) {
        toast(t("imageTooBig"), "error");
        return;
      }
    }
    setFiles((prev) => [...prev, ...picked]);
    setPreviews((prev) => [...prev, ...picked.map((f) => URL.createObjectURL(f))]);
  };

  const removeFile = (i: number) => {
    setFiles((prev) => prev.filter((_, j) => j !== i));
    setPreviews((prev) => {
      URL.revokeObjectURL(prev[i]);
      return prev.filter((_, j) => j !== i);
    });
  };

  const err = (key?: string) => (key ? t(key) : undefined);

  return (
    <form className="space-y-4" onSubmit={handleSubmit((v) => mutation.mutate(v))} noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("selectCrop")} required error={err(errors.name?.message)}>
          {customCrop ? (
            <Input
              placeholder={t("productName")}
              {...register("name")}
            />
          ) : (
            <Select
              defaultValue={nameValue || ""}
              onChange={(e) => {
                if (e.target.value === "__other") {
                  setCustomCrop(true);
                  setValue("name", "");
                } else {
                  setValue("name", e.target.value, { shouldValidate: true });
                }
              }}
            >
              <option value="" disabled>
                {t("selectCrop")}
              </option>
              {cropOptions.map((c) => (
                <option key={c.id} value={c.name}>
                  {c.name}
                </option>
              ))}
              <option value="__other">{t("catOther")}…</option>
            </Select>
          )}
        </Field>
        <Field label={t("selectFarm")}>
          <Select
            defaultValue=""
            onChange={(e) => setValue("farm_id", e.target.value ? Number(e.target.value) : undefined)}
          >
            <option value="">{t("selectFarm")}</option>
            {(farmsQ.data || []).map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} — {f.district}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label={t("quantity")} required error={err(errors.quantity?.message)}>
          <Input type="number" min={0.1} step={0.1} {...register("quantity", { valueAsNumber: true })} />
        </Field>
        <Field label={t("unit")} required>
          <Select {...register("unit")}>
            <option value="kg">kg</option>
            <option value="quintal">quintal</option>
            <option value="ton">ton</option>
            <option value="piece">piece</option>
          </Select>
        </Field>
        <Field label={t("price")} required error={err(errors.price_per_unit?.message)}>
          <Input type="number" min={0.01} step={0.01} {...register("price_per_unit", { valueAsNumber: true })} />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label={t("district")} required error={err(errors.district?.message)}>
          <Input {...register("district")} />
        </Field>
        <Field label={t("harvestDate")}>
          <Input type="date" {...register("harvest_date")} />
        </Field>
        <Field label={t("availableUntil")}>
          <Input type="date" {...register("available_until")} />
        </Field>
      </div>
      <Field label={t("description")}>
        <Textarea rows={3} {...register("description")} />
      </Field>
      <Field label={t("imageUrl")} hint={t("imagesHint")}>
        <Input type="url" placeholder="https://…" {...register("image_url")} />
      </Field>

      <div>
        <p className="mb-1.5 block text-[13px] font-bold text-ink">{t("uploadImages")}</p>
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          className="hidden"
          onChange={(e) => onFiles(e.target.files)}
        />
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="flex w-full items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line bg-white px-4 py-6 text-sm font-bold text-muted hover:border-leaf hover:text-forest"
        >
          <ImagePlus className="h-5 w-5" /> {t("uploadImages")} ({files.length}/{MAX_IMAGES})
        </button>
        {previews.length > 0 && (
          <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5">
            {previews.map((u, i) => (
              <div key={u} className="relative aspect-square overflow-hidden rounded-2xl border border-line">
                <img src={u} alt="" className="h-full w-full object-cover" />
                <button
                  type="button"
                  aria-label={t("delete")}
                  onClick={() => removeFile(i)}
                  className="absolute right-1 top-1 rounded-full bg-black/60 p-1 text-white"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
        {uploadPct !== null && (
          <div className="mt-3">
            <div className="h-2 overflow-hidden rounded-full bg-cream">
              <div className="h-full bg-leaf transition-all" style={{ width: `${uploadPct}%` }} />
            </div>
            <p className="mt-1 text-xs font-semibold text-muted">
              {t("uploadProgress")}: {uploadPct}%
            </p>
          </div>
        )}
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="ghost" onClick={onDone}>
          {t("cancel")}
        </Button>
        <Button type="submit" loading={mutation.isPending}>
          {product ? t("save") : t("publishProduct")}
        </Button>
      </div>
    </form>
  );
}
