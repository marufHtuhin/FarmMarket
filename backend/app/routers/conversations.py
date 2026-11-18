"""Farmer-buyer in-app messaging.

One thread per (farmer, buyer, listing, offer) tuple, created-or-found by
POST /conversations. Only the two participants can read or send in a thread
(403 otherwise). Every new message also creates a Notification for the
recipient, following the pattern in routers/offers.py and main.py.

Privacy: this is in-app chat only. Responses expose the other participant's
id, name, role and district — never a phone number or email address.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services.rate_limit import message_limiter

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])

PREVIEW_LEN = 120

_MISSING = object()  # _serialize sentinel: "not precomputed" vs None (no messages)


def _other_user(conv: models.ChatConversation, user) -> models.User:
    return conv.buyer if conv.farmer_id == user.id else conv.farmer


def _unread_count(db: Session, conv_id: int, user_id: int) -> int:
    return (
        db.query(models.ChatMessage)
        .filter_by(conversation_id=conv_id, read_at=None)
        .filter(models.ChatMessage.sender_id != user_id)
        .count()
    )


def _serialize(db: Session, conv: models.ChatConversation, user, unread=_MISSING, last=_MISSING) -> dict:
    """Serialize one conversation. `unread`/`last` are precomputed batch
    values from list_mine (P12 N+1 fix); when _MISSING (single-conversation
    paths like create_or_find) they are queried for this conversation."""
    other = _other_user(conv, user)
    if last is _MISSING:
        last = (
            db.query(models.ChatMessage)
            .filter_by(conversation_id=conv.id)
            .order_by(models.ChatMessage.id.desc())
            .first()
        )
    if unread is _MISSING:
        unread = _unread_count(db, conv.id, user.id)
    return {
        "id": conv.id,
        "farmer_id": conv.farmer_id,
        "buyer_id": conv.buyer_id,
        # No phone/email: in-app chat only.
        "other": {"id": other.id, "name": other.name, "role": other.role,
                  "district": other.district},
        "listing_id": conv.listing_id,
        "listing_name": conv.listing.name if conv.listing else None,
        "offer_id": conv.offer_id,
        "unread_count": unread,
        "last_message": (
            {"body": last.body[:PREVIEW_LEN], "sender_id": last.sender_id,
             "created_at": last.created_at}
            if last else None
        ),
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
    }


def _get_participant_conversation(db: Session, conv_id: int, user) -> models.ChatConversation:
    conv = db.query(models.ChatConversation).filter_by(id=conv_id).first()
    if not conv:
        raise HTTPException(404, "Conversation not found")
    if user.id not in (conv.farmer_id, conv.buyer_id):
        raise HTTPException(403, "Not a participant in this conversation")
    return conv


@router.post("")
def create_or_find(data: schemas.ConversationIn, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    other = db.query(models.User).filter_by(id=data.other_user_id).first()
    if not other:
        raise HTTPException(404, "User not found")
    if other.id == user.id:
        raise HTTPException(400, "Cannot message yourself")
    roles = {user.role, other.role}
    if roles != {"farmer", "buyer"}:
        raise HTTPException(400, "Messaging is only available between a farmer and a buyer")
    farmer_id = user.id if user.role == "farmer" else other.id
    buyer_id = other.id if user.role == "farmer" else user.id

    listing = None
    if data.listing_id is not None:
        listing = db.query(models.Product).filter_by(id=data.listing_id).first()
        if not listing:
            raise HTTPException(404, "Listing not found")
        if listing.farmer_id != farmer_id:
            raise HTTPException(400, "Listing does not belong to this farmer")
    if data.offer_id is not None:
        offer = db.query(models.Offer).filter_by(id=data.offer_id).first()
        if not offer:
            raise HTTPException(404, "Offer not found")
        if offer.farmer_id != farmer_id or offer.buyer_id != buyer_id:
            raise HTTPException(400, "Offer does not belong to these participants")

    q = db.query(models.ChatConversation).filter_by(farmer_id=farmer_id, buyer_id=buyer_id)
    # NULL-safe equality: listing_id/offer_id are nullable, so `== None`
    # would never match; use IS NULL for the unset side.
    q = q.filter(models.ChatConversation.listing_id.is_(None)) if data.listing_id is None \
        else q.filter(models.ChatConversation.listing_id == data.listing_id)
    q = q.filter(models.ChatConversation.offer_id.is_(None)) if data.offer_id is None \
        else q.filter(models.ChatConversation.offer_id == data.offer_id)
    conv = q.first()
    if conv:
        return _serialize(db, conv, user)
    conv = models.ChatConversation(farmer_id=farmer_id, buyer_id=buyer_id,
                                   listing_id=data.listing_id, offer_id=data.offer_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return _serialize(db, conv, user)


@router.get("")
def list_mine(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = (
        db.query(models.ChatConversation)
        .filter((models.ChatConversation.farmer_id == user.id)
                | (models.ChatConversation.buyer_id == user.id))
        .options(selectinload(models.ChatConversation.farmer),
                 selectinload(models.ChatConversation.buyer),
                 selectinload(models.ChatConversation.listing))
        .order_by(models.ChatConversation.updated_at.desc(),
                  models.ChatConversation.id.desc())
        .all()
    )
    # Batch the per-conversation data in 3 fixed queries instead of 2 per
    # conversation (P12 N+1 fix): unread counts, latest message ids, and
    # the latest messages themselves.
    unread: dict[int, int] = {}
    last: dict[int, models.ChatMessage] = {}
    ids = [c.id for c in rows]
    if ids:
        unread = dict(
            db.query(models.ChatMessage.conversation_id, func.count(models.ChatMessage.id))
            .filter(models.ChatMessage.conversation_id.in_(ids),
                    models.ChatMessage.sender_id != user.id,
                    models.ChatMessage.read_at.is_(None))
            .group_by(models.ChatMessage.conversation_id).all())
        last_ids = dict(
            db.query(models.ChatMessage.conversation_id, func.max(models.ChatMessage.id))
            .filter(models.ChatMessage.conversation_id.in_(ids))
            .group_by(models.ChatMessage.conversation_id).all())
        if last_ids:
            for m in db.query(models.ChatMessage).filter(
                    models.ChatMessage.id.in_(last_ids.values())).all():
                last[m.conversation_id] = m
    return [_serialize(db, c, user, unread=unread.get(c.id, 0),
                       last=last.get(c.id)) for c in rows]


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user=Depends(get_current_user)):
    conv_ids = [
        c.id for c in db.query(models.ChatConversation.id)
        .filter((models.ChatConversation.farmer_id == user.id)
                | (models.ChatConversation.buyer_id == user.id)).all()
    ]
    if not conv_ids:
        return {"unread": 0}
    total = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.conversation_id.in_(conv_ids),
                models.ChatMessage.sender_id != user.id,
                models.ChatMessage.read_at.is_(None))
        .count()
    )
    return {"unread": total}


@router.get("/{conv_id}/messages")
def get_messages(conv_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    conv = _get_participant_conversation(db, conv_id, user)
    rows = (
        db.query(models.ChatMessage)
        .filter_by(conversation_id=conv.id)
        .order_by(models.ChatMessage.id.asc())
        .all()
    )
    return [{"id": m.id, "sender_id": m.sender_id, "sender_name": m.sender.name,
             "body": m.body, "created_at": m.created_at, "read_at": m.read_at}
            for m in rows]


@router.post("/{conv_id}/messages")
def send_message(conv_id: int, data: schemas.ChatMessageIn, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    conv = _get_participant_conversation(db, conv_id, user)
    if not message_limiter.allow(f"msg:{user.id}"):
        raise HTTPException(429, "Too many messages — please wait a minute and try again")
    body = data.body.strip()
    if not body:
        raise HTTPException(400, "Message must not be empty")
    msg = models.ChatMessage(conversation_id=conv.id, sender_id=user.id, body=body)
    db.add(msg)
    conv.updated_at = datetime.utcnow()
    recipient_id = conv.buyer_id if conv.farmer_id == user.id else conv.farmer_id
    db.add(models.Notification(user_id=recipient_id, title="New message",
             message=f"{user.name}: {body[:PREVIEW_LEN]}"))
    db.commit()
    db.refresh(msg)
    return {"id": msg.id, "sender_id": msg.sender_id, "sender_name": user.name,
            "body": msg.body, "created_at": msg.created_at, "read_at": msg.read_at}


@router.post("/{conv_id}/read")
def mark_read(conv_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    conv = _get_participant_conversation(db, conv_id, user)
    now = datetime.utcnow()
    count = (
        db.query(models.ChatMessage)
        .filter_by(conversation_id=conv.id, read_at=None)
        .filter(models.ChatMessage.sender_id != user.id)
        .update({"read_at": now})
    )
    db.commit()
    return {"marked_read": count}
