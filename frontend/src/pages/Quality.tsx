import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Camera, ImagePlus, Leaf } from "lucide-react";
import { visionApi, type VisionResult } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage, apiStatus } from "../utils/format";
import { Button, Card, EmptyState, PageHeader } from "../components/ui/core";
import { Field, Input } from "../components/ui/fields";
import { Badge } from "../components/ui/misc";

export function QualityPage() {
  const { t, fmtNum } = useLang();
  const { toast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [crop, setCrop] = useState("");
  const [refPrice, setRefPrice] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [result, setResult] = useState<VisionResult | null>(null);
  const [notTrained, setNotTrained] = useState(false);
  const cameraRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: () =>
      visionApi.assess(
        file as File,
        crop,
        { referencePrice: refPrice ? Number(refPrice) : undefined },
        setProgress
      ),
    onSuccess: (res) => {
      setResult(res);
      setNotTrained(false);
      setProgress(null);
    },
    onError: (e) => {
      setProgress(null);
      if (apiStatus(e) === 503) {
        setNotTrained(true);
        setResult(null);
      } else {
        toast(apiErrorMessage(e), "error");
      }
    },
  });

  const pick = (f: File | null) => {
    if (!f) return;
    setFile(f);
    setResult(null);
    setNotTrained(false);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(URL.createObjectURL(f));
  };

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title={t("qualityTitle")} sub={t("qualitySub")} />
      <Card className="p-5 sm:p-6">
        <input
          ref={cameraRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0] || null)}
        />
        <input
          ref={galleryRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0] || null)}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <Button variant="secondary" size="lg" onClick={() => cameraRef.current?.click()}>
            <Camera className="h-5 w-5" /> {t("takePhoto")}
          </Button>
          <Button variant="secondary" size="lg" onClick={() => galleryRef.current?.click()}>
            <ImagePlus className="h-5 w-5" /> {t("chooseFromGallery")}
          </Button>
        </div>

        {preview && (
          <div className="mt-4 overflow-hidden rounded-3xl border border-line">
            <img src={preview} alt="" className="max-h-80 w-full object-cover" />
          </div>
        )}

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label={t("ti_crop")} required>
            <Input value={crop} onChange={(e) => setCrop(e.target.value)} placeholder={t("ti_cropPh")} />
          </Field>
          <Field label={t("ti_refPricePh")}>
            <Input type="number" min={0.01} step={0.01} value={refPrice} onChange={(e) => setRefPrice(e.target.value)} />
          </Field>
        </div>

        <Button
          className="mt-5 w-full"
          size="lg"
          loading={mutation.isPending}
          disabled={!file || !crop.trim()}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? t("assessing") : t("ti_assessBtn")}
        </Button>
        {progress !== null && (
          <div className="mt-3">
            <div className="h-2 overflow-hidden rounded-full bg-cream">
              <div className="h-full bg-leaf transition-all" style={{ width: `${progress}%` }} />
            </div>
            <p className="mt-1 text-xs font-semibold text-muted">
              {t("uploadProgress")}: {progress}%
            </p>
          </div>
        )}
      </Card>

      {notTrained && (
        <div className="mt-5 rounded-3xl border border-[#f4e4bf] bg-[#fff8e9] px-5 py-4 text-sm font-semibold text-[#80632d]">
          {t("visionNotTrained")}
        </div>
      )}

      {result && (
        <Card className="mt-5 p-5 sm:p-6">
          <h2 className="flex items-center gap-2 font-display text-lg font-extrabold text-forest">
            <Leaf className="h-5 w-5 text-leaf" /> {t("gradeResult")}
          </h2>
          <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
            <div className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
              {t("ti_grade")}
              <b className="block text-lg font-extrabold text-forest">{result.grade}</b>
            </div>
            <div className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
              {t("ti_ripeness")}
              <b className="block text-lg font-extrabold text-forest">{result.ripeness || t("ti_na")}</b>
            </div>
            <div className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
              {t("ti_disease")}
              <b className="block text-lg font-extrabold text-forest">
                {(result.disease || t("ti_na")).replace(/___/g, " – ").replace(/_/g, " ")}
              </b>
            </div>
            <div className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
              {t("ti_confidence")}
              <b className="block text-lg font-extrabold text-forest">{Math.round(result.confidence * 100)}%</b>
            </div>
            <div className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
              {t("ti_priceMultiplier")}
              <b className="block text-lg font-extrabold text-forest">
                {result.price_multiplier ?? t("ti_manualReview")}
              </b>
            </div>
            <div className="rounded-2xl bg-mint px-3.5 py-3 text-[13px] text-muted">
              {t("ti_suggestedPrice")}
              <b className="block text-lg font-extrabold text-forest">
                {result.suggested_price !== null && result.suggested_price !== undefined
                  ? `৳${fmtNum(result.suggested_price)}`
                  : "—"}
              </b>
            </div>
          </div>
          {result.needs_manual_review && (
            <div className="mt-4 rounded-2xl border border-[#f4e4bf] bg-[#fff8e9] px-4 py-3 text-[13px] text-[#80632d]">
              {t("ti_manualReviewNote")}
            </div>
          )}
          {(result.reasons || []).length > 0 && (
            <p className="mt-4 text-sm text-muted">{result.reasons!.join(" · ")}</p>
          )}
          {(result.warnings || []).length > 0 && (
            <div className="mt-3 space-y-2">
              {result.warnings!.map((w, i) => (
                <p key={i} className="rounded-2xl bg-[#fff8e9] px-4 py-2 text-[13px] text-[#80632d]">
                  {w}
                </p>
              ))}
            </div>
          )}
          <p className="mt-4 text-xs text-muted">
            {t("latestResult")} · {result.model_version || ""}
          </p>
        </Card>
      )}

      {!result && !notTrained && !mutation.isPending && (
        <EmptyState title={t("ti_choosePhoto")} hint={t("qualitySub")} />
      )}
      <div className="mt-4 flex justify-center">
        <Badge tone="gray">{t("ti_visionNote")}</Badge>
      </div>
    </div>
  );
}
