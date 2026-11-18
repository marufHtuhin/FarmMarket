"""Krishi Bondhu assistant (Phase 5) tests: chat + conversations + RAG.

No real Gemini key exists in this environment, so most chat tests exercise
the template fallback; the Gemini path is covered with a mocked httpx
client (fake key + canned 200s), never a live call.
"""
import pytest

from conftest import register
from app import models
from app.services import gemini_assistant as GA
from app.services import rag


@pytest.fixture(autouse=True)
def _no_gemini_key_and_fresh_limiter(monkeypatch):
    # The rate limit is read from the env on every call, so monkeypatching
    # ASSISTANT_RATE_LIMIT_PER_MIN works without re-importing the service.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    GA.reset_limiter()
    GA.LAST_GEMINI_ERROR.clear()
    yield
    GA.reset_limiter()
    GA.LAST_GEMINI_ERROR.clear()


def _chat(client, headers, **kwargs):
    return client.post("/api/v1/assistant/chat", headers=headers, json=kwargs)


def test_chat_template_mode_stores_conversation_and_messages(client, db):
    farmer = register(client, "f@x.t", "farmer")
    r = _chat(client, farmer, message="How do I store tomatoes after harvest?",
              language="en")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "template"
    assert body["sources"], "template reply should cite retrieved notes"
    assert any(s["ref"] == "tomato.md" for s in body["sources"])
    assert "template" in body["reply"].lower()
    assert "tomato" in body["reply"].lower()
    conv = db.query(models.Conversation).filter_by(id=body["conversation_id"]).first()
    assert conv is not None and conv.user_id is not None
    msgs = db.query(models.Message).filter_by(conversation_id=conv.id).all()
    assert len(msgs) == 2
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].mode == "template" and "tomato.md" in msgs[1].sources


def test_chat_includes_stored_price_rows(client, db):
    farmer = register(client, "f@x.t", "farmer")
    db.add(models.PriceRecord(product_name="Tomato", district="Gazipur",
                              market_name="Gazipur Bazar", price_per_unit=42,
                              source="Demo reference data"))
    db.commit()
    r = _chat(client, farmer, message="What is the tomato price?", language="en")
    assert r.status_code == 200, r.text
    assert "42" in r.json()["reply"]
    assert "Demo reference data" in r.json()["reply"]


def test_second_message_reuses_conversation(client, db):
    farmer = register(client, "f@x.t", "farmer")
    cid = _chat(client, farmer, message="Tell me about tomato storage",
                language="en").json()["conversation_id"]
    r = _chat(client, farmer, conversation_id=cid,
              message="And what about rain?", language="en")
    assert r.status_code == 200
    assert r.json()["conversation_id"] == cid
    assert db.query(models.Conversation).count() == 1
    assert db.query(models.Message).filter_by(conversation_id=cid).count() == 4


def test_list_and_get_conversations(client):
    farmer = register(client, "f@x.t", "farmer")
    cid = _chat(client, farmer, message="How do I store onions?",
                language="en").json()["conversation_id"]
    listing = client.get("/api/v1/assistant/conversations", headers=farmer)
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["message_count"] == 2
    detail = client.get(f"/api/v1/assistant/conversations/{cid}", headers=farmer)
    assert detail.status_code == 200
    assert [m["role"] for m in detail.json()["messages"]] == ["user", "assistant"]
    assert detail.json()["messages"][1]["sources"]


def test_other_users_conversation_is_404(client):
    farmer = register(client, "f@x.t", "farmer")
    other = register(client, "f2@x.t", "farmer")
    cid = _chat(client, farmer, message="How do I store onions?",
                language="en").json()["conversation_id"]
    assert client.get(f"/api/v1/assistant/conversations/{cid}",
                      headers=other).status_code == 404
    assert _chat(client, other, conversation_id=cid,
                 message="hello?", language="en").status_code == 404
    assert client.delete(f"/api/v1/assistant/conversations/{cid}",
                         headers=other).status_code == 404
    assert client.get("/api/v1/assistant/conversations",
                      headers=other).json() == []


def test_delete_conversation(client, db):
    farmer = register(client, "f@x.t", "farmer")
    cid = _chat(client, farmer, message="How do I store onions?",
                language="en").json()["conversation_id"]
    r = client.delete(f"/api/v1/assistant/conversations/{cid}", headers=farmer)
    assert r.status_code == 200
    assert client.get(f"/api/v1/assistant/conversations/{cid}",
                      headers=farmer).status_code == 404
    assert db.query(models.Conversation).filter_by(id=cid).first() is None
    assert db.query(models.Message).filter_by(conversation_id=cid).count() == 0


def test_chat_unauthenticated_401(client):
    assert _chat(client, {}, message="hello", language="en").status_code == 401
    assert client.get("/api/v1/assistant/conversations").status_code == 401


def test_chat_validation_errors(client):
    farmer = register(client, "f@x.t", "farmer")
    assert _chat(client, farmer, message="x" * 2001, language="en").status_code == 422
    assert _chat(client, farmer, message="", language="en").status_code == 422
    assert _chat(client, farmer, message="hello", language="xx").status_code == 422
    assert _chat(client, farmer, message="hello",
                 conversation_id=99999, language="en").status_code == 404


def test_rate_limit_via_api(client, monkeypatch):
    # Limit is read from the env on every call: monkeypatch works without re-import.
    monkeypatch.setenv("ASSISTANT_RATE_LIMIT_PER_MIN", "2")
    farmer = register(client, "f@x.t", "farmer")
    assert _chat(client, farmer, message="one", language="en").status_code == 200
    assert _chat(client, farmer, message="two", language="en").status_code == 200
    r = _chat(client, farmer, message="three", language="en")
    assert r.status_code == 429


def test_rate_limiter_unit(monkeypatch):
    monkeypatch.setenv("ASSISTANT_RATE_LIMIT_PER_MIN", "2")
    rl = GA.AssistantRateLimiter()
    assert rl.allow("u1") and rl.allow("u1") and not rl.allow("u1")
    assert rl.allow("u2")  # per-user buckets


def test_rag_retrieve_returns_tomato_doc():
    results = rag.retrieve("how do I harvest and store tomatoes?", top_k=3)
    assert results, "expected at least one retrieved doc"
    assert results[0]["ref"] == "tomato.md"
    assert results[0]["score"] > 0
    assert "tomato" in results[0]["snippet"].lower()
    assert rag.retrieve("zzzqqq no such topic", top_k=3) == []


def test_price_context_matches_product_name(client, db):
    db.add(models.PriceRecord(product_name="Onion", district="Rajshahi",
                              price_per_unit=65, source="Demo reference data"))
    db.commit()
    rows = rag.price_context(db, "what is the onion price today?")
    assert len(rows) == 1
    assert rows[0]["product_name"] == "Onion"
    assert rows[0]["source"] == "Demo reference data"
    assert rows[0]["recorded_at"]
    assert rag.price_context(db, "what is the mango price today?") == []


def test_generate_reply_without_key_is_template():
    out = GA.generate_reply("How do I store tomatoes?", "en",
                            rag.retrieve("tomato storage"), [])
    assert out["mode"] == "template"
    assert "template" in out["reply"].lower()


def _fake_httpx_client(monkeypatch, post_fn):
    """Swap httpx.Client for a fake whose post() runs post_fn (REST path)."""
    import httpx

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, **kwargs):
            return post_fn(url, **kwargs)

    monkeypatch.setattr(httpx, "Client", _FakeClient)


def test_gemini_timeout_falls_back_to_template_quickly(monkeypatch):
    """Regression test (found live 2026-11-16): a hung Gemini call used to
    hang the whole request because ThreadPoolExecutor.__exit__ waits for
    pending work. The timeout must now be real — template mode within a
    few seconds, even if the model call never returns."""
    import time

    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-timeout-test")
    # Patch the helper directly: it floors the timeout at 5s, which would
    # make this test slow for no reason (the floor is covered separately).
    monkeypatch.setattr(GA, "_gemini_timeout_s", lambda: 1.0)

    def _hang(url, **kwargs):
        time.sleep(30)  # far longer than the 1s timeout
        return httpx.Response(200, json={"candidates": []})

    _fake_httpx_client(monkeypatch, _hang)

    started = time.monotonic()
    out = GA.generate_reply("How do I store tomatoes?", "en",
                            rag.retrieve("tomato storage"), [])
    elapsed = time.monotonic() - started
    assert out["mode"] == "template"
    assert "template" in out["reply"].lower()
    assert elapsed < 12, f"timeout did not bound the call (took {elapsed:.1f}s)"
    assert GA.get_last_gemini_error()["type"] == "TimeoutError"


def test_gemini_timeout_env_override_and_floor(monkeypatch):
    monkeypatch.setenv("GEMINI_TIMEOUT_S", "45")
    assert GA._gemini_timeout_s() == 45.0
    monkeypatch.setenv("GEMINI_TIMEOUT_S", "1")
    assert GA._gemini_timeout_s() == 5.0  # floored: a 1s limit is unusable
    monkeypatch.setenv("GEMINI_TIMEOUT_S", "not-a-number")
    assert GA._gemini_timeout_s() == float(GA.GEMINI_TIMEOUT_S)
    monkeypatch.delenv("GEMINI_TIMEOUT_S")
    assert GA._gemini_timeout_s() == float(GA.GEMINI_TIMEOUT_S)


def test_gemini_rest_success_returns_gemini_mode(monkeypatch):
    """The REST path: a 200 with candidates text yields mode gemini, and the
    key travels in the x-goog-api-key header (never in the URL)."""
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-success-test")
    seen: dict = {}

    def _ok(url, **kwargs):
        seen["url"] = url
        seen["headers"] = kwargs.get("headers", {})
        seen["payload"] = kwargs.get("json", {})
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [
                {"text": "Hello from Gemini. "},
                {"text": "Store tomatoes in a cool place."}]}}]})

    _fake_httpx_client(monkeypatch, _ok)
    out = GA.generate_reply("How do I store tomatoes?", "en",
                            rag.retrieve("tomato storage"), [])
    assert out["mode"] == "gemini"
    assert "Hello from Gemini" in out["reply"]
    assert "gemini-3.8-flash" in seen["url"]
    assert "fake-key" not in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == "fake-key-for-success-test"
    assert seen["payload"]["contents"][0]["parts"][0]["text"]
    assert GA.get_last_gemini_error() == {}


def test_gemini_rest_404_falls_back_to_template_and_records_error(monkeypatch):
    """A retired model (404) falls back to template and records the failure
    for the /assistant/status diagnostic."""
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-404-test")

    def _gone(url, **kwargs):
        return httpx.Response(404, json={"error": {"message": "model not found"}})

    _fake_httpx_client(monkeypatch, _gone)
    out = GA.generate_reply("How do I store tomatoes?", "en",
                            rag.retrieve("tomato storage"), [])
    assert out["mode"] == "template"
    err = GA.get_last_gemini_error()
    assert err["type"] == "RuntimeError"
    assert "not found" in err["message"]
    assert err["at"]


# --- Model fallback chain (2026-11-17): primary fails -> retry once with
# gemini-3.5-flash-lite inside the SAME overall bound, then template. Mocked
# only: live Gemini from the user's network stays unverified. ---
def test_gemini_primary_timeout_retries_fallback_model(monkeypatch):
    """Primary model read-times out -> one retry with gemini-3.5-flash-lite
    succeeds -> mode gemini, well inside the overall bound (the retry
    must not double it)."""
    import time

    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-fallback-test")
    monkeypatch.setattr(GA, "_gemini_timeout_s", lambda: 5.0)
    seen_urls: list[str] = []

    def _flaky(url, **kwargs):
        seen_urls.append(url)
        if "gemini-3.5-flash-lite" in url:
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [
                    {"text": "Fallback reply."}]}}]})
        raise httpx.ReadTimeout("mocked: primary read timed out",
                                request=None)

    _fake_httpx_client(monkeypatch, _flaky)
    started = time.monotonic()
    out = GA.generate_reply("How do I store tomatoes?", "en",
                            rag.retrieve("tomato storage"), [])
    elapsed = time.monotonic() - started
    assert out["mode"] == "gemini"
    assert "Fallback reply" in out["reply"]
    assert len(seen_urls) == 2  # primary tried, then exactly one retry
    assert "gemini-3.8-flash" in seen_urls[0]
    assert "gemini-3.5-flash-lite" in seen_urls[1]
    assert elapsed < 5, f"retry exceeded the overall bound ({elapsed:.1f}s)"
    assert GA.get_last_gemini_error() == {}  # success clears the stale failure


def test_gemini_both_models_fail_falls_back_to_template_and_records_models(monkeypatch):
    """Both models fail (e.g. a bad key) -> template fallback, and the
    recorded error names every model tried, for /assistant/status."""
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-both-fail-test")
    seen_urls: list[str] = []

    def _bad(url, **kwargs):
        seen_urls.append(url)
        return httpx.Response(400, json={
            "error": {"message": "API key not valid. Please pass a valid API key."}})

    _fake_httpx_client(monkeypatch, _bad)
    out = GA.generate_reply("How do I store tomatoes?", "en",
                            rag.retrieve("tomato storage"), [])
    assert out["mode"] == "template"
    assert len(seen_urls) == 2  # primary tried, then exactly one retry
    err = GA.get_last_gemini_error()
    assert err["type"] == "RuntimeError"
    assert "API key not valid" in err["message"]
    assert err["models_tried"] == ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
    assert err["model"] == "gemini-3.5-flash-lite"  # last model attempted


def test_gemini_no_duplicate_retry_when_primary_is_fallback(monkeypatch):
    """GEMINI_MODEL=gemini-3.5-flash-lite: the chain is a single model, so a
    failure is NOT retried against the same model."""
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-no-dup-test")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    seen_urls: list[str] = []

    def _bad(url, **kwargs):
        seen_urls.append(url)
        return httpx.Response(400, json={"error": {"message": "boom"}})

    _fake_httpx_client(monkeypatch, _bad)
    out = GA.generate_reply("How do I store tomatoes?", "en",
                            rag.retrieve("tomato storage"), [])
    assert out["mode"] == "template"
    assert len(seen_urls) == 1
    assert GA.get_last_gemini_error()["models_tried"] == ["gemini-3.5-flash-lite"]


def test_system_instruction_answers_from_own_knowledge():
    """Regression (17 Nov 2026): the old instruction said "Answer ONLY from
    the provided context", so Gemini refused real farming questions (e.g.
    rice harvest timing) whenever RAG retrieved nothing. The notes were
    then removed from the Gemini path entirely at the user's request, so
    the instruction must tell Gemini to answer fully from its own
    knowledge — with no mention of notes or context — while still
    forbidding invented prices/dates and pesticide/fertiliser dosages.
    The style now mirrors the user's old Bangla agri-chatbot prompt:
    simple farmer-friendly words, disease answers structured as cause +
    solution + prevention, and local pesticide/fertiliser names — but
    with NO emojis (the user's 17 Nov 2026 rule overrides the old
    chatbot's emoji style)."""
    assert "ONLY from the provided context" not in GA.SYSTEM_INSTRUCTION
    assert "retrieved notes" not in GA.SYSTEM_INSTRUCTION
    assert "provided context" not in GA.SYSTEM_INSTRUCTION
    assert "from your own knowledge" in GA.SYSTEM_INSTRUCTION
    assert "never refuse a farming question" in GA.SYSTEM_INSTRUCTION
    assert "Never invent prices, weather, dates, yields" in GA.SYSTEM_INSTRUCTION
    assert "Do not give pesticide or fertiliser dosages" in GA.SYSTEM_INSTRUCTION
    # Prompt style (17 Nov 2026): disease structure, local names, no emojis.
    assert "cause, solution, and prevention" in GA.SYSTEM_INSTRUCTION
    assert "local pesticide and fertiliser NAMES" in GA.SYSTEM_INSTRUCTION
    assert "Do not use emojis" in GA.SYSTEM_INSTRUCTION
    assert "no jargon" in GA.SYSTEM_INSTRUCTION
    # Greeting (17 Nov 2026): Gemini greeted with "Nomoskar"; the user wants
    # a neutral Hi/Hello instead of any religious greeting.
    assert "use a simple 'Hi' or 'Hello'" in GA.SYSTEM_INSTRUCTION
    assert "never use religious greetings" in GA.SYSTEM_INSTRUCTION.lower()
    # Banglish (17 Nov 2026): match the user's script — Bangla script gets
    # Bangla, English gets English, Banglish (romanized Bangla) gets
    # Banglish. Detected from the message itself; there is no third
    # language option in the chat selector.
    assert "Match the user's script" in GA.SYSTEM_INSTRUCTION
    assert "Banglish (romanized Bangla)" in GA.SYSTEM_INSTRUCTION


def test_gemini_prompt_has_no_notes_section():
    """The Gemini prompt carries no retrieved notes (removed 2026-11-17):
    it is the question plus stored price rows only."""
    prompt = GA._gemini_prompt("When do I harvest rice?", "en", [])
    assert "Retrieved notes" not in prompt
    assert "no notes retrieved" not in prompt
    assert "When do I harvest rice?" in prompt
    assert "Stored reference prices" in prompt


def test_gemini_mode_chat_returns_no_sources(client, monkeypatch):
    """A Gemini-mode reply cites no notes: the answer came from the model,
    so attaching note sources would falsely imply it came from them.
    (Template mode still cites notes — see the template chat test.)"""
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-sources-test")

    def _ok(url, **kwargs):
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [
                {"text": "Harvest rice when most grains are firm and golden."}]}}]})

    _fake_httpx_client(monkeypatch, _ok)
    farmer = register(client, "f@x.t", "farmer")
    r = _chat(client, farmer, message="When do I harvest rice?", language="en")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "gemini"
    assert body["sources"] == []
    assert "firm and golden" in body["reply"]
