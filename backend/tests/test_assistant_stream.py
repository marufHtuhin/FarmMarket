"""Gemini diagnosis hardening + streaming (Workstream A).

- POST /api/v1/assistant/test: admin-only live probe (one tiny call).
- POST /api/v1/assistant/chat/stream: SSE streaming chat with template
  fallback before the first token.
- stream_gemini_reply(): mocked-httpx unit tests of the SSE parsing.

No real Gemini key exists here: every live call is faked by swapping
httpx.Client, the same pattern as test_assistant.py.
"""
import json

import httpx
import pytest

from conftest import register
from app import models
from app.security import create_access_token, hash_password
from app.services import gemini_assistant as GA


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    GA.reset_limiter()
    GA.LAST_GEMINI_ERROR.clear()
    yield
    GA.reset_limiter()
    GA.LAST_GEMINI_ERROR.clear()


def _admin_headers(db):
    """Admin users cannot self-register; create one directly in the DB."""
    u = models.User(email="admin@x.t", name="Admin", role="admin",
                    district="Dhaka", password_hash=hash_password("Passw0rd!"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"Authorization": "Bearer " + create_access_token(u.id)}


class _FakeStreamResp:
    """Stand-in for the httpx response returned by client.stream()."""

    def __init__(self, status_code=200, lines=(), body=None):
        self.status_code = status_code
        self._lines = list(lines)
        self._body = body if body is not None else {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_lines(self):
        yield from self._lines

    def read(self):
        return b""

    def json(self):
        return self._body


def _fake_httpx(monkeypatch, post_fn=None, stream_fn=None, client_seen=None):
    """Swap httpx.Client for a fake supporting post() and stream().
    client_seen (a dict) records the constructor kwargs of the last client
    created — used to assert which timeout a call used."""

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            if client_seen is not None:
                client_seen.clear()
                client_seen.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, **kwargs):
            assert post_fn is not None, "test did not fake post()"
            return post_fn(url, **kwargs)

        def stream(self, method, url, **kwargs):
            assert stream_fn is not None, "test did not fake stream()"
            return stream_fn(method, url, **kwargs)

    monkeypatch.setattr(httpx, "Client", _FakeClient)


def _sse_line(text):
    return "data: " + json.dumps(
        {"candidates": [{"content": {"parts": [{"text": text}]}}]})


def _sse_events(body: str):
    """Parse an SSE body into [(event_type, parsed_json_or_None)]."""
    events = []
    for block in body.strip().split("\n\n"):
        etype, data = "message", ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                etype = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        events.append((etype, json.loads(data) if data else None))
    return events


def _read_stream(client, headers, payload):
    with client.stream("POST", "/api/v1/assistant/chat/stream",
                       headers=headers, json=payload) as r:
        assert r.status_code == 200, f"stream HTTP {r.status_code}"
        body = "".join(r.iter_text())
    return body


# ---------------------------------------------------------------------------
# stream_gemini_reply() unit tests (mocked httpx)
# ---------------------------------------------------------------------------
def test_stream_yields_text_chunks_in_order(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    seen: dict = {}

    def _stream(method, url, **kwargs):
        seen["method"] = method
        seen["url"] = url
        seen["params"] = kwargs.get("params")
        seen["headers"] = kwargs.get("headers", {})
        return _FakeStreamResp(lines=[_sse_line("Hello "), _sse_line("world")])

    _fake_httpx(monkeypatch, stream_fn=_stream)
    chunks = list(GA.stream_gemini_reply("hi", "en", []))
    assert chunks == ["Hello ", "world"]
    assert seen["method"] == "POST"
    assert ":streamGenerateContent" in seen["url"]
    assert seen["params"] == {"alt": "sse"}
    assert seen["headers"]["x-goog-api-key"] == "fake-key"
    assert "fake-key" not in seen["url"]


def test_stream_skips_comments_done_and_empty_chunks(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _stream(method, url, **kwargs):
        return _FakeStreamResp(lines=[
            "", ": ping", _sse_line("a"),
            "data: " + json.dumps({"candidates": []}),  # empty chunk: skipped
            "data: [DONE]", _sse_line("b"),
        ])

    _fake_httpx(monkeypatch, stream_fn=_stream)
    assert list(GA.stream_gemini_reply("hi", "en", [])) == ["a", "b"]


def test_stream_http_error_raises_with_detail(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _stream(method, url, **kwargs):
        return _FakeStreamResp(
            status_code=400,
            body={"error": {"message": "API key not valid. Please pass a valid API key."}})

    _fake_httpx(monkeypatch, stream_fn=_stream)
    with pytest.raises(RuntimeError, match="API key not valid"):
        list(GA.stream_gemini_reply("hi", "en", []))


def test_stream_404_raises_model_not_found(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _stream(method, url, **kwargs):
        return _FakeStreamResp(status_code=404,
                               body={"error": {"message": "model not found"}})

    _fake_httpx(monkeypatch, stream_fn=_stream)
    with pytest.raises(RuntimeError, match="model not found"):
        list(GA.stream_gemini_reply("hi", "en", []))


def test_stream_empty_raises(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _stream(method, url, **kwargs):
        return _FakeStreamResp(lines=["data: [DONE]"])

    _fake_httpx(monkeypatch, stream_fn=_stream)
    with pytest.raises(RuntimeError, match="no text"):
        list(GA.stream_gemini_reply("hi", "en", []))


def test_stream_primary_failure_before_first_token_retries_fallback(monkeypatch):
    """Fallback chain for streams: the primary model 400s before any
    token, so the stream restarts once with gemini-3.5-flash-lite and the
    caller sees the fallback's tokens."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    seen_urls: list[str] = []

    def _stream(method, url, **kwargs):
        seen_urls.append(url)
        if "gemini-3.5-flash-lite" in url:
            return _FakeStreamResp(lines=[_sse_line("Hello "), _sse_line("fallback")])
        return _FakeStreamResp(
            status_code=400, body={"error": {"message": "primary boom"}})

    _fake_httpx(monkeypatch, stream_fn=_stream)
    assert list(GA.stream_gemini_reply("hi", "en", [])) == ["Hello ", "fallback"]
    assert len(seen_urls) == 2
    assert "gemini-3.8-flash" in seen_urls[0]
    assert "gemini-3.5-flash-lite" in seen_urls[1]


def test_stream_both_models_fail_before_first_token_raises_with_models_tried(monkeypatch):
    """Both models fail before any token: the raise carries
    gemini_models_tried, so the router's fallback records which models
    failed for /assistant/status."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _stream(method, url, **kwargs):
        return _FakeStreamResp(
            status_code=400, body={"error": {"message": "API key not valid."}})

    _fake_httpx(monkeypatch, stream_fn=_stream)
    with pytest.raises(RuntimeError, match="API key not valid") as excinfo:
        list(GA.stream_gemini_reply("hi", "en", []))
    assert excinfo.value.gemini_models_tried == ["gemini-3.8-flash",
                                                 "gemini-3.5-flash-lite"]


def test_stream_no_key_raises(monkeypatch):
    def _stream(method, url, **kwargs):
        raise AssertionError("must not reach the network without a key")

    _fake_httpx(monkeypatch, stream_fn=_stream)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not set"):
        list(GA.stream_gemini_reply("hi", "en", []))


# ---------------------------------------------------------------------------
# POST /api/v1/assistant/test
# ---------------------------------------------------------------------------
def test_test_endpoint_admin_success(monkeypatch, client, db):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    # The probe's TCP connect measurement is mocked: it must not depend
    # on live network in tests (the real measurement is a socket connect
    # to generativelanguage.googleapis.com).
    monkeypatch.setattr(GA, "_measure_connect_ms", lambda *a, **k: 12.4)
    seen: dict = {}
    client_seen: dict = {}

    def _ok(url, **kwargs):
        seen["url"] = url
        seen["payload"] = kwargs.get("json", {})
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "hi"}]}}]})

    _fake_httpx(monkeypatch, post_fn=_ok, client_seen=client_seen)
    r = client.post("/api/v1/assistant/test", headers=_admin_headers(db), json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"ok": True, "mode": "gemini",
                    "latency_ms": body["latency_ms"], "error": None,
                    "model": "gemini-3.8-flash",
                    "connect_ms": 12, "ttfb_ms": body["ttfb_ms"]}
    assert isinstance(body["latency_ms"], int) and body["latency_ms"] >= 0
    # This fake never invokes the httpx event hooks, so no first-byte time
    # was measured: ttfb_ms is honestly None (see
    # test_test_endpoint_reports_per_stage_timing for the hook path).
    assert body["ttfb_ms"] is None
    # The probe is tiny: prompt "say hi", max 8 output tokens.
    assert "say hi" in seen["payload"]["contents"][0]["parts"][0]["text"]
    assert seen["payload"]["generationConfig"] == {"maxOutputTokens": 8}
    # ...but it waits longer than chat (60s, not 20s) so a slow-but-working
    # key reports ok with honest latency instead of a timeout.
    assert client_seen["timeout"].read == float(GA.GEMINI_TEST_TIMEOUT_S) == 60.0
    assert client_seen["timeout"].connect == float(GA.CONNECT_TIMEOUT_S) == 5.0
    # The key itself must never appear in the response.
    assert "fake-key-for-test" not in r.text


def test_test_endpoint_reports_per_stage_timing(monkeypatch, client, db):
    """The probe reports connect_ms (TCP connect probe) and ttfb_ms
    (request dispatch -> response headers via httpx event hooks), so the
    next user-side test pinpoints where a stalled call stops."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-timing-test")
    monkeypatch.setattr(GA, "_measure_connect_ms", lambda *a, **k: 12.4)

    class _HookClient:
        """Fake httpx.Client that invokes the event hooks around post()."""

        def __init__(self, *args, **kwargs):
            self._hooks = kwargs.get("event_hooks") or {}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, **kwargs):
            req = httpx.Request("POST", url)
            for hook in self._hooks.get("request", []):
                hook(req)
            resp = httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{"text": "hi"}]}}]},
                request=req)
            for hook in self._hooks.get("response", []):
                hook(resp)
            return resp

    monkeypatch.setattr(httpx, "Client", _HookClient)
    r = client.post("/api/v1/assistant/test", headers=_admin_headers(db), json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["model"] == "gemini-3.8-flash"
    assert body["connect_ms"] == 12  # mocked probe value, rounded to whole ms
    assert isinstance(body["ttfb_ms"], int) and body["ttfb_ms"] >= 0


def test_test_endpoint_admin_failure_shape_and_status_agrees(monkeypatch, client, db):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-bad")
    monkeypatch.setattr(GA, "_measure_connect_ms", lambda *a, **k: 15.0)

    def _bad(url, **kwargs):
        return httpx.Response(400, json={
            "error": {"message": "API key not valid. Please pass a valid API key."}})

    _fake_httpx(monkeypatch, post_fn=_bad)
    headers = _admin_headers(db)
    r = client.post("/api/v1/assistant/test", headers=headers, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["mode"] == "template"
    assert isinstance(body["latency_ms"], int) and body["latency_ms"] >= 0
    assert "API key not valid" in body["error"]
    assert "fake-key-bad" not in r.text
    # Both models were tried (fallback chain); the probe reports the last
    # one attempted, and the connect probe value is still reported.
    assert body["model"] == "gemini-3.5-flash-lite"
    assert body["connect_ms"] == 15
    assert body["ttfb_ms"] is None  # this fake never invokes the hooks
    # The failure is recorded, so /status shows the same error.
    status = client.get("/api/v1/assistant/status", headers=headers).json()
    assert "API key not valid" in status["last_gemini_error"]["message"]
    assert status["last_gemini_error"]["models_tried"] == [
        "gemini-3.8-flash", "gemini-3.5-flash-lite"]


def test_test_endpoint_no_key(client, db):
    r = client.post("/api/v1/assistant/test", headers=_admin_headers(db), json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["mode"] == "template"
    assert "GEMINI_API_KEY is not set" in body["error"]


def test_test_endpoint_non_admin_403(client):
    farmer = register(client, "f@x.t", "farmer")
    assert client.post("/api/v1/assistant/test", headers=farmer, json={}).status_code == 403


def test_test_endpoint_unauthenticated_401(client):
    assert client.post("/api/v1/assistant/test", json={}).status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/assistant/chat/stream
# ---------------------------------------------------------------------------
def test_stream_template_mode_no_key(client, db):
    farmer = register(client, "f@x.t", "farmer")
    body = _read_stream(client, farmer,
                        {"message": "How do I store tomatoes?", "language": "en"})
    events = _sse_events(body)
    assert events[0][0] == "message"
    assert "template" in events[0][1]["text"].lower()
    assert "tomato" in events[0][1]["text"].lower()
    done = events[-1]
    assert done[0] == "done"
    assert done[1]["mode"] == "template"
    assert done[1]["conversation_id"]
    assert done[1]["sources"]
    # The conversation + both messages were persisted.
    db.rollback()
    msgs = db.query(models.Message).filter_by(
        conversation_id=done[1]["conversation_id"]).order_by(models.Message.id).all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].mode == "template"
    assert "tomato" in msgs[1].content.lower()


def test_stream_gemini_mode(monkeypatch, client, db):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _stream(method, url, **kwargs):
        return _FakeStreamResp(lines=[_sse_line("Hello "), _sse_line("farmer")])

    _fake_httpx(monkeypatch, stream_fn=_stream)
    farmer = register(client, "f@x.t", "farmer")
    body = _read_stream(client, farmer,
                        {"message": "How do I store tomatoes?", "language": "en"})
    events = _sse_events(body)
    assert [e[1]["text"] for e in events if e[0] == "message"] == ["Hello ", "farmer"]
    done = events[-1]
    assert done[0] == "done"
    assert done[1]["mode"] == "gemini"
    db.rollback()
    msgs = db.query(models.Message).filter_by(
        conversation_id=done[1]["conversation_id"]).order_by(models.Message.id).all()
    assert len(msgs) == 2
    assert msgs[1].mode == "gemini"
    assert msgs[1].content == "Hello farmer"


def test_stream_gemini_failure_before_first_token_falls_back_to_template(monkeypatch, client, db):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _stream(method, url, **kwargs):
        return _FakeStreamResp(
            status_code=400,
            body={"error": {"message": "API key not valid."}})

    _fake_httpx(monkeypatch, stream_fn=_stream)
    farmer = register(client, "f@x.t", "farmer")
    body = _read_stream(client, farmer,
                        {"message": "How do I store tomatoes?", "language": "en"})
    events = _sse_events(body)
    assert events[0][0] == "message"
    assert "template" in events[0][1]["text"].lower()
    done = events[-1]
    assert done[0] == "done"
    assert done[1]["mode"] == "template"
    # The failure is recorded for /assistant/status.
    assert "API key not valid" in GA.get_last_gemini_error()["message"]


def test_stream_mid_stream_failure_sends_error_event_keeps_partial(monkeypatch, client, db):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _stream(method, url, **kwargs):
        class _BreakingResp(_FakeStreamResp):
            def iter_lines(self):
                yield _sse_line("partial ")
                raise httpx.ConnectError("connection reset", request=None)

        return _BreakingResp()

    _fake_httpx(monkeypatch, stream_fn=_stream)
    farmer = register(client, "f@x.t", "farmer")
    body = _read_stream(client, farmer,
                        {"message": "How do I store tomatoes?", "language": "en"})
    events = _sse_events(body)
    assert events[0] == ("message", {"text": "partial "})
    assert events[1][0] == "error"
    assert events[-1][0] == "done"
    assert events[-1][1]["mode"] == "gemini"  # partial reply stays labelled gemini
    db.rollback()
    msgs = db.query(models.Message).filter_by(
        conversation_id=events[-1][1]["conversation_id"]).order_by(models.Message.id).all()
    assert msgs[1].content == "partial "
    assert msgs[1].mode == "gemini"


def test_stream_unauthenticated_401(client):
    r = client.post("/api/v1/assistant/chat/stream",
                    json={"message": "hi", "language": "en"})
    assert r.status_code == 401


def test_stream_validation_422(client):
    farmer = register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/assistant/chat/stream", headers=farmer,
                    json={"message": "", "language": "en"})
    assert r.status_code == 422
    r = client.post("/api/v1/assistant/chat/stream", headers=farmer,
                    json={"message": "hi", "language": "en", "conversation_id": 99999})
    assert r.status_code == 404


def test_stream_shares_rate_limit_with_chat(client, monkeypatch):
    monkeypatch.setenv("ASSISTANT_RATE_LIMIT_PER_MIN", "1")
    farmer = register(client, "f@x.t", "farmer")
    r = client.post("/api/v1/assistant/chat", headers=farmer,
                    json={"message": "one", "language": "en"})
    assert r.status_code == 200
    r = client.post("/api/v1/assistant/chat/stream", headers=farmer,
                    json={"message": "two", "language": "en"})
    assert r.status_code == 429
