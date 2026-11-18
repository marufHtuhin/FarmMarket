import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { notificationsApi } from "../services/api";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";
import { Badge } from "../components/ui/misc";

export function NotificationsPage() {
  const { t, fmtDateTime } = useLang();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [readLocal, setReadLocal] = useState<Set<number>>(new Set());

  const q = useQuery({ queryKey: ["notifications"], queryFn: notificationsApi.list });

  const markOne = useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id).catch(() => null),
    onSuccess: (_d, id) => {
      setReadLocal((prev) => new Set(prev).add(id));
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const markAll = useMutation({
    mutationFn: () => notificationsApi.markAllRead().catch(() => null),
    onSuccess: () => {
      setReadLocal(new Set((q.data || []).map((n) => n.id)));
      qc.invalidateQueries({ queryKey: ["notifications"] });
      toast(t("markAllRead"), "success");
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  const items = q.data || [];
  const unreadCount = items.filter((n) => !n.is_read && !readLocal.has(n.id)).length;

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title={t("notificationsTitle")}
        sub={unreadCount > 0 ? `${unreadCount} ${t("unread")}` : undefined}
        action={
          unreadCount > 0 ? (
            <Button variant="secondary" size="sm" loading={markAll.isPending} onClick={() => markAll.mutate()}>
              {t("markAllRead")}
            </Button>
          ) : undefined
        }
      />
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && items.length === 0 && (
        <EmptyState icon={<Bell className="h-10 w-10 text-leaf" />} title={t("noNotifications")} />
      )}
      {q.isSuccess && items.length > 0 && (
        <Card className="divide-y divide-line overflow-hidden">
          {items.map((n) => {
            const isRead = n.is_read || readLocal.has(n.id);
            return (
              <div key={n.id} className={`flex items-start justify-between gap-3 px-5 py-4 ${isRead ? "" : "bg-mint/50"}`}>
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-bold">
                    {n.title}
                    {!isRead && <Badge tone="marigold">{t("unread")}</Badge>}
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-muted">{n.message}</p>
                  <p className="mt-1 text-xs text-muted">{n.created_at ? fmtDateTime(n.created_at) : ""}</p>
                </div>
                {!isRead && (
                  <Button variant="ghost" size="sm" className="shrink-0" onClick={() => markOne.mutate(n.id)}>
                    {t("markRead")}
                  </Button>
                )}
              </div>
            );
          })}
        </Card>
      )}
    </div>
  );
}
