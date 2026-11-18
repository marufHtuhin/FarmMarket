import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { offersApi, type Product } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage, apiStatus } from "../utils/format";
import { Modal } from "./ui/misc";
import { Button } from "./ui/core";
import { Field, Input, Textarea } from "./ui/fields";

export function OfferModal({ open, onClose, product }: { open: boolean; onClose: () => void; product: Product }) {
  const { t, fmtNum } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [quantity, setQuantity] = useState(1);
  const [price, setPrice] = useState(product.price_per_unit);
  const [message, setMessage] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      offersApi.create({ product_id: product.id, quantity, offered_price: price, message: message || undefined }),
    onSuccess: () => {
      toast(t("offerSent"), "success");
      qc.invalidateQueries({ queryKey: ["offers"] });
      onClose();
    },
    onError: (e) => {
      if (apiStatus(e) === 404) toast(t("errorGeneric"), "error");
      else toast(apiErrorMessage(e), "error");
    },
  });

  const valid = quantity > 0 && quantity <= product.quantity && price > 0;

  return (
    <Modal open={open} onClose={onClose} title={`${t("makeOffer")}: ${product.name}`}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) mutation.mutate();
        }}
      >
        <p className="text-sm text-muted">
          {t("farmerPrice")}: <b className="text-ink">৳{fmtNum(product.price_per_unit)}/{product.unit}</b> ·{" "}
          {t("available")}: <b className="text-ink">{fmtNum(product.quantity)} {product.unit}</b>
        </p>
        <Field label={t("orderQuantity")} required>
          <Input type="number" min={0.1} max={product.quantity} step={0.1} value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} required />
        </Field>
        <Field label={t("offeredPrice")} required>
          <Input type="number" min={0.01} step={0.01} value={price} onChange={(e) => setPrice(Number(e.target.value))} required />
        </Field>
        <Field label={t("offerMessage")}>
          <Textarea rows={2} value={message} onChange={(e) => setMessage(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button type="submit" loading={mutation.isPending} disabled={!valid}>
            {t("makeOffer")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
