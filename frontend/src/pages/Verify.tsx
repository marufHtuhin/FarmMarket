import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { QrCode, ScanLine } from "lucide-react";
import { twinApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { apiErrorMessage } from "../utils/format";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { Input } from "../components/ui/fields";
import { BatchView } from "../components/BatchView";

export function VerifyPage() {
  const { code: routeCode } = useParams<{ code?: string }>();
  const navigate = useNavigate();
  const { t } = useLang();
  const [input, setInput] = useState(routeCode || "");

  const q = useQuery({
    queryKey: ["batch-public", routeCode],
    queryFn: () => twinApi.public(routeCode as string),
    enabled: !!routeCode,
    retry: false,
  });

  const lookup = () => {
    const code = input.trim();
    if (code) navigate(`/verify/${encodeURIComponent(code)}`, { replace: true });
  };

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={t("verifyTitle")} sub={t("verifySub")} />
      <Card className="p-5">
        <form
          className="flex flex-col gap-3 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            lookup();
          }}
        >
          <div className="relative min-w-0 flex-1">
            <QrCode className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t("ti_batchPh")}
              aria-label={t("enterCode")}
              className="pl-10 font-mono"
            />
          </div>
          <Button type="submit" size="lg" disabled={!input.trim()}>
            <ScanLine className="h-4 w-4" /> {t("ti_lookupBtn")}
          </Button>
        </form>
        <p className="mt-3 text-xs text-muted">{t("publicViewNote")}</p>
      </Card>

      <div className="mt-6">
        {q.isLoading && <Spinner label={t("loading")} />}
        {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
        {routeCode && q.isSuccess && !q.data && <EmptyState title={t("batchNotFound")} />}
        {q.isSuccess && q.data && <BatchView batch={q.data} />}
        {!routeCode && !q.isLoading && (
          <EmptyState icon={<QrCode className="h-10 w-10 text-leaf" />} title={t("verifyTitle")} hint={t("verifySub")} />
        )}
      </div>
    </div>
  );
}
