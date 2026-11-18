import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, ImagePlus, Menu, Mic, Plus, Send, Square, User, Volume2, X, Zap } from "lucide-react";
import {
  advisorApi,
  assistantApi,
  streamAssistantChat,
  type AssistantMessage,
  type AssistantTestResult,
} from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { apiErrorMessage, apiStatus } from "../utils/format";
import { Button, Card, EmptyState, Spinner } from "../components/ui/core";
import { Drawer } from "../components/ui/misc";
import { Input, Select } from "../components/ui/fields";

interface ChatMsg extends AssistantMessage {
  fallback?: boolean;
  /** True while this message is still receiving streamed tokens. */
  streaming?: boolean;
  /** Local object URL of a photo the user attached with this message.
   *  Revoked when the conversation changes or the page unmounts. */
  imageUrl?: string;
}

function revokeImageUrls(msgs: ChatMsg[]) {
  for (const m of msgs) if (m.imageUrl) URL.revokeObjectURL(m.imageUrl);
}

/** Minimal Web Speech API shapes — TS's DOM lib has no SpeechRecognition
 *  (only speechSynthesis), so these are declared locally. */
interface SpeechRecognitionResultLike {
  transcript: string;
}
interface SpeechRecognitionEventLike {
  results: ArrayLike<ArrayLike<SpeechRecognitionResultLike>>;
}
interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function speechSynthesisSupported(): boolean {
  return (
    typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window
  );
}

/** Bangla Unicode block (U+0980–U+09FF). A reply containing any Bangla
 *  character is read with a Bangla voice; anything else (English or
 *  Banglish in Latin script) with an English voice. Detected from the
 *  reply text itself — chatLang alone would mis-voice a Banglish reply
 *  sent under the Bangla UI. */
function hasBanglaScript(text: string): boolean {
  return /[\u0980-\u09FF]/.test(text);
}

/** Pick a voice matching the reply's script, or null when the device has
 *  none — the caller hides the speaker button in that case rather than
 *  reading the reply with the wrong voice (an English voice silently
 *  skips the Bangla words). */
function pickVoice(voices: SpeechSynthesisVoice[], text: string): SpeechSynthesisVoice | null {
  const prefix = hasBanglaScript(text) ? "bn" : "en";
  return voices.find((v) => v.lang.toLowerCase().startsWith(prefix)) ?? null;
}

export function AssistantPage() {
  const { t, lang } = useLang();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [chatLang, setChatLang] = useState(lang);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [assistantMissing, setAssistantMissing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState<AssistantTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  // Photo question (disease detection): the attached file + its preview URL.
  const [attachedImage, setAttachedImage] = useState<File | null>(null);
  const [attachedPreview, setAttachedPreview] = useState<string | null>(null);
  // Voice (Web Speech API only, no backend): recording state + which
  // assistant message is currently being read aloud.
  const [recording, setRecording] = useState(false);
  const [speakingIndex, setSpeakingIndex] = useState<number | null>(null);
  // Feature-detected once: unsupported browsers simply hide the controls.
  const [voiceInputSupported] = useState(() => getSpeechRecognitionCtor() !== null);
  const [voiceReadoutSupported] = useState(() => speechSynthesisSupported());
  // Installed TTS voices (loaded async — see the voiceschanged effect).
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  // Mirrors for the unmount cleanup (refs hold the latest values there).
  const messagesRef = useRef<ChatMsg[]>([]);
  messagesRef.current = messages;
  const attachedPreviewRef = useRef<string | null>(null);
  attachedPreviewRef.current = attachedPreview;

  // Abort an in-flight stream if the user leaves the page mid-reply; stop
  // any voice recognition/speech and release photo object URLs.
  useEffect(
    () => () => {
      abortRef.current?.abort();
      recognitionRef.current?.abort();
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      revokeImageUrls(messagesRef.current);
      if (attachedPreviewRef.current) URL.revokeObjectURL(attachedPreviewRef.current);
    },
    []
  );

  // Voices load asynchronously: Chrome returns [] from getVoices() until
  // the voiceschanged event fires, so refresh on it. Until a voice for a
  // reply's language is known, its speaker button stays hidden.
  useEffect(() => {
    if (!voiceReadoutSupported) return;
    const synth = window.speechSynthesis;
    const loadVoices = () => {
      const list = typeof synth.getVoices === "function" ? synth.getVoices() : [];
      setVoices(list ?? []);
    };
    loadVoices();
    synth.addEventListener?.("voiceschanged", loadVoices);
    return () => synth.removeEventListener?.("voiceschanged", loadVoices);
  }, [voiceReadoutSupported]);

  const convsQ = useQuery({
    queryKey: ["assistant-conversations"],
    queryFn: assistantApi.conversations,
    retry: false,
  });

  const convQ = useQuery({
    queryKey: ["assistant-conversation", conversationId],
    queryFn: () => assistantApi.conversation(conversationId as string),
    enabled: !!conversationId,
    retry: false,
  });

  useEffect(() => {
    if (convQ.data?.messages) {
      const incoming = convQ.data.messages;
      setMessages((prev) => {
        // Same thread refetched (e.g. after a send adopted a conversation
        // id): carry local photo thumbnails over — the server stores the
        // text, not the object URL, so without this the photo would vanish
        // from the bubble as soon as the refetch lands.
        const sameThread =
          incoming.length === prev.length &&
          incoming.every((m, i) => m.role === prev[i].role && m.content === prev[i].content);
        if (!sameThread) {
          // Different conversation: release the old thread's photo URLs.
          revokeImageUrls(prev);
          return incoming;
        }
        return incoming.map((m, i) => (prev[i].imageUrl ? { ...m, imageUrl: prev[i].imageUrl } : m));
      });
    }
  }, [convQ.data]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /** Non-stream chat (axios, 90s cap) with the classic-advisor fallback
   *  when the assistant endpoint is missing. Used when streaming fails. */
  const sendViaHttp = async (text: string) => {
    try {
      const res = await assistantApi.chat({ conversation_id: conversationId, message: text, language: chatLang });
      setConversationId(res.conversation_id);
      qc.invalidateQueries({ queryKey: ["assistant-conversations"] });
      return { reply: res.reply, sources: res.sources, mode: res.mode, fallback: false };
    } catch (e) {
      if (apiStatus(e) === 404) {
        // Assistant endpoint not built yet — fall back to the classic advisor.
        setAssistantMissing(true);
        const advice = await advisorApi.advice({
          crop: "tomato",
          language: chatLang === "bn" ? "bn" : "en",
          report: text,
        });
        const reply = [
          advice.summary,
          "",
          ...advice.actions.map((a) => `• ${a.action}${a.timing ? ` (${a.timing})` : ""}${a.reason ? ` — ${a.reason}` : ""}`),
          "",
          `${t("ti_risks")}: ${advice.risks.join("; ")}`,
          advice.uncertainty_note || "",
        ]
          .filter(Boolean)
          .join("\n");
        return { reply, sources: [], mode: "template" as const, fallback: true };
      }
      throw e;
    }
  };

  /** Drop the attached photo (releases its preview URL). */
  const clearAttachment = () => {
    if (attachedPreview) URL.revokeObjectURL(attachedPreview);
    setAttachedImage(null);
    setAttachedPreview(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const onImagePicked = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (attachedPreview) URL.revokeObjectURL(attachedPreview);
    setAttachedImage(file);
    setAttachedPreview(URL.createObjectURL(file));
  };

  /** Photo question (disease detection): multipart upload instead of the
   *  text stream. On error the message is NOT appended and the input +
   *  photo are kept so the user can retry. */
  const sendImage = async () => {
    if (!attachedImage || busy) return;
    const text = input.trim();
    const file = attachedImage;
    const previewUrl = attachedPreview;
    setBusy(true);
    try {
      const res = await assistantApi.chatImage({
        image: file,
        message: text || undefined,
        language: chatLang,
        conversation_id: conversationId,
      });
      setConversationId(String(res.conversation_id));
      qc.invalidateQueries({ queryKey: ["assistant-conversations"] });
      setMessages((prev) => [
        ...prev,
        { role: "user", content: text, imageUrl: previewUrl ?? undefined },
        { role: "assistant", content: res.reply, sources: res.sources, mode: res.mode },
      ]);
      // The preview URL now belongs to the message — clear the attachment
      // state WITHOUT revoking it.
      setAttachedImage(null);
      setAttachedPreview(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setInput("");
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `${t("assistantError")} (${apiErrorMessage(err)})`, mode: "template" },
      ]);
    } finally {
      setBusy(false);
    }
  };

  /** Voice input (Web Speech API, no backend). The transcript lands in the
   *  input box; the user sends as normal. */
  const toggleRecording = () => {
    if (recording) {
      recognitionRef.current?.stop();
      setRecording(false);
      return;
    }
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = chatLang === "bn" ? "bn-BD" : "en-US";
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript?.trim();
      if (transcript) setInput((prev) => (prev.trim() ? `${prev.trim()} ${transcript}` : transcript));
    };
    rec.onerror = () => setRecording(false);
    rec.onend = () => {
      setRecording(false);
      recognitionRef.current = null;
    };
    recognitionRef.current = rec;
    try {
      rec.start();
      setRecording(true);
    } catch {
      // start() throws if recognition is already running — never crash.
      recognitionRef.current = null;
      setRecording(false);
    }
  };

  /** Read an assistant reply aloud (speechSynthesis, no backend).
   *  Clicking the same message again — or another message — stops the
   *  current speech. */
  const stopSpeaking = () => {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeakingIndex(null);
  };

  const speak = (index: number, text: string) => {
    if (!voiceReadoutSupported) return;
    if (speakingIndex === index) {
      stopSpeaking();
      return;
    }
    // Voice matched to the reply's script, not chatLang: a Banglish reply
    // under the Bangla UI still needs an English voice. No suitable voice
    // → no speech (the button is hidden in that case; this is defensive).
    const voice = pickVoice(voices, text);
    if (!voice) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.onend = () => setSpeakingIndex(null);
    utterance.onerror = () => setSpeakingIndex(null);
    setSpeakingIndex(index);
    window.speechSynthesis.speak(utterance);
  };

  const send = async () => {
    const text = input.trim();
    if ((!text && !attachedImage) || busy) return;
    if (attachedImage) {
      await sendImage();
      return;
    }
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setBusy(true);
    // Streaming placeholder: tokens append to this message as they arrive.
    // Streaming (fetch, no timeout cap) keeps slow Gemini replies alive past
    // the 20s cliff that used to end in template mode or a 30s axios error.
    setMessages((prev) => [...prev, { role: "assistant", content: "", streaming: true }]);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const done = await streamAssistantChat(
        { conversation_id: conversationId, message: text, language: chatLang },
        (tok) =>
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.streaming) next[next.length - 1] = { ...last, content: last.content + tok };
            return next;
          }),
        controller.signal
      );
      setConversationId(done.conversation_id);
      qc.invalidateQueries({ queryKey: ["assistant-conversations"] });
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.streaming) {
          next[next.length - 1] = { role: "assistant", content: last.content, sources: done.sources, mode: done.mode };
        }
        return next;
      });
    } catch (e) {
      if (controller.signal.aborted) return;
      // Streaming failed (network, expired token, server cut): drop the
      // placeholder and fall back to the regular non-stream chat, which
      // also refreshes an expired token via the axios interceptor.
      setMessages((prev) => {
        const next = [...prev];
        if (next[next.length - 1]?.streaming) next.pop();
        return next;
      });
      try {
        const res = await sendViaHttp(text);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: res.reply, sources: res.sources, mode: res.mode, fallback: res.fallback },
        ]);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `${t("assistantError")} (${apiErrorMessage(err)})`, mode: "template" },
        ]);
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  /** Admin-only live Gemini probe: one tiny call, shows ok/fail + latency. */
  const testGemini = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      setTestResult(await assistantApi.test());
    } catch (e) {
      setTestResult({ ok: false, mode: "template", latency_ms: 0, error: apiErrorMessage(e) });
    } finally {
      setTesting(false);
    }
  };

  const newConversation = () => {
    revokeImageUrls(messagesRef.current);
    clearAttachment();
    stopSpeaking();
    setConversationId(undefined);
    setMessages([]);
    setDrawerOpen(false);
  };

  const convList = (
    <div className="space-y-2">
      <Button variant="secondary" className="w-full" onClick={newConversation}>
        <Plus className="h-4 w-4" /> {t("newConversation")}
      </Button>
      {convsQ.isLoading && <Spinner />}
      {(convsQ.data || []).length === 0 && !convsQ.isLoading && (
        <p className="py-4 text-center text-sm text-muted">{t("noConversations")}</p>
      )}
      {(convsQ.data || []).map((c) => (
        <button
          key={c.id}
          type="button"
          onClick={() => {
            stopSpeaking();
            setConversationId(c.id);
            setDrawerOpen(false);
          }}
          className={`block w-full truncate rounded-2xl px-3.5 py-2.5 text-left text-sm font-semibold transition ${
            c.id === conversationId ? "bg-mint text-forest" : "hover:bg-cream"
          }`}
        >
          {c.title || c.id.slice(0, 24)}
        </button>
      ))}
    </div>
  );

  return (
    <div className="flex h-[calc(100vh-11rem)] min-h-[480px] gap-5 lg:h-[calc(100vh-9rem)]">
      {/* Conversation list — desktop */}
      <Card className="hidden w-72 shrink-0 flex-col p-4 lg:flex">
        <h2 className="mb-3 font-display font-bold text-forest">{t("conversations")}</h2>
        <div className="thin-scroll flex-1 overflow-y-auto">{convList}</div>
      </Card>
      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title={t("conversations")}>
        {convList}
      </Drawer>

      {/* Chat */}
      <Card className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <button
            type="button"
            aria-label={t("conversations")}
            onClick={() => setDrawerOpen(true)}
            className="grid h-9 w-9 place-items-center rounded-full bg-cream lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="grid h-9 w-9 place-items-center rounded-full bg-leaf text-white">
            <Bot className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="truncate font-display font-extrabold text-forest">{t("assistantTitle")}</h1>
            <p className="truncate text-xs text-muted">{t("assistantSub")}</p>
          </div>
          {user?.role === "admin" && (
            <Button variant="secondary" size="sm" onClick={testGemini} loading={testing} className="shrink-0">
              <Zap className="h-4 w-4" />
              <span className="hidden sm:inline">{t("testGemini")}</span>
            </Button>
          )}
          {/* Width on a wrapper: Select's own field class sets w-full, which
              beats w-24 in the Tailwind stylesheet order and overflowed the
              header on phones (measured right edge 433px at 390px). */}
          <div className="w-24 shrink-0">
            <Select
              value={chatLang}
              onChange={(e) => setChatLang(e.target.value as "bn" | "en")}
              aria-label={t("changeLanguage")}
            >
              <option value="bn">বাংলা</option>
              <option value="en">English</option>
            </Select>
          </div>
        </div>

        {assistantMissing && (
          <div className="border-b border-[#f4e4bf] bg-[#fff8e9] px-4 py-2 text-[13px] text-[#80632d]">
            {t("advisorFallbackNote")}
          </div>
        )}

        {testResult && (
          <div
            className={`flex items-start justify-between gap-2 border-b px-4 py-2 text-[13px] ${
              testResult.ok
                ? "border-[#cfe8d8] bg-[#eefaf2] text-[#1d5c38]"
                : "border-[#f1c4c4] bg-[#fceaea] text-[#a53f3f]"
            }`}
          >
            <p className="min-w-0 break-words">
              <span className="font-bold">
                {testResult.ok ? `✓ ${t("geminiTestOk")}` : `✗ ${t("geminiTestFail")}`}
              </span>
              {` · ${testResult.latency_ms} ms`}
              {testResult.error ? ` — ${testResult.error}` : ""}
            </p>
            <button type="button" aria-label="Dismiss" onClick={() => setTestResult(null)} className="shrink-0">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        <div className="thin-scroll flex-1 overflow-y-auto px-4 py-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 py-8 text-center">
              <span className="grid h-16 w-16 place-items-center rounded-full bg-mint text-3xl">🌾</span>
              <div>
                <p className="font-display text-lg font-bold text-forest">{t("assistantTitle")}</p>
                <p className="mt-1 max-w-sm text-sm text-muted">{t("assistantSub")}</p>
              </div>
              <div className="flex max-w-md flex-wrap justify-center gap-2">
                {["suggestedQ1", "suggestedQ2", "suggestedQ3", "suggestedQ4"].map((k) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => {
                      setInput(t(k));
                    }}
                    className="rounded-full border border-line bg-white px-3.5 py-2 text-[13px] font-semibold text-ink hover:border-leaf"
                  >
                    {t(k)}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((m, i) => (
                <div key={i} className={`flex gap-2.5 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                  <span
                    className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${
                      m.role === "user" ? "bg-marigold text-[#2e2110]" : "bg-leaf text-white"
                    }`}
                  >
                    {m.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                  </span>
                  <div
                    className={`max-w-[85%] rounded-3xl px-4 py-3 text-sm leading-relaxed sm:max-w-[75%] ${
                      m.role === "user" ? "bg-forest text-white" : "bg-cream text-ink"
                    }`}
                  >
                    {m.imageUrl && (
                      <img src={m.imageUrl} alt="" className="mb-2 max-h-40 w-auto rounded-2xl object-cover" />
                    )}
                    {(m.content || m.streaming) && (
                      <p className="whitespace-pre-wrap">
                        {m.streaming && !m.content ? t("ti_preparing") : m.content}
                      </p>
                    )}
                    {/* Speaker button only when a voice exists for this
                        reply's script — without a Bangla voice the
                        browser would read only the English words. */}
                    {m.role === "assistant" &&
                      m.content &&
                      !m.streaming &&
                      voiceReadoutSupported &&
                      pickVoice(voices, m.content) && (
                      <button
                        type="button"
                        aria-label={speakingIndex === i ? t("stopReading") : t("readAloud")}
                        title={speakingIndex === i ? t("stopReading") : t("readAloud")}
                        onClick={() => speak(i, m.content)}
                        className={`mt-2 grid h-7 w-7 place-items-center rounded-full transition ${
                          speakingIndex === i ? "bg-leaf text-white" : "bg-white/70 text-forest hover:bg-white"
                        }`}
                      >
                        {speakingIndex === i ? <Square className="h-3.5 w-3.5" /> : <Volume2 className="h-4 w-4" />}
                      </button>
                    )}
                    {(m.sources || []).length > 0 && (
                      <p className="mt-2 border-t border-line pt-2 text-xs text-muted">
                        {t("sourcesLabel")}:{" "}
                        {m.sources!.map((s) => s.title).join(" · ")}
                      </p>
                    )}
                  </div>
                </div>
              ))}
              {busy && !messages[messages.length - 1]?.streaming && (
                <div className="flex gap-2.5">
                  <span className="grid h-8 w-8 place-items-center rounded-full bg-leaf text-white">
                    <Bot className="h-4 w-4" />
                  </span>
                  <div className="rounded-3xl bg-cream px-4 py-3 text-sm text-muted">{t("ti_preparing")}</div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <div className="border-t border-line">
          {attachedPreview && (
            <div className="relative w-fit px-3 pt-3">
              <img src={attachedPreview} alt="" className="h-20 w-20 rounded-2xl object-cover" />
              <button
                type="button"
                aria-label={t("removeImage")}
                title={t("removeImage")}
                onClick={clearAttachment}
                className="absolute -right-1.5 -top-0 grid h-6 w-6 place-items-center rounded-full bg-forest text-white"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          <form
            className="flex gap-2 p-3"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              aria-label={t("attachImage")}
              onChange={onImagePicked}
            />
            <button
              type="button"
              aria-label={t("attachImage")}
              title={t("attachImage")}
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
              className={`grid h-10 w-10 shrink-0 place-items-center rounded-full transition disabled:opacity-50 ${
                attachedImage ? "bg-mint text-forest" : "bg-cream text-forest hover:bg-mint"
              }`}
            >
              <ImagePlus className="h-5 w-5" />
            </button>
            {voiceInputSupported && (
              <button
                type="button"
                aria-label={recording ? t("listening") : t("voiceInput")}
                title={recording ? t("listening") : t("voiceInput")}
                onClick={toggleRecording}
                disabled={busy}
                className={`grid h-10 w-10 shrink-0 place-items-center rounded-full transition disabled:opacity-50 ${
                  recording ? "animate-pulse bg-red-100 text-red-600" : "bg-cream text-forest hover:bg-mint"
                }`}
              >
                <Mic className="h-5 w-5" />
              </button>
            )}
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t("askQuestion")}
              aria-label={t("askQuestion")}
              className="flex-1"
            />
            <Button type="submit" loading={busy} disabled={!input.trim() && !attachedImage} aria-label={t("send")}>
              <Send className="h-4 w-4" />
              <span className="hidden sm:inline">{t("send")}</span>
            </Button>
          </form>
        </div>
      </Card>
    </div>
  );
}
