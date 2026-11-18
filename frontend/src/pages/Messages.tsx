import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, MessageSquare, Send } from "lucide-react";
import { conversationsApi } from "../services/api";
import type { ChatConversation } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { useToast } from "../contexts/ToastContext";
import { apiErrorMessage } from "../utils/format";
import { Button, Card, EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui/core";

function UnreadBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-marigold px-1.5 text-[11px] font-extrabold text-[#2e2110]">
      {count > 99 ? "99+" : count}
    </span>
  );
}

function ConversationRow({ conv }: { conv: ChatConversation }) {
  const { t, fmtDateTime } = useLang();
  const last = conv.last_message;
  return (
    <Link
      to={`/messages/${conv.id}`}
      className="flex items-center gap-3 rounded-3xl border border-line bg-white px-4 py-3.5 shadow-card transition hover:border-leaf"
    >
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-leaf text-base font-extrabold text-white">
        {conv.other.name.charAt(0).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <b className="truncate text-[15px] text-ink">{conv.other.name}</b>
          {last?.created_at && (
            <span className="shrink-0 text-xs text-muted">{fmtDateTime(last.created_at)}</span>
          )}
        </span>
        <span className="block truncate text-xs text-muted">
          {t(`role${conv.other.role[0].toUpperCase()}${conv.other.role.slice(1)}`)}
          {conv.other.district ? ` · ${conv.other.district}` : ""}
          {conv.listing_name ? ` · ${t("conversationAbout")} ${conv.listing_name}` : ""}
        </span>
        {last && <span className="mt-0.5 block truncate text-sm text-[#4c5f52]">{last.body}</span>}
      </span>
      <UnreadBadge count={conv.unread_count} />
    </Link>
  );
}

function ThreadView({ convId }: { convId: number }) {
  const { t, fmtDateTime } = useLang();
  const { user } = useAuth();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const markedUpTo = useRef(0);

  const convsQ = useQuery({ queryKey: ["conversations"], queryFn: conversationsApi.list, retry: false });
  const conv = (convsQ.data || []).find((c) => c.id === convId);

  const msgsQ = useQuery({
    queryKey: ["conversations", convId, "messages"],
    queryFn: () => conversationsApi.getMessages(convId),
    retry: false,
    // Poll while the thread is open so a reply appears without a refresh.
    refetchInterval: 15_000,
  });

  const readMutation = useMutation({
    mutationFn: () => conversationsApi.markRead(convId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      qc.invalidateQueries({ queryKey: ["conversations", "unread"] });
    },
  });

  // Mark incoming messages read whenever the thread shows unread ones.
  const messages = msgsQ.data || [];
  const maxIncomingId = messages.reduce(
    (max, m) => (m.sender_id !== user?.id && !m.read_at ? Math.max(max, m.id) : max),
    0
  );
  useEffect(() => {
    if (maxIncomingId > markedUpTo.current && !readMutation.isPending) {
      markedUpTo.current = maxIncomingId;
      readMutation.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [maxIncomingId]);

  // Keep the newest message in view.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length]);

  const sendMutation = useMutation({
    mutationFn: (body: string) => conversationsApi.sendMessage(convId, body),
    onSuccess: () => {
      setDraft("");
      qc.invalidateQueries({ queryKey: ["conversations", convId, "messages"] });
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
    onError: (e) => toast(apiErrorMessage(e), "error"),
  });

  if (convsQ.isLoading || msgsQ.isLoading) return <Spinner label={t("loading")} />;
  if (msgsQ.isError) return <ErrorState message={apiErrorMessage(msgsQ.error)} onRetry={() => msgsQ.refetch()} />;
  if (convsQ.isSuccess && !conv) {
    return (
      <EmptyState
        title={t("conversationNotFound")}
        action={
          <Link to="/messages">
            <Button variant="secondary">{t("back")}</Button>
          </Link>
        }
      />
    );
  }

  const other = conv?.other;
  const canSend = draft.trim().length > 0 && !sendMutation.isPending;

  return (
    <div className="mx-auto flex max-w-2xl flex-col">
      <Link to="/messages" className="mb-4 inline-flex items-center gap-2 self-start text-sm font-bold text-leaf hover:underline">
        <ArrowLeft className="h-4 w-4" /> {t("back")}
      </Link>
      <Card className="flex min-h-[60vh] flex-col overflow-hidden">
        <div className="border-b border-line px-4 py-3.5 sm:px-5">
          <p className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-leaf text-sm font-extrabold text-white">
              {other?.name.charAt(0).toUpperCase()}
            </span>
            <span className="min-w-0">
              <b className="block truncate text-[15px]">{other?.name}</b>
              <span className="block truncate text-xs text-muted">
                {other && t(`role${other.role[0].toUpperCase()}${other.role.slice(1)}`)}
                {other?.district ? ` · ${other.district}` : ""}
                {conv?.listing_name ? ` · ${t("conversationAbout")} ${conv.listing_name}` : ""}
              </span>
            </span>
          </p>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4 sm:px-5" style={{ maxHeight: "55vh" }}>
          {messages.length === 0 && (
            <p className="py-8 text-center text-sm text-muted">{t("noMessagesYet")}</p>
          )}
          {messages.map((m) => {
            const mine = m.sender_id === user?.id;
            return (
              <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    mine ? "rounded-br-sm bg-forest text-white" : "rounded-bl-sm bg-cream text-ink"
                  }`}
                >
                  <p className="whitespace-pre-wrap break-words">{m.body}</p>
                  <p className={`mt-1 text-right text-[11px] ${mine ? "text-white/70" : "text-muted"}`}>
                    {m.created_at ? fmtDateTime(m.created_at) : ""}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        <form
          className="flex items-center gap-2 border-t border-line bg-white px-3 py-3 sm:px-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSend) sendMutation.mutate(draft.trim());
          }}
        >
          <label htmlFor="chat-input" className="sr-only">
            {t("typeMessage")}
          </label>
          <input
            id="chat-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t("typeMessage")}
            maxLength={2000}
            autoComplete="off"
            className="min-w-0 flex-1 rounded-full border border-line bg-cream px-4 py-2.5 text-sm outline-none focus:border-leaf"
          />
          <Button type="submit" disabled={!canSend} loading={sendMutation.isPending} aria-label={t("sendMessage")}>
            <Send className="h-4 w-4" />
            <span className="hidden sm:inline">{t("sendMessage")}</span>
          </Button>
        </form>
      </Card>
      <p className="mt-3 text-center text-xs text-muted">{t("chatPrivacyNote")}</p>
    </div>
  );
}

export function MessagesPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useLang();
  const threadId = id ? Number(id) : NaN;

  if (id) {
    if (!Number.isFinite(threadId)) {
      return <EmptyState title={t("conversationNotFound")} action={<Link to="/messages"><Button variant="secondary">{t("back")}</Button></Link>} />;
    }
    return <ThreadView convId={threadId} />;
  }

  return <ConversationList />;
}

function ConversationList() {
  const { t } = useLang();
  const q = useQuery({ queryKey: ["conversations"], queryFn: conversationsApi.list, retry: false });

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title={t("messagesTitle")} sub={t("messagesSub")} />
      <p className="mb-4 rounded-2xl bg-mint px-4 py-2.5 text-xs font-semibold text-forest">{t("chatPrivacyNote")}</p>
      {q.isLoading && <Spinner label={t("loading")} />}
      {q.isError && <ErrorState message={apiErrorMessage(q.error)} onRetry={() => q.refetch()} />}
      {q.isSuccess && q.data.length === 0 && (
        <EmptyState
          icon={<MessageSquare className="h-10 w-10 text-leaf" />}
          title={t("noConversations")}
          hint={t("noConversationsHint")}
          action={
            <Link to="/marketplace">
              <Button>{t("navMarket")}</Button>
            </Link>
          }
        />
      )}
      {q.isSuccess && q.data.length > 0 && (
        <div className="space-y-3">
          {q.data.map((conv) => (
            <ConversationRow key={conv.id} conv={conv} />
          ))}
        </div>
      )}
    </div>
  );
}
