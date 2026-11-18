import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ordersApi, type Product } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Modal } from "./ui/misc";
import { Button } from "./ui/core";
import { Field, Input, Textarea } from "./ui/fields";

export function OrderModal({ open, onClose, product }: { open: boolean; onClose: () => void; product: Product }) {
  const { t, fmtNum } = useLang();
  const { toast } = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [quantity, setQuantity] = useState(1);
  const [address, setAddress] = useState("");

  const mutation = useMutation({
    mutationFn: () => ordersApi.create({ product_id: product.id, quantity, delivery_address: address }),
    onSuccess: (res) => {
      toast(`${t("orderSuccess")} · ৳${fmtNum(res.total_amount)}`, "success");
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["orders"] });
      onClose();
      navigate("/orders");
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const valid = quantity > 0 && quantity <= product.quantity;

  return (
    <Modal open={open} onClose={onClose} title={`${t("order")}: ${product.name}`}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) mutation.mutate();
        }}
      >
        <p className="text-sm text-muted">
          {t("available")}: <b className="text-ink">{fmtNum(product.quantity)} {product.unit}</b> · ৳
          {fmtNum(product.price_per_unit)}/{product.unit}
        </p>
        <Field label={t("orderQuantity")} required error={!valid && quantity > 0 ? t("quantityExceeded") : undefined}>
          <Input
            type="number"
            min={0.1}
            max={product.quantity}
            step={0.1}
            value={quantity}
            onChange={(e) => setQuantity(Number(e.target.value))}
            required
          />
        </Field>
        <Field label={t("deliveryAddress")}>
          <Textarea rows={2} value={address} onChange={(e) => setAddress(e.target.value)} placeholder={t("deliveryAddress")} />
        </Field>
        <p className="rounded-2xl bg-cream px-4 py-3 text-sm font-bold">
          {t("total")}: ৳{fmtNum(Math.max(0, quantity) * product.price_per_unit)}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button type="submit" loading={mutation.isPending} disabled={!valid}>
            {t("placeOrder")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
