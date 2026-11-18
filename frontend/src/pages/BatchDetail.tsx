import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { twinApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Button, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { BatchView } from "../components/BatchView";

export function BatchDetailPage() {
  const { code } = useParams<{ code: string }>();
  const { t } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: ["batch", code],
    queryFn: () => twinApi.public(code as string),
    enabled: !!code,
    retry: false,
  });

  const sealMutation = useMutation({
    mutationFn: () => twinApi.seal(code as string),
    onSuccess: () => {
      toast(t("sealedMsg"), "success");
      qc.invalidateQueries({ queryKey: ["batch", code] });
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  if (q.isLoading) return <Spinner label={t("loading")} />;
  if (q.isError)
    return (
      <div>
        <Link to="/batches" className="mb-4 inline-flex items-center gap-2 text-sm font-bold text-leaf hover:underline">
          <ArrowLeft className="h-4 w-4" /> {t("back")}
        </Link>
        <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />
      </div>
    );
  if (!q.data) return <EmptyState title={t("batchNotFound")} />;

  return (
    <div>
      <Link to="/batches" className="mb-4 inline-flex items-center gap-2 text-sm font-bold text-leaf hover:underline">
        <ArrowLeft className="h-4 w-4" /> {t("back")}
      </Link>
      <PageHeader
        title={t("batchDetail")}
        sub={q.data.batch_code}
        action={
          <Button variant="secondary" loading={sealMutation.isPending} onClick={() => sealMutation.mutate()}>
            {t("sealReadings")}
          </Button>
        }
      />
      <BatchView batch={q.data} />
    </div>
  );
}
