"""Krishi Bondhu assistant: Gemini answers from its own knowledge, with a
template fallback built from the FarmMarket notes.

Modes, always reported to the caller:
  * "gemini"   - Google Gemini (GEMINI_API_KEY set). The model answers the
                 farmer's question fully from its own knowledge, like the
                 Gemini app — no retrieved notes are sent with the prompt
                 (removed 2026-11-17 at the user's request). Stored price
                 rows are still included so price questions use real
                 records. The system instruction still forbids inventing
                 prices, weather, dates or facts, and still refuses
                 pesticide/fertiliser dosages (extension officer).
  * "template" - deterministic reply built from the same retrieved docs and
                 price rows. Used when no key is configured or on ANY Gemini
                 failure (import error, timeout, API error). Never raises.

Transport: plain HTTPS REST (httpx) against the Generative Language API,
NOT the google-generativeai SDK — the SDK's gRPC transport hung
indefinitely from the user's network (found live 2026-11-16: no response
even after 30s), while plain HTTPS works. The API key travels in the
x-goog-api-key header, never in a URL or a log line.

Timeout: the Gemini call runs in a daemon worker thread joined with a
limit (default 20s, overridable per-process with GEMINI_TIMEOUT_S).
If it times out the request returns template mode immediately; the
worker thread is abandoned (daemon threads never block process shutdown)
and its result is discarded. Do NOT use ThreadPoolExecutor here: its
context manager waits for pending work on exit, which turned the timeout
into an unbounded hang (found live 2026-11-16 — the chat spun forever).

Model fallback chain: if the primary model call fails for ANY reason
(including a timeout), the call is retried ONCE with gemini-3.5-flash-lite
before falling back to template — for the blocking call, the probe, and
the stream (streaming retries only before the first token: once tokens
have gone out, a retry would duplicate text). The retry shares the
original call's overall deadline (GEMINI_TIMEOUT_S for chat, 60s for the
probe, STREAM_TOTAL_TIMEOUT_S for a stream); it never doubles the bound.
Which models were tried is recorded in the last-error diagnostic.

Diagnostics: the last Gemini failure is recorded in LAST_GEMINI_ERROR
(read it with get_last_gemini_error()) and logged at warning level, so a
deployer can see WHY template mode is active. It never contains the key.
test_gemini() makes one tiny live call ("say hi", max 8 output tokens) so
an admin can prove the key + model work from THIS process — changing the
key in .env does nothing until the backend restarts, because .env is
loaded once at process start (load_dotenv in main.py). The probe waits
up to 60s (GEMINI_TEST_TIMEOUT_S), not the 20s chat bound, so it can
tell "slow" from "blocked" and report honest latency. It also reports
per-stage timing — connect_ms (a TCP connect probe to the API host) and
ttfb_ms (request dispatch to response headers) — so a stalled call can
be localised: fast connect + no first byte means the stall is after
connect (the exact symptom seen from the user's machine 2026-11-17,
where the REST call read-timed out on BOTH Wi-Fi and a mobile hotspot).

Streaming: stream_gemini_reply() yields reply text as it arrives via
:streamGenerateContent (alt=sse). The template fallback is instant and
is never streamed.

Vision: analyze_crop_image() sends a crop photo as an inlineData part
through the SAME _gemini_post transport (model chain, shared deadline,
one fallback retry) and returns a structured disease analysis
(রোগের নাম / কারণ / সমাধান / প্রতিরোধ, plain-text labels — no emojis
anywhere in the assistant's replies, per the user's 17 Nov 2026 rule).
There is no template fallback for vision: a failure is a clear error,
never a fabricated diagnosis.

Rate limiting: per-user, in-memory (dict of user_id -> deque of timestamps),
default 10 messages/minute, overridable with ASSISTANT_RATE_LIMIT_PER_MIN
(read on every call so tests can override it without re-importing). The
limit is checked by the router, which returns HTTP 429 when exceeded.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

GEMINI_TIMEOUT_S = 20
# Wall-clock cap for one streamed reply (the per-token read timeout is
# GEMINI_TIMEOUT_S; this bounds a slow-but-alive stream).
STREAM_TOTAL_TIMEOUT_S = 180
DEFAULT_MODEL = "gemini-3.8-flash"
# One retry with this model when the primary fails for any reason
# (see _model_chain); it shares the original call's deadline.
# NOTE (17 Nov 2026): gemini-2.5-flash was the fallback until Google
# retired it for new API users (deprecated 2 Nov 2026, shutdown 1 Dec
# 2026; returns 404 "no longer available to new users"). Google names
# gemini-3.5-flash-lite as its replacement, and it was verified live
# from the user's own machine (200 in 8.8s) the same evening.
FALLBACK_MODEL = "gemini-3.5-flash-lite"
# TCP connect budget for every Gemini call (the read budget is the
# configured GEMINI_TIMEOUT_S / remaining deadline — see _gemini_post_once).
CONNECT_TIMEOUT_S = 5.0
# Slack added to the daemon-thread join so httpx's own timeout raises
# first: its error names the real failure (ReadTimeout, ConnectError)
# instead of a generic TimeoutError. The retry still fits inside the
# overall bound — the fallback attempt only starts when time remains on
# the shared deadline.
JOIN_SLACK_S = 1.0
DEFAULT_RATE_LIMIT_PER_MIN = 10
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_API_HOST = "generativelanguage.googleapis.com"

# Last Gemini failure, for the /assistant/status diagnostic endpoint:
# {"type": ..., "message": ..., "at": <UTC ISO timestamp>,
#  "models_tried": [...], "model": <last model tried>}. Never holds the key.
LAST_GEMINI_ERROR: dict = {}


def get_last_gemini_error() -> dict:
    """Copy of the last recorded Gemini failure ({} when none / last call OK)."""
    return dict(LAST_GEMINI_ERROR)


def _record_gemini_error(exc: Exception) -> None:
    """Record + log a Gemini failure for the /assistant/status diagnostic.
    Silent degradation hid a retired model for a full day (2026-11-16), so
    every Gemini failure goes through here. The key is never logged/stored.
    When the failure came out of the model fallback chain, the exception
    carries gemini_models_tried (set by _gemini_post / stream_gemini_reply)
    and the record names the models tried + the last one attempted."""
    entry: dict = {
        "type": type(exc).__name__,
        "message": str(exc),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    models_tried = getattr(exc, "gemini_models_tried", None)
    if models_tried:
        entry["models_tried"] = list(models_tried)
        entry["model"] = models_tried[-1]
    LAST_GEMINI_ERROR.clear()
    LAST_GEMINI_ERROR.update(entry)
    logger.warning("Gemini failed (%s: %s)", type(exc).__name__, exc)


def _model_chain() -> list[str]:
    """Primary model first, then the fallback — unless the primary IS the
    fallback (GEMINI_MODEL=gemini-3.5-flash-lite), in which case retrying it
    would just repeat the same call."""
    primary = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    return [primary] if primary == FALLBACK_MODEL else [primary, FALLBACK_MODEL]


def _measure_connect_ms(host: str, port: int = 443,
                        timeout_s: float = CONNECT_TIMEOUT_S) -> float | None:
    """TCP connect time to host:port in ms, or None when unreachable.
    A separate lightweight probe (its own socket, no API call): the
    /assistant/test diagnostic uses it to tell 'cannot reach Google at
    all' from 'connected but the response never arrives' (the ReadTimeout
    the user hit live on 2026-11-17). Runs inside the daemon worker
    thread, so a DNS stall is still bounded by the thread join."""
    import socket

    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return (time.monotonic() - t0) * 1000
    except OSError:
        return None


def _ms(value: float | None) -> int | None:
    """Whole-ms timing for a JSON response (None stays None)."""
    return int(round(value)) if value is not None else None


def _gemini_timeout_s() -> float:
    """Effective Gemini timeout: GEMINI_TIMEOUT_S env override, else the
    module default. Read on every call so tests can patch the constant."""
    try:
        return max(5.0, float(os.getenv("GEMINI_TIMEOUT_S", str(GEMINI_TIMEOUT_S))))
    except ValueError:
        return float(GEMINI_TIMEOUT_S)

SYSTEM_INSTRUCTION = (
    "You are Krishi Bondhu, an expert farming assistant for Bangladeshi "
    "farmers. Answer the farmer's question fully from your own knowledge, "
    "like a knowledgeable farming adviser — never refuse a farming "
    "question, and never give a one-line deflection. Use simple, fluent "
    "Bangla (or English when the farmer asks in English), short sentences, "
    "and farmer-friendly words — no jargon. Give short, clear, practical "
    "advice the farmer can act on today. For disease questions, structure "
    "your answer as cause, solution, and prevention: what caused it, how "
    "to fix it, and how to stop it coming back. Use local pesticide and "
    "fertiliser NAMES where relevant — names only, never amounts. Do not "
    "use emojis in your replies. Never invent prices, "
    "weather, dates, yields or specific facts. Do not give pesticide or "
    "fertiliser dosages; tell the farmer to ask a local extension "
    "officer. When you greet the user, use a simple 'Hi' or 'Hello'; "
    "never use religious greetings such as Nomoskar, Salam, or Adab. "
    "Match the user's script: if they write in Bangla script, reply in "
    "Bangla; if they write in English, reply in English; if they write "
    "in Banglish (romanized Bangla), reply in Banglish."
)


def rate_limit_per_min() -> int:
    try:
        return max(1, int(os.getenv("ASSISTANT_RATE_LIMIT_PER_MIN",
                                    str(DEFAULT_RATE_LIMIT_PER_MIN))))
    except ValueError:
        return DEFAULT_RATE_LIMIT_PER_MIN


class AssistantRateLimiter:
    """Tiny in-process per-user limiter (1-minute window)."""

    def __init__(self, window_s: int = 60):
        self.window_s = window_s
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, user_id: str) -> bool:
        now = time.monotonic()
        q = self.hits[str(user_id)]
        while q and now - q[0] > self.window_s:
            q.popleft()
        if len(q) >= rate_limit_per_min():
            return False
        q.append(now)
        return True

    def reset(self) -> None:
        self.hits.clear()


limiter = AssistantRateLimiter()


def reset_limiter() -> None:
    limiter.reset()


# ---------------------------------------------------------------------------
# Template fallback
# ---------------------------------------------------------------------------
_T = {
    "en": {
        "header": "This is template advice from FarmMarket notes (no AI model was used).",
        "notes_say": "What the notes say:",
        "no_docs": ("I could not find notes that answer this question. Please ask about "
                    "a crop, harvest, storage, prices or weather."),
        "prices": "Reference prices from our records:",
        "no_prices": "No stored price records match your question.",
    },
    "bn": {
        "header": "এটি ফার্মমার্কেট নোট থেকে টেমপ্লেট পরামর্শ (কোনো এআই মডেল ব্যবহার করা হয়নি)।",
        "notes_say": "নোটে যা আছে:",
        "no_docs": ("এই প্রশ্নের উত্তর দেওয়ার মতো কোনো নোট পাওয়া যায়নি। ফসল, ফসল তোলা, "
                    "সংরক্ষণ, দাম বা আবহাওয়া সম্পর্কে জিজ্ঞাসা করুন।"),
        "prices": "আমাদের রেকর্ড থেকে রেফারেন্স দাম:",
        "no_prices": "আপনার প্রশ্নের সঙ্গে মেলে এমন কোনো সংরক্ষিত দামের রেকর্ড নেই।",
    },
}


def _extension_officer_line(language: str) -> str:
    """Reuse the advisor module's template line (bn/en) instead of duplicating it."""
    try:
        from . import advisor as _advisor

        lang = _advisor.LANGUAGES.get(language) or _advisor.LANGUAGES["en"]
        out = _advisor.template_advice("crop", lang, None, None, None)
        return out["risks"][-1]  # the "ask your local extension officer" line
    except Exception:
        return {"bn": "বড় সিদ্ধান্তের আগে স্থানীয় কৃষি সম্প্রসারণ কর্মকর্তার পরামর্শ নিন।",
                "en": "Ask your local agriculture extension officer before making big decisions."}.get(
                    language, "Ask your local agriculture extension officer before making big decisions.")


def _format_price_row(row: dict) -> str:
    recorded = (row.get("recorded_at") or "")[:10] or "date unknown"
    place = row.get("district") or ""
    if row.get("market_name"):
        place = f"{place} ({row['market_name']})" if place else row["market_name"]
    place = f", {place}" if place else ""
    return (f"- {row.get('product_name')} — {row.get('price_per_unit')} per "
            f"{row.get('unit', 'kg')}{place} (source: {row.get('source')}; "
            f"recorded {recorded})")


def template_reply(message: str, language: str, context_docs: list[dict],
                   price_rows: list[dict]) -> str:
    t = _T.get(language, _T["en"])
    parts = [t["header"], ""]
    bullets: list[str] = []
    for doc in context_docs or []:
        for b in doc.get("bullets") or []:
            line = f"- {b} ({doc.get('title', doc.get('ref', ''))})"
            if line not in bullets:
                bullets.append(line)
            if len(bullets) >= 4:
                break
        if len(bullets) >= 4:
            break
    if bullets:
        parts.append(t["notes_say"])
        parts.extend(bullets[:4])
    else:
        parts.append(t["no_docs"])
    parts.append("")
    if price_rows:
        parts.append(t["prices"])
        parts.extend(_format_price_row(r) for r in price_rows)
        parts.append("")
    parts.append(_extension_officer_line(language))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Gemini path (plain REST over httpx — see the module docstring for why)
# ---------------------------------------------------------------------------
def _gemini_prompt(message: str, language: str,
                   price_rows: list[dict]) -> str:
    # No retrieved notes: Gemini answers from its own knowledge (the notes
    # were removed from this prompt 2026-11-17 at the user's request).
    # Stored price rows stay: they are real records, so price questions
    # get real numbers instead of invented ones.
    prices_text = "\n".join(_format_price_row(r) for r in price_rows) \
        if price_rows else "(no stored price records match)"
    lang_name = "Bangla" if language == "bn" else "English"
    return (f"Reply in {lang_name}.\n\n"
            f"Stored reference prices:\n{prices_text}\n\n"
            f"Farmer's question:\n{message}")


def _extract_chunk_text(chunk: dict) -> str:
    """Text of a generateContent/streamGenerateContent response chunk.
    Tolerates missing candidates/content/parts (returns ""). Deliberately
    NOT stripped: stream chunks carry their own spacing ("Hello " +
    "world"), and stripping per chunk would glue words together."""
    candidates = chunk.get("candidates") or []
    parts = ((candidates[0].get("content") or {}).get("parts") or []
             if candidates else [])
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


# The /assistant/test probe gets a longer bound than chat (60s): its job is
# to distinguish "slow" from "blocked". A ReadTimeout at the 20s chat bound
# proves nothing about a key that answers in 45s (seen live 2026-11-17:
# key + model correct, read timed out from the user's network).
GEMINI_TEST_TIMEOUT_S = 60


def _gemini_post_once(prompt: str, model: str, api_key: str,
                      generation_config: dict | None, timeout_s: float,
                      timing: dict | None,
                      parts: list[dict] | None = None) -> str:
    """One blocking generateContent call against ONE model, bounded by
    timeout_s. Raises on any failure; the caller decides whether to retry
    with the next model in the chain. timeout_s is the REMAINING budget
    on the shared deadline for a retry attempt, not the full configured
    timeout — the chain never exceeds the overall bound.

    `parts` overrides the request contents: when given (the vision path),
    the parts are sent as-is (e.g. an inlineData image part + a text
    part); otherwise the contents are a single text part built from
    `prompt`. Everything else — timeout split, daemon-thread backstop,
    error handling — is identical for text and vision calls.

    The httpx timeout is split explicitly: connect 5s, read = timeout_s
    (write 10s, pool 5s). When `timing` is given (the /assistant/test
    probe only), it is filled with connect_ms (a TCP connect probe to
    the API host) and ttfb_ms (request dispatch -> response headers,
    via httpx event hooks) so a stalled call can be localised. The key
    goes in the x-goog-api-key header, never in a URL."""
    import httpx  # already a core dependency (requirements.txt)

    url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [{"parts": parts if parts is not None else [{"text": prompt}]}],
    }
    if generation_config:
        payload["generationConfig"] = generation_config
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    # The httpx timeout is the primary bound; the daemon-thread join below is
    # the backstop (e.g. a DNS stall). A hung call must never block the
    # request — ThreadPoolExecutor.__exit__ waits for pending work, which
    # defeated the old timeout entirely.
    box: dict = {}

    def _generate() -> None:
        try:
            hook_times: dict[str, float] = {}
            client_kwargs: dict = {"timeout": httpx.Timeout(
                connect=CONNECT_TIMEOUT_S, read=timeout_s,
                write=10.0, pool=5.0)}
            if timing is not None:
                # Own-socket probe first: it runs inside this worker, so a
                # DNS/connect stall is still bounded by the join below.
                # Capped at the attempt's remaining budget.
                timing["connect_ms"] = _measure_connect_ms(
                    GEMINI_API_HOST, timeout_s=min(CONNECT_TIMEOUT_S, timeout_s))

                def _on_request(request):  # noqa: ANN001, ANN202
                    hook_times["request"] = time.monotonic()

                def _on_response(response):  # noqa: ANN001, ANN202
                    hook_times["response"] = time.monotonic()

                client_kwargs["event_hooks"] = {"request": [_on_request],
                                                "response": [_on_response]}
            with httpx.Client(**client_kwargs) as client:
                resp = client.post(url, json=payload, headers=headers)
            if (timing is not None and "request" in hook_times
                    and "response" in hook_times):
                timing["ttfb_ms"] = ((hook_times["response"]
                                      - hook_times["request"]) * 1000)
            if resp.status_code == 404:
                raise RuntimeError(
                    f"Gemini model not found: {model} "
                    "(retired or misspelled — check GEMINI_MODEL)")
            if resp.status_code >= 400:
                # Explicit status check instead of raise_for_status(): the
                # error body usually names the real problem (bad key, quota).
                try:
                    detail = (resp.json().get("error") or {}).get("message", "")
                except Exception:
                    detail = ""
                raise RuntimeError(
                    f"Gemini API error HTTP {resp.status_code}: "
                    f"{detail or 'no detail'}")
            data = resp.json()
            text = _extract_chunk_text(data).strip()  # strip the WHOLE reply
            if not text:
                candidates = data.get("candidates") or []
                reason = (candidates[0] or {}).get("finishReason", "unknown") \
                    if candidates else "no candidates"
                raise RuntimeError(
                    f"Gemini returned no text (finishReason: {reason})")
            box["text"] = text
        except Exception as exc:  # noqa: BLE001 - re-raised on the main thread
            box["error"] = exc

    worker = threading.Thread(target=_generate, daemon=True)
    worker.start()
    worker.join(timeout=timeout_s + JOIN_SLACK_S)  # slack so httpx raises first
    if worker.is_alive():
        raise TimeoutError(f"Gemini call exceeded {timeout_s:g}s")
    if "error" in box:
        raise box["error"]
    return box["text"]


def _gemini_post(prompt: str, generation_config: dict | None = None,
                 timeout_s: float | None = None,
                 timing: dict | None = None,
                 parts: list[dict] | None = None) -> str:
    """generateContent with a one-model fallback chain: if the primary
    model fails for ANY reason (timeout included), retry ONCE with
    gemini-3.5-flash-lite before giving up. Both attempts share ONE deadline
    (timeout_s from the call start): the retry gets only the time left,
    so the chain never doubles the bound. timeout_s overrides the
    GEMINI_TIMEOUT_S bound (used by the test probe); it is floored at 5s
    like the default. When the chain is exhausted the last exception is
    re-raised with a gemini_models_tried attribute naming every model
    attempted, so the diagnostic records which models failed. When
    `timing` is given, timing["model"] names the model that answered
    (or the last one tried, on failure). `parts`, when given, replaces
    the text prompt as the request contents (the vision path sends an
    inlineData image part + a text part); the fallback chain and the
    shared deadline apply unchanged."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    timeout_s = _gemini_timeout_s() if timeout_s is None \
        else max(5.0, float(timeout_s))
    chain = _model_chain()
    deadline = time.monotonic() + timeout_s
    tried: list[str] = []
    last_exc: Exception | None = None
    for i, model in enumerate(chain):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break  # no time left for another attempt: do not exceed the bound
        tried.append(model)
        if timing is not None:
            timing["model"] = model
        # First attempt gets the full configured timeout (its httpx read
        # timeout is exactly GEMINI_TIMEOUT_S); a retry gets what is left.
        attempt_timeout = timeout_s if i == 0 else remaining
        try:
            text = _gemini_post_once(prompt, model, api_key, generation_config,
                                     timeout_s=attempt_timeout, timing=timing,
                                     parts=parts)
            if len(tried) > 1:
                logger.info("Gemini fallback model %s succeeded after %s failed",
                            model, tried[0])
            return text
        except Exception as exc:  # noqa: BLE001 - retry once, then re-raise
            last_exc = exc
            if model != chain[-1]:
                logger.warning(
                    "Gemini model %s failed (%s: %s); retrying with %s",
                    model, type(exc).__name__, exc, chain[-1])
    if last_exc is None:
        last_exc = TimeoutError(f"Gemini call exceeded {timeout_s:g}s")
    last_exc.gemini_models_tried = tried  # type: ignore[attr-defined]
    raise last_exc


def _call_gemini(message: str, language: str,
                 price_rows: list[dict]) -> str:
    """One Gemini call over REST. Raises on any failure; the caller
    degrades to template."""
    return _gemini_post(_gemini_prompt(message, language, price_rows))


# ---------------------------------------------------------------------------
# Gemini vision: photo disease detection (POST /api/v1/assistant/chat-image)
# ---------------------------------------------------------------------------
def _vision_prompt(message: str, language: str) -> str:
    """Structured disease-analysis prompt for the vision call. The section
    headers stay in Bangla (the farmers' language) either way; the reply
    language follows the request. Dosages are forbidden here too — names
    only, per SYSTEM_INSTRUCTION — and a healthy plant must be reported
    healthy, never given an invented disease."""
    lang_name = "Bangla" if language == "bn" else "English"
    note = f"\n\nFarmer's note: {message.strip()}" if message.strip() else ""
    return (
        f"Reply in {lang_name}. Look at this crop photo and identify any "
        "disease or pest problem. If the plant looks healthy, say so clearly "
        "instead of inventing a disease.\n"
        "Structure your answer exactly like this, using these plain-text "
        "labels and no emojis:\n"
        "রোগের নাম: the disease or pest name (or say the plant looks healthy)\n"
        "কারণ: what caused it\n"
        "সমাধান: how to treat it (local pesticide or fertiliser NAMES only, "
        "never dosages — tell the farmer to ask a local extension officer for dosage)\n"
        "প্রতিরোধ: how to prevent it coming back\n"
        "Use short, clear, practical advice in simple words. Do not use "
        "emojis in your reply. Never invent prices, dates or facts."
        f"{note}"
    )


def analyze_crop_image(image_bytes: bytes, mime_type: str,
                       message: str = "", language: str = "bn") -> str:
    """Analyse a crop photo with Gemini vision over the SAME REST transport
    as chat (_gemini_post: model chain gemini-3.8-flash ->
    gemini-3.5-flash-lite, shared deadline, one fallback retry, daemon-
    thread timeout backstop). The image goes as an inlineData part plus
    the structured prompt text. Raises on any failure (no key, timeout,
    API error); the caller returns a clear error — NEVER a fabricated
    diagnosis. A success clears the stale last-error diagnostic, like
    generate_reply/test_gemini do."""
    import base64

    language = language if language in ("bn", "en") else "bn"
    parts = [
        {"inlineData": {"mime_type": mime_type,
                        "data": base64.b64encode(image_bytes).decode("ascii")}},
        {"text": _vision_prompt(message, language)},
    ]
    text = _gemini_post("", parts=parts)
    LAST_GEMINI_ERROR.clear()  # a success clears the stale failure
    return text


def test_gemini() -> dict:
    """One tiny live Gemini call ("say hi", max 8 output tokens) against
    the key + model THIS process is running with. Returns
    {ok, mode, latency_ms, error, model, connect_ms, ttfb_ms} — never
    the key. A failure is also recorded in LAST_GEMINI_ERROR so
    /assistant/status agrees. The probe waits up to GEMINI_TEST_TIMEOUT_S
    (60s, not the 20s chat bound) so a slow-but-working key reports ok
    with honest latency instead of a timeout; latency_ms is the measured
    wall time either way. model names the model that answered (or the
    last one tried, on failure); connect_ms is a TCP connect probe to
    the API host (None when unreachable) and ttfb_ms is request dispatch
    to response headers (None when no response arrived) — together they
    localise a stall: fast connect + no first byte = the stall is after
    connect, on the network path or at Google."""
    started = time.monotonic()
    if not os.getenv("GEMINI_API_KEY", "").strip():
        return {"ok": False, "mode": "template", "latency_ms": 0,
                "error": "GEMINI_API_KEY is not set",
                "model": None, "connect_ms": None, "ttfb_ms": None}
    timing: dict = {}
    try:
        _gemini_post("say hi", generation_config={"maxOutputTokens": 8},
                     timeout_s=GEMINI_TEST_TIMEOUT_S, timing=timing)
    except Exception as exc:  # noqa: BLE001 - the error IS the result
        _record_gemini_error(exc)
        return {"ok": False, "mode": "template",
                "latency_ms": int((time.monotonic() - started) * 1000),
                "error": f"{type(exc).__name__}: {exc}",
                "model": timing.get("model"),
                "connect_ms": _ms(timing.get("connect_ms")),
                "ttfb_ms": _ms(timing.get("ttfb_ms"))}
    LAST_GEMINI_ERROR.clear()  # a success clears the stale failure
    return {"ok": True, "mode": "gemini",
            "latency_ms": int((time.monotonic() - started) * 1000),
            "error": None,
            "model": timing.get("model"),
            "connect_ms": _ms(timing.get("connect_ms")),
            "ttfb_ms": _ms(timing.get("ttfb_ms"))}


def _stream_model_once(model: str, api_key: str, payload: dict,
                       headers: dict, started: float,
                       read_timeout_s: float) -> Iterator[str]:
    """Yield SSE text chunks from ONE model via :streamGenerateContent.
    Raises on any failure (no key, HTTP error, timeout, empty stream);
    the caller retries with the next model only when nothing was yielded
    yet. `started` is the SHARED stream start, so the
    STREAM_TOTAL_TIMEOUT_S cap spans both attempts; read_timeout_s is
    the per-token read budget for this attempt (capped at the time left
    on the shared cap)."""
    import httpx  # already a core dependency (requirements.txt)

    url = f"{GEMINI_API_BASE}/models/{model}:streamGenerateContent"
    chars = 0
    with httpx.Client(timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S,
                                            read=read_timeout_s,
                                            write=10.0, pool=5.0)) as client:
        with client.stream("POST", url, params={"alt": "sse"},
                           json=payload, headers=headers) as resp:
            if resp.status_code >= 400:
                try:
                    resp.read()
                    detail = (resp.json().get("error") or {}).get("message", "")
                except Exception:
                    detail = ""
                if resp.status_code == 404:
                    raise RuntimeError(
                        f"Gemini model not found: {model} "
                        "(retired or misspelled — check GEMINI_MODEL)")
                raise RuntimeError(
                    f"Gemini API error HTTP {resp.status_code}: "
                    f"{detail or 'no detail'}")
            for line in resp.iter_lines():
                if time.monotonic() - started > STREAM_TOTAL_TIMEOUT_S:
                    raise TimeoutError(
                        f"Gemini stream exceeded {STREAM_TOTAL_TIMEOUT_S}s")
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                text = _extract_chunk_text(json.loads(data))
                if not text:
                    continue
                chars += len(text)
                yield text
    if chars == 0:
        raise RuntimeError("Gemini stream returned no text")


def stream_gemini_reply(message: str, language: str,
                        price_rows: list[dict]) -> Iterator[str]:
    """Yield Gemini reply text as it arrives, via :streamGenerateContent
    (alt=sse). Raises on any failure (no key, HTTP error, timeout, empty
    stream); the caller falls back to template when nothing was yielded
    yet. Logs first-token + total latency at info level; never logs the
    key or the prompt.

    Bounding: each read between tokens is limited by GEMINI_TIMEOUT_S
    (default 20s), and the whole stream by STREAM_TOTAL_TIMEOUT_S. No
    daemon-thread backstop is used here (unlike _gemini_post): a generator
    yields incrementally, so a thread join cannot bound it — the httpx
    read timeout is the bound.

    Fallback chain: if the primary model fails BEFORE the first token
    (HTTP error, timeout, empty stream), the stream restarts ONCE with
    gemini-3.5-flash-lite, sharing the same STREAM_TOTAL_TIMEOUT_S deadline
    (the retry's per-token read timeout is capped at the time left).
    Once a token has been yielded there is no retry: the caller keeps
    the partial reply (mode "gemini") and the failure becomes an error
    event. A failure before any token carries a gemini_models_tried
    attribute naming every model attempted."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    prompt = _gemini_prompt(message, language, price_rows)
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [{"parts": [{"text": prompt}]}],
    }
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    started = time.monotonic()
    first_token_ms: int | None = None
    chars = 0
    chain = _model_chain()
    tried: list[str] = []
    last_exc: Exception | None = None
    for model in chain:
        remaining_total = STREAM_TOTAL_TIMEOUT_S - (time.monotonic() - started)
        if remaining_total <= 0:
            break  # no time left for another attempt: do not exceed the cap
        tried.append(model)
        try:
            for text in _stream_model_once(
                    model, api_key, payload, headers, started,
                    read_timeout_s=min(_gemini_timeout_s(), remaining_total)):
                if first_token_ms is None:
                    first_token_ms = int((time.monotonic() - started) * 1000)
                chars += len(text)
                yield text
            break  # completed with text (an empty stream raises inside)
        except Exception as exc:  # noqa: BLE001 - retry once, then re-raise
            last_exc = exc
            if chars > 0:
                raise  # tokens already went out: no retry, keep the partial
            if model != chain[-1]:
                logger.warning(
                    "Gemini stream model %s failed (%s: %s); retrying with %s",
                    model, type(exc).__name__, exc, chain[-1])
    if chars == 0:
        if last_exc is None:
            last_exc = TimeoutError(
                f"Gemini stream exceeded {STREAM_TOTAL_TIMEOUT_S}s")
        last_exc.gemini_models_tried = tried  # type: ignore[attr-defined]
        raise last_exc
    logger.info("Gemini stream done: first_token_ms=%s total_ms=%d chars=%d",
                first_token_ms, int((time.monotonic() - started) * 1000), chars)


def generate_reply(message: str, language: str = "bn",
                   context_docs: list[dict] | None = None,
                   price_rows: list[dict] | None = None) -> dict:
    """Generate an assistant reply. Never raises for Gemini problems: any
    failure (no key, timeout, API error) falls back to the template path
    and returns mode "template". context_docs feeds ONLY the template
    fallback — the Gemini path answers from its own knowledge."""
    language = language if language in ("bn", "en") else "bn"
    context_docs = context_docs or []
    price_rows = price_rows or []
    if os.getenv("GEMINI_API_KEY", "").strip():
        try:
            reply = _call_gemini(message, language, price_rows)
            LAST_GEMINI_ERROR.clear()  # a success clears the stale failure
            return {"reply": reply, "mode": "gemini"}
        except Exception as exc:
            _record_gemini_error(exc)
    return {"reply": template_reply(message, language, context_docs, price_rows),
            "mode": "template"}
