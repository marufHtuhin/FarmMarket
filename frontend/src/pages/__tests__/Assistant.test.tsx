import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/test-utils";
import { AssistantPage } from "../Assistant";

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return {
    ...actual,
    assistantApi: {
      chat: vi.fn(),
      chatImage: vi.fn(),
      test: vi.fn(),
      conversations: vi.fn(),
      conversation: vi.fn(),
    },
    advisorApi: { advice: vi.fn(), languages: vi.fn() },
    streamAssistantChat: vi.fn(),
  };
});

import { assistantApi } from "../../services/api";

const CHAT_IMAGE_REPLY = "The leaf shows early blight. Remove affected leaves and spray a copper fungicide.";

function attachImageFile() {
  const file = new File(["fake-image-bytes"], "leaf.jpg", { type: "image/jpeg" });
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

const BN_REPLY = "পাতায় দাগ দেখা যাচ্ছে। আক্রান্ত পাতা সরিয়ে ফেলুন।";
const BANGLISH_REPLY = "Dhan katar somoy hoye geche, ekhon katte paren.";

interface FakeVoice {
  lang: string;
  name: string;
}

class FakeUtterance {
  text: string;
  lang = "";
  voice: FakeVoice | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(text: string) {
    this.text = text;
  }
}

/** Install a fake speechSynthesis whose voice list comes from the given
 *  getter (so a test can change it and fire "voiceschanged"). Returns the
 *  speak/cancel spies and a `fire` helper for synthetic events. */
function installSpeechSynthesis(getVoicesImpl: () => FakeVoice[]) {
  const speak = vi.fn();
  const cancel = vi.fn();
  const listeners = new Map<string, Array<() => void>>();
  const synth = {
    speak,
    cancel,
    getVoices: vi.fn(getVoicesImpl),
    addEventListener: vi.fn((type: string, fn: () => void) => {
      const arr = listeners.get(type) ?? [];
      arr.push(fn);
      listeners.set(type, arr);
    }),
    removeEventListener: vi.fn(),
  };
  (window as unknown as Record<string, unknown>).speechSynthesis = synth;
  (window as unknown as Record<string, unknown>).SpeechSynthesisUtterance = FakeUtterance;
  const fire = (type: string) => listeners.get(type)?.forEach((fn) => fn());
  return { speak, cancel, synth, fire };
}

/** Render the page and send a photo question so one assistant reply with
 *  the given text appears. */
async function sendImageAndWaitForReply(reply: string) {
  vi.mocked(assistantApi.chatImage).mockResolvedValueOnce({
    reply,
    mode: "gemini",
    conversation_id: 7,
    sources: [],
  });
  renderWithProviders(<AssistantPage />, { route: "/assistant" });
  attachImageFile();
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => {
    expect(screen.getByText(reply)).toBeInTheDocument();
  });
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("fm_lang", "en");
  // jsdom has no scrollIntoView — the page scrolls to the newest message.
  Element.prototype.scrollIntoView = vi.fn();
  vi.mocked(assistantApi.conversations).mockResolvedValue([]);
  // Never-resolving by default: the local message list stays untouched
  // unless a test opts into the refetch-merge behaviour.
  vi.mocked(assistantApi.conversation).mockImplementation(() => new Promise(() => {}));
  // jsdom has no createObjectURL — stub it so photo previews work in tests.
  URL.createObjectURL = vi.fn(() => "blob:fake-preview");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.clearAllMocks();
  delete (window as unknown as Record<string, unknown>).SpeechRecognition;
  delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  delete (window as unknown as Record<string, unknown>).speechSynthesis;
  delete (window as unknown as Record<string, unknown>).SpeechSynthesisUtterance;
});

describe("AssistantPage image upload", () => {
  it("renders the attach-photo button next to the chat input", () => {
    renderWithProviders(<AssistantPage />, { route: "/assistant" });
    expect(screen.getByRole("button", { name: "Attach a photo" })).toBeInTheDocument();
    expect(screen.getByLabelText("Type your question…")).toBeInTheDocument();
  });

  it("shows a thumbnail preview with a remove button after picking an image", () => {
    renderWithProviders(<AssistantPage />, { route: "/assistant" });
    attachImageFile();

    const preview = document.querySelector('img[src="blob:fake-preview"]');
    expect(preview).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove photo" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Remove photo" }));
    expect(document.querySelector('img[src="blob:fake-preview"]')).not.toBeInTheDocument();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake-preview");
  });

  it("sends the photo via chatImage and shows the photo + reply, adopting the returned conversation id", async () => {
    vi.mocked(assistantApi.chatImage).mockResolvedValueOnce({
      reply: CHAT_IMAGE_REPLY,
      mode: "gemini",
      conversation_id: 7,
      sources: [],
    });
    // The conversation refetch after adopting the id returns the same
    // thread — the photo thumbnail must survive the merge.
    vi.mocked(assistantApi.conversation).mockResolvedValueOnce({
      id: "7",
      messages: [
        { role: "user", content: "What disease is this?" },
        { role: "assistant", content: CHAT_IMAGE_REPLY },
      ],
    });
    renderWithProviders(<AssistantPage />, { route: "/assistant" });

    attachImageFile();
    fireEvent.change(screen.getByLabelText("Type your question…"), {
      target: { value: "What disease is this?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(assistantApi.chatImage).toHaveBeenCalledTimes(1);
    });
    const call = vi.mocked(assistantApi.chatImage).mock.calls[0][0];
    expect(call.image).toBeInstanceOf(File);
    expect(call.image.name).toBe("leaf.jpg");
    expect(call.message).toBe("What disease is this?");
    expect(call.language).toBe("en");
    expect(call.conversation_id).toBeUndefined();

    await waitFor(() => {
      expect(screen.getByText(CHAT_IMAGE_REPLY)).toBeInTheDocument();
    });
    // Photo still shown in the user bubble after the conversation refetch.
    await waitFor(() => {
      expect(assistantApi.conversation).toHaveBeenCalledWith("7");
    });
    expect(document.querySelector('img[src="blob:fake-preview"]')).toBeInTheDocument();
    // Input + preview cleared on success.
    expect(screen.getByLabelText("Type your question…")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Remove photo" })).not.toBeInTheDocument();
  });

  it("shows the server error and keeps the input + photo for retry when chatImage fails", async () => {
    vi.mocked(assistantApi.chatImage).mockRejectedValueOnce({
      response: { data: { detail: "No Gemini key configured" }, status: 503 },
      message: "Request failed with status code 503",
    });
    renderWithProviders(<AssistantPage />, { route: "/assistant" });

    attachImageFile();
    fireEvent.change(screen.getByLabelText("Type your question…"), {
      target: { value: "What disease is this?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText(/No Gemini key configured/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Could not get an answer/)).toBeInTheDocument();
    // Retry state preserved.
    expect(screen.getByLabelText("Type your question…")).toHaveValue("What disease is this?");
    expect(document.querySelector('img[src="blob:fake-preview"]')).toBeInTheDocument();
  });
});

describe("AssistantPage voice", () => {
  it("hides the mic button when SpeechRecognition is unsupported", () => {
    renderWithProviders(<AssistantPage />, { route: "/assistant" });
    expect(screen.queryByRole("button", { name: "Speak" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Listening…" })).not.toBeInTheDocument();
  });

  it("shows the mic when supported and puts the transcript into the input", async () => {
    const instances: Array<{
      lang: string;
      onresult: ((e: { results: Array<Array<{ transcript: string }>> }) => void) | null;
      onend: (() => void) | null;
      start: () => void;
      stop: () => void;
    }> = [];
    class FakeRecognition {
      lang = "";
      interimResults = false;
      continuous = false;
      onresult: ((e: { results: Array<Array<{ transcript: string }>> }) => void) | null = null;
      onerror: (() => void) | null = null;
      onend: (() => void) | null = null;
      start = vi.fn();
      stop = vi.fn();
      abort = vi.fn();
      constructor() {
        instances.push(this);
      }
    }
    (window as unknown as Record<string, unknown>).SpeechRecognition = FakeRecognition;

    renderWithProviders(<AssistantPage />, { route: "/assistant" });
    const mic = screen.getByRole("button", { name: "Speak" });
    fireEvent.click(mic);

    expect(instances).toHaveLength(1);
    expect(instances[0].lang).toBe("en-US");
    expect(screen.getByRole("button", { name: "Listening…" })).toBeInTheDocument();

    act(() => {
      instances[0].onresult?.({ results: [[{ transcript: "tomato price" }]] });
    });
    expect(screen.getByLabelText("Type your question…")).toHaveValue("tomato price");

    act(() => {
      instances[0].onend?.();
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Speak" })).toBeInTheDocument();
    });
  });

  it("hides speaker buttons when speechSynthesis is unavailable", async () => {
    vi.mocked(assistantApi.chatImage).mockResolvedValueOnce({
      reply: CHAT_IMAGE_REPLY,
      mode: "gemini",
      conversation_id: 7,
      sources: [],
    });
    renderWithProviders(<AssistantPage />, { route: "/assistant" });
    attachImageFile();
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText(CHAT_IMAGE_REPLY)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Read aloud" })).not.toBeInTheDocument();
  });

  it("reads an assistant reply aloud and stops on a second click when supported", async () => {
    const enVoice = { lang: "en-US", name: "English US" };
    const { speak, cancel } = installSpeechSynthesis(() => [enVoice]);

    await sendImageAndWaitForReply(CHAT_IMAGE_REPLY);

    const readButton = screen.getByRole("button", { name: "Read aloud" });
    fireEvent.click(readButton);

    expect(speak).toHaveBeenCalledTimes(1);
    const utterance = speak.mock.calls[0][0] as FakeUtterance;
    expect(utterance.text).toBe(CHAT_IMAGE_REPLY);
    expect(utterance.voice).toBe(enVoice);
    expect(utterance.lang).toBe("en-US");
    expect(screen.getByRole("button", { name: "Stop reading" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Stop reading" }));
    expect(cancel).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Read aloud" })).toBeInTheDocument();
  });

  it("uses the Bangla voice for a Bangla reply", async () => {
    const bnVoice = { lang: "bn-BD", name: "Bangla" };
    const enVoice = { lang: "en-US", name: "English US" };
    const { speak } = installSpeechSynthesis(() => [enVoice, bnVoice]);

    await sendImageAndWaitForReply(BN_REPLY);

    fireEvent.click(screen.getByRole("button", { name: "Read aloud" }));
    expect(speak).toHaveBeenCalledTimes(1);
    const utterance = speak.mock.calls[0][0] as FakeUtterance;
    expect(utterance.text).toBe(BN_REPLY);
    expect(utterance.voice).toBe(bnVoice);
    expect(utterance.lang).toBe("bn-BD");
  });

  it("hides the speaker button for a Bangla reply when no Bangla voice exists", async () => {
    installSpeechSynthesis(() => [{ lang: "en-US", name: "English US" }]);
    await sendImageAndWaitForReply(BN_REPLY);
    expect(screen.queryByRole("button", { name: "Read aloud" })).not.toBeInTheDocument();
  });

  it("hides the speaker button for an English reply when no English voice exists", async () => {
    installSpeechSynthesis(() => [{ lang: "bn-BD", name: "Bangla" }]);
    await sendImageAndWaitForReply(CHAT_IMAGE_REPLY);
    expect(screen.queryByRole("button", { name: "Read aloud" })).not.toBeInTheDocument();
  });

  it("uses the English voice for a Banglish reply even when the chat language is Bangla", async () => {
    const bnVoice = { lang: "bn-BD", name: "Bangla" };
    const enVoice = { lang: "en-US", name: "English US" };
    const { speak } = installSpeechSynthesis(() => [bnVoice, enVoice]);

    vi.mocked(assistantApi.chatImage).mockResolvedValueOnce({
      reply: BANGLISH_REPLY,
      mode: "gemini",
      conversation_id: 7,
      sources: [],
    });
    renderWithProviders(<AssistantPage />, { route: "/assistant" });
    // Switch the chat language to Bangla via the header select (UI stays
    // English, chatLang becomes "bn") — the Latin-script reply must still
    // get the English voice.
    fireEvent.change(screen.getByLabelText("Change language"), { target: { value: "bn" } });
    attachImageFile();
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText(BANGLISH_REPLY)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "Read aloud" }));
    expect(speak).toHaveBeenCalledTimes(1);
    const utterance = speak.mock.calls[0][0] as FakeUtterance;
    expect(utterance.voice).toBe(enVoice);
    expect(utterance.lang).toBe("en-US");
  });

  it("shows the speaker button once voices arrive via voiceschanged", async () => {
    let currentVoices: FakeVoice[] = [];
    const bnVoice = { lang: "bn-BD", name: "Bangla" };
    const { fire } = installSpeechSynthesis(() => currentVoices);

    await sendImageAndWaitForReply(BN_REPLY);

    // Voices not loaded yet: no button (never a half-read reply).
    expect(screen.queryByRole("button", { name: "Read aloud" })).not.toBeInTheDocument();

    act(() => {
      currentVoices = [bnVoice];
      fire("voiceschanged");
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Read aloud" })).toBeInTheDocument();
    });
  });
});
