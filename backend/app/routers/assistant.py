"""Krishi Bondhu assistant (Phase 5): RAG-grounded chat with Gemini,
with a deterministic template fallback when no Gemini key is configured.

Conversations are private: every endpoint only touches the caller's own
conversations, and another user's conversation id yields 404 (not 403), so
ids cannot be probed. API keys are never accepted or returned here.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..database import SessionLocal, get_db
from ..security import get_current_user, require_role
from ..services import gemini_assistant as GA
from ..services import rag
from ..services import vision as V

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])
admin = require_role("admin")


class ChatIn(BaseModel):
    conversation_id: int | None = None
    message: str = Field(min_length=1, max_length=2000)
    language: Literal["bn", "en"] = "bn"


def _get_own_conversation(db: Session, conv_id: int, user_id: int) -> models.Conversation:
    conv = db.query(models.Conversation).filter_by(id=conv_id, user_id=user_id).first()
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conv


def _parse_sources(raw: str) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except ValueError:
        return []


def _vision_image_payload(data: bytes) -> tuple[bytes, str]:
    """Validate a chat-image upload with the SAME limits /vision/assess
    enforces (V.load_image: max 5 MB, must be a readable image) and
    return (bytes, mime_type) for the Gemini inlineData part. The mime
    type comes from the image's real format (PIL), never the client-
    supplied content type. Formats Gemini cannot take inline (e.g. BMP)
    are re-encoded as JPEG from the validated image."""
    import io

    from PIL import Image

    try:
        img = V.load_image(data)  # raises BadImageError on size/format
    except V.BadImageError as e:
        raise HTTPException(400, str(e))
    fmt = Image.open(io.BytesIO(data)).format
    mime = Image.MIME.get(fmt or "")
    if mime in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        return data, mime
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue(), "image/jpeg"


@router.get("/status")
def assistant_status(user=Depends(admin)):
    """Admin-only Gemini diagnostic: why is the assistant in template mode?

    Reports whether a key is configured, which model is in use, and the last
    recorded Gemini failure (type/message/UTC timestamp, including timeouts,
    plus the models tried when the failure came out of the fallback chain)
    — or null when no failure has been recorded. The API key itself is
    NEVER returned, in whole or in part.
    """
    last_error = GA.get_last_gemini_error()
    return {"key_configured": bool(os.getenv("GEMINI_API_KEY", "").strip()),
            "model": os.getenv("GEMINI_MODEL", GA.DEFAULT_MODEL).strip() or GA.DEFAULT_MODEL,
            "last_gemini_error": last_error or None}


@router.post("/test")
def assistant_test(user=Depends(admin)):
    """Admin-only live Gemini probe: one tiny call ("say hi", max 8 output
    tokens) against the key + model THIS process is actually running with.
    Returns {ok, mode, latency_ms, error, model, connect_ms, ttfb_ms} —
    never the key. model names the model that answered (or the last one
    tried); connect_ms is a TCP connect probe to the API host and ttfb_ms
    is request dispatch to response headers, so a stall can be localised
    (fast connect + no first byte = the stall is after connect). Use it
    right after changing the key: .env is loaded once at backend start,
    so a new key needs a restart before this can pass."""
    return GA.test_gemini()


def _prepare_chat(data: ChatIn, db: Session, user) -> tuple[models.Conversation, str]:
    """Shared /chat + /chat/stream setup: rate limit, validation,
    conversation lookup/creation, and storing the user's message."""
    if not GA.limiter.allow(str(user.id)):
        raise HTTPException(429, "Too many assistant messages; please wait a minute and try again")
    message = data.message.strip()
    if not message:
        raise HTTPException(422, "Message must not be empty")
    if data.conversation_id is not None:
        conv = _get_own_conversation(db, data.conversation_id, user.id)
    else:
        conv = models.Conversation(user_id=user.id, title=message[:40],
                                   language=data.language)
        db.add(conv)
        db.commit()
        db.refresh(conv)
    db.add(models.Message(conversation_id=conv.id, role="user", content=message,
                          sources="", mode=""))
    db.commit()
    return conv, message


@router.post("/chat")
def chat(data: ChatIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    conv, message = _prepare_chat(data, db, user)
    docs = rag.retrieve(message, top_k=3)
    prices = rag.price_context(db, message, limit=5)
    result = GA.generate_reply(message, data.language, docs, prices)
    # Sources are cited only for template replies: Gemini answers from its
    # own knowledge, so attaching note sources to a Gemini reply would
    # falsely imply the answer came from those notes.
    sources = [{"title": d["title"], "ref": d["ref"]} for d in docs] \
        if result["mode"] == "template" else []
    db.add(models.Message(conversation_id=conv.id, role="assistant",
                          content=result["reply"], sources=json.dumps(sources),
                          mode=result["mode"]))
    db.commit()
    return {"conversation_id": conv.id, "reply": result["reply"],
            "sources": sources, "mode": result["mode"]}


@router.post("/chat/stream")
def chat_stream(data: ChatIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """SSE chat: Gemini reply tokens stream as `data: {"text": ...}` events,
    then a final `event: done` with {mode, conversation_id, sources}.
    The template fallback is sent as one instant event (it needs no
    streaming). If Gemini fails before the first token, the stream falls
    back to the template reply, labelled mode "template". A mid-stream
    failure sends an `event: error` and keeps the partial reply (mode
    "gemini"). Latency (first-token + total ms) and mode are logged at
    info level; the prompt and the key are never logged."""
    conv, message = _prepare_chat(data, db, user)
    conv_id = conv.id  # primitives only: the db session closes before streaming
    docs = rag.retrieve(message, top_k=3)
    prices = rag.price_context(db, message, limit=5)
    # Template sources: attached only when the final mode is template (see
    # _finish/done below). Gemini answers from its own knowledge, so a
    # Gemini reply carries no note sources.
    template_sources = [{"title": d["title"], "ref": d["ref"]} for d in docs]
    language = data.language
    # End the read transaction from price_context: the stream generator
    # saves the reply on its own session, and SQLite (rollback-journal
    # mode) refuses a writer while another connection holds a read lock.
    db.commit()
    started = time.monotonic()

    def event_stream():
        first_token_ms: int | None = None
        chunks: list[str] = []
        mode = "gemini" if os.getenv("GEMINI_API_KEY", "").strip() else "template"

        def _finish() -> None:
            """Persist the assistant reply + log latency. Runs once, even
            if the client disconnects mid-stream. Never logs the prompt."""
            try:
                session = SessionLocal()
                try:
                    session.add(models.Message(
                        conversation_id=conv_id, role="assistant",
                        content="".join(chunks),
                        sources=json.dumps(template_sources
                                           if mode == "template" else []),
                        mode=mode))
                    session.commit()
                finally:
                    session.close()
            except Exception as exc:  # noqa: BLE001 - reply was delivered; log it
                logger.warning("assistant stream: could not save reply (%s)", exc)
            logger.info("assistant stream done: mode=%s first_token_ms=%s total_ms=%d",
                        mode, first_token_ms, int((time.monotonic() - started) * 1000))

        try:
            if mode == "template":
                text = GA.template_reply(message, language, docs, prices)
                chunks.append(text)
                yield f"data: {json.dumps({'text': text})}\n\n"
            else:
                try:
                    for token in GA.stream_gemini_reply(message, language, prices):
                        if first_token_ms is None:
                            first_token_ms = int((time.monotonic() - started) * 1000)
                        chunks.append(token)
                        yield f"data: {json.dumps({'text': token})}\n\n"
                except Exception as exc:  # noqa: BLE001 - fallback/error event below
                    if not chunks:
                        # Nothing sent yet: fall back to template, labelled.
                        GA._record_gemini_error(exc)
                        mode = "template"
                        text = GA.template_reply(message, language, docs, prices)
                        chunks.append(text)
                        yield f"data: {json.dumps({'text': text})}\n\n"
                    else:
                        yield (f"event: error\ndata: "
                               f"{json.dumps({'error': str(exc)})}\n\n")
        finally:
            _finish()  # no yields inside: safe even on client disconnect
        done_payload = json.dumps({"mode": mode, "conversation_id": conv_id,
                                   "sources": template_sources
                                   if mode == "template" else []})
        yield f"event: done\ndata: {done_payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.post("/chat-image")
def chat_image(image: UploadFile = File(...), message: str = Form(""),
               language: Literal["bn", "en"] = Form("bn"),
               conversation_id: int | None = Form(None),
               db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Photo disease detection: the farmer uploads a crop photo and Gemini
    vision returns a structured analysis (রোগের নাম / কারণ / সমাধান /
    প্রতিরোধ, plain-text labels) in the requested language. The photo + reply are saved to
    the conversation like a text chat. Unlike /chat there is NO template
    fallback — a diagnosis must come from the model, never be fabricated:
    no key -> 503, Gemini failure -> 502 (recorded in the /assistant/status
    diagnostic for admins). Upload limits are the same as /vision/assess
    (max 5 MB, must be a readable image); anything else is a 400."""
    # Validate the upload BEFORE creating a conversation or spending a
    # rate-limit hit: a rejected file must not leave an empty conversation.
    raw = image.file.read(V.MAX_IMAGE_BYTES + 1)
    data, mime_type = _vision_image_payload(raw)
    if not os.getenv("GEMINI_API_KEY", "").strip():
        raise HTTPException(
            503, "Photo disease detection needs a Gemini API key "
                 "(GEMINI_API_KEY is not configured on the server)")
    note = message.strip()
    display = note or ({"bn": "[ফসলের ছবি]", "en": "[Crop photo]"}[language])
    conv, _ = _prepare_chat(
        ChatIn(conversation_id=conversation_id, message=display,
               language=language), db, user)
    try:
        reply = GA.analyze_crop_image(data, mime_type, note, language)
    except Exception as exc:  # noqa: BLE001 - never fabricate a diagnosis
        GA._record_gemini_error(exc)
        raise HTTPException(
            502, "Gemini could not analyse the photo; please try again")
    db.add(models.Message(conversation_id=conv.id, role="assistant",
                          content=reply, sources=json.dumps([]),
                          mode="gemini"))
    db.commit()
    return {"reply": reply, "mode": "gemini", "conversation_id": conv.id,
            "sources": []}


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user=Depends(get_current_user)):
    counts = dict(db.query(models.Message.conversation_id, func.count(models.Message.id))
                  .group_by(models.Message.conversation_id).all())
    rows = (db.query(models.Conversation).filter_by(user_id=user.id)
            .order_by(models.Conversation.created_at.desc(),
                      models.Conversation.id.desc()).all())
    return [{"id": c.id, "title": c.title, "language": c.language,
             "created_at": c.created_at, "message_count": counts.get(c.id, 0)}
            for c in rows]


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: int, db: Session = Depends(get_db),
                     user=Depends(get_current_user)):
    conv = _get_own_conversation(db, conv_id, user.id)
    msgs = (db.query(models.Message).filter_by(conversation_id=conv.id)
            .order_by(models.Message.created_at, models.Message.id).all())
    return {"conversation": {"id": conv.id, "title": conv.title,
                             "language": conv.language, "created_at": conv.created_at},
            "messages": [{"role": m.role, "content": m.content,
                          "sources": _parse_sources(m.sources), "mode": m.mode,
                          "created_at": m.created_at} for m in msgs]}


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(get_db),
                        user=Depends(get_current_user)):
    conv = _get_own_conversation(db, conv_id, user.id)
    db.delete(conv)  # messages cascade via the relationship
    db.commit()
    return {"message": "Conversation deleted", "id": conv_id}
