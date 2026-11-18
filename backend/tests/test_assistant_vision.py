"""Krishi Bondhu photo disease detection (POST /api/v1/assistant/chat-image).

Gemini vision over the existing REST transport, mocked with a fake httpx
client (fake key + canned responses) — never a live call. Unlike text
chat there is NO template fallback here: a diagnosis must come from the
model, so no key -> 503 and a Gemini failure -> 502, never a fabricated
diagnosis.
"""
import io

import pytest

from conftest import register
from app import models
from app.services import gemini_assistant as GA
from app.services.vision import MAX_IMAGE_BYTES

ANALYSIS = ("রোগের নাম: পাতার দাগ রোগ\n"
            "কারণ: ছত্রাকের সংক্রমণ\n"
            "সমাধান: কপার অক্সিক্লোরাইড স্প্রে করুন\n"
            "প্রতিরোধ: আক্রান্ত পাতা সরিয়ে ফেলুন")


@pytest.fixture(autouse=True)
def _no_gemini_key_and_fresh_limiter(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    GA.reset_limiter()
    GA.LAST_GEMINI_ERROR.clear()
    yield
    GA.reset_limiter()
    GA.LAST_GEMINI_ERROR.clear()


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


def _image_bytes(fmt="PNG"):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color="green").save(buf, format=fmt)
    return buf.getvalue()


def _chat_image(client, headers, image_bytes, filename="leaf.png",
                content_type="image/png", **form):
    return client.post(
        "/api/v1/assistant/chat-image", headers=headers,
        files={"image": (filename, image_bytes, content_type)}, data=form)


def _ok_response(monkeypatch, seen=None):
    """Mock a successful Gemini vision reply; optionally capture payloads."""
    import httpx

    def _ok(url, **kwargs):
        if seen is not None:
            seen.append(kwargs.get("json") or {})
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": ANALYSIS}]}}]})

    _fake_httpx_client(monkeypatch, _ok)


# ---------------------------------------------------------------------------
# Prompt + helper
# ---------------------------------------------------------------------------
def test_vision_prompt_has_structured_sections():
    prompt = GA._vision_prompt("leaves have brown spots", "en")
    for section in ("রোগের নাম:", "কারণ:", "সমাধান:", "প্রতিরোধ:"):
        assert section in prompt
    assert "Reply in English" in prompt
    assert "never dosages" in prompt
    assert "leaves have brown spots" in prompt
    assert "Reply in Bangla" in GA._vision_prompt("", "bn")
    # No emojis anywhere in the assistant's replies (user rule, 17 Nov 2026):
    # the prompt uses plain-text labels and tells the model not to use emojis.
    assert "Do not use emojis" in prompt
    for emoji in ("🔍", "🦠", "💊", "🛡️"):
        assert emoji not in prompt


def test_analyze_crop_image_sends_inline_data(monkeypatch):
    """The helper sends the image as an inlineData part (base64 + mime)
    through the shared _gemini_post transport, not a new transport."""
    import base64

    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-vision-test")
    seen = []
    _ok_response(monkeypatch, seen)
    img = _image_bytes()
    assert GA.analyze_crop_image(img, "image/png", "spots?", "en") == ANALYSIS
    assert len(seen) == 1
    parts = seen[0]["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mime_type"] == "image/png"
    assert parts[0]["inlineData"]["data"] == base64.b64encode(img).decode("ascii")
    assert "রোগের নাম:" in parts[1]["text"]
    # The system instruction rides along, as on the text path.
    assert "Krishi Bondhu" in seen[0]["system_instruction"]["parts"][0]["text"]


def test_analyze_crop_image_retries_with_fallback_model(monkeypatch):
    """A primary-model failure retries ONCE with the fallback model,
    like the text path (shared _gemini_post chain)."""
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-vision-test")

    def _flaky(url, **kwargs):
        if "gemini-3.8-flash" in url:
            return httpx.Response(503, json={
                "error": {"message": "model overloaded"}})
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": ANALYSIS}]}}]})

    _fake_httpx_client(monkeypatch, _flaky)
    assert GA.analyze_crop_image(_image_bytes(), "image/png") == ANALYSIS


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
def test_chat_image_success_saves_conversation(client, db, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-vision-test")
    seen = []
    _ok_response(monkeypatch, seen)
    farmer = register(client, "f@x.t", "farmer")
    r = _chat_image(client, farmer, _image_bytes(),
                    message="leaves have brown spots", language="en")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "gemini"
    assert body["reply"] == ANALYSIS
    assert body["sources"] == []
    assert isinstance(body["conversation_id"], int)
    msgs = db.query(models.Message).filter_by(
        conversation_id=body["conversation_id"]).order_by(models.Message.id).all()
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "leaves have brown spots"
    assert msgs[1].content == ANALYSIS and msgs[1].mode == "gemini"
    # The image really went to Gemini as an inlineData part.
    parts = seen[0]["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mime_type"] == "image/png"
    assert "রোগের নাম:" in parts[1]["text"]


def test_chat_image_without_message_saves_photo_placeholder(client, db, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-vision-test")
    _ok_response(monkeypatch)
    farmer = register(client, "f@x.t", "farmer")
    r = _chat_image(client, farmer, _image_bytes(), language="bn")
    assert r.status_code == 200, r.text
    msgs = db.query(models.Message).filter_by(
        conversation_id=r.json()["conversation_id"]).all()
    assert msgs[0].content == "[ফসলের ছবি]"


def test_chat_image_reuses_conversation(client, db, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-vision-test")
    _ok_response(monkeypatch)
    farmer = register(client, "f@x.t", "farmer")
    cid = client.post("/api/v1/assistant/chat", headers=farmer,
                      json={"message": "Tell me about tomato storage",
                            "language": "en"}).json()["conversation_id"]
    r = _chat_image(client, farmer, _image_bytes(), conversation_id=str(cid),
                    message="and this leaf?", language="en")
    assert r.status_code == 200, r.text
    assert r.json()["conversation_id"] == cid
    assert db.query(models.Conversation).count() == 1
    assert db.query(models.Message).filter_by(conversation_id=cid).count() == 4


def test_chat_image_no_key_is_503_and_creates_nothing(client, db):
    farmer = register(client, "f@x.t", "farmer")
    r = _chat_image(client, farmer, _image_bytes(), language="en")
    assert r.status_code == 503, r.text
    assert "Gemini" in r.json()["detail"]
    assert db.query(models.Conversation).count() == 0


def test_chat_image_gemini_failure_is_502_never_fabricated(client, db, monkeypatch):
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-vision-test")

    def _fail(url, **kwargs):
        return httpx.Response(500, json={"error": {"message": "boom"}})

    _fake_httpx_client(monkeypatch, _fail)
    farmer = register(client, "f@x.t", "farmer")
    r = _chat_image(client, farmer, _image_bytes(), language="en")
    assert r.status_code == 502, r.text
    # No assistant message was invented; the failure is recorded for the
    # admin /assistant/status diagnostic instead.
    assert db.query(models.Message).filter_by(role="assistant").count() == 0
    assert GA.get_last_gemini_error(), "failure must be recorded"
    assert GA.get_last_gemini_error()["models_tried"] == [
        "gemini-3.8-flash", "gemini-3.5-flash-lite"]


def test_chat_image_rejects_non_image(client, db):
    farmer = register(client, "f@x.t", "farmer")
    r = _chat_image(client, farmer, b"this is not an image at all",
                    filename="notes.txt", content_type="text/plain")
    assert r.status_code == 400, r.text
    assert "readable image" in r.json()["detail"]
    assert db.query(models.Conversation).count() == 0


def test_chat_image_rejects_too_large(client, db):
    farmer = register(client, "f@x.t", "farmer")
    r = _chat_image(client, farmer, b"\x00" * (MAX_IMAGE_BYTES + 1),
                    filename="huge.png")
    assert r.status_code == 400, r.text
    assert "too large" in r.json()["detail"].lower()
    assert db.query(models.Conversation).count() == 0


def test_chat_image_bmp_is_reencoded_as_jpeg(client, monkeypatch):
    """Formats Gemini cannot take inline (BMP) are re-encoded as JPEG
    from the validated image instead of being rejected."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-vision-test")
    seen = []
    _ok_response(monkeypatch, seen)
    farmer = register(client, "f@x.t", "farmer")
    r = _chat_image(client, farmer, _image_bytes("BMP"), filename="leaf.bmp",
                    content_type="image/bmp", language="en")
    assert r.status_code == 200, r.text
    assert seen[0]["contents"][0]["parts"][0]["inlineData"]["mime_type"] == "image/jpeg"


def test_chat_image_unauthenticated_401(client):
    assert _chat_image(client, {}, _image_bytes()).status_code == 401


def test_chat_image_other_users_conversation_is_404(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-vision-test")
    _ok_response(monkeypatch)
    farmer = register(client, "f@x.t", "farmer")
    other = register(client, "f2@x.t", "farmer")
    cid = client.post("/api/v1/assistant/chat", headers=farmer,
                      json={"message": "Tell me about tomato storage",
                            "language": "en"}).json()["conversation_id"]
    r = _chat_image(client, other, _image_bytes(), conversation_id=str(cid),
                    language="en")
    assert r.status_code == 404, r.text
