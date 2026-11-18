import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageSquare } from "lucide-react";
import { conversationsApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Button } from "./ui/core";
import { useNavigate } from "react-router-dom";

/** "Message farmer/buyer" button: creates-or-finds the thread, then opens it.
 *  Used on listing detail, offers and order pages. Chat is in-app only — no
 *  phone number is ever shown. */
export function MessageButton({
  otherUserId,
  listingId,
  offerId,
  label,
  variant = "secondary",
  size = "md",
}: {
  otherUserId: number;
  listingId?: number | null;
  offerId?: number | null;
  label: string;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
}) {
  const { t } = useLang();
  const { toast } = useToast();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      conversationsApi.create({
        other_user_id: otherUserId,
        listing_id: listingId ?? null,
        offer_id: offerId ?? null,
      }),
    onSuccess: (conv) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      navigate(`/messages/${conv.id}`);
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  return (
    <Button
      variant={variant}
      size={size}
      loading={mutation.isPending}
      onClick={() => mutation.mutate()}
      aria-label={label}
    >
      <MessageSquare className="h-4 w-4" />
      {mutation.isPending ? t("messageStarting") : label}
    </Button>
  );
}
