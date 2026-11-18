"""Farmer-buyer in-app messaging: create-or-find, permissions, unread counts,
notifications, rate limiting. Privacy: no phone number or email is ever
exposed through the messaging API."""
from decimal import Decimal

import pytest

from conftest import register
from app import models
from app.services.rate_limit import reset_message_limiter


@pytest.fixture(autouse=True)
def _fresh_message_limiter():
    reset_message_limiter()
    yield
    reset_message_limiter()


def _user_id(db, email):
    return db.query(models.User).filter_by(email=email).first().id


def _pair(client, db):
    farmer = register(client, "f@x.t", "farmer")
    buyer = register(client, "b@x.t", "buyer")
    return farmer, buyer, _user_id(db, "f@x.t"), _user_id(db, "b@x.t")


def _product(db, farmer_id, name="Tomato"):
    p = models.Product(farmer_id=farmer_id, name=name, quantity=50, unit="kg",
                       price_per_unit=40, district="Gazipur")
    db.add(p)
    db.commit()
    return p.id


def _offer(db, product_id, buyer_id, farmer_id):
    o = models.Offer(product_id=product_id, buyer_id=buyer_id, farmer_id=farmer_id,
                     quantity=Decimal("5"), offered_price=Decimal("38"))
    db.add(o)
    db.commit()
    return o.id


def _create(client, headers, **kw):
    return client.post("/api/v1/conversations", headers=headers, json=kw)


def test_create_conversation_returns_other_without_contact_details(client, db):
    farmer, buyer, fid, bid = _pair(client, db)
    r = _create(client, buyer, other_user_id=fid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["farmer_id"] == fid and body["buyer_id"] == bid
    assert body["other"] == {"id": fid, "name": "User f", "role": "farmer",
                             "district": "Gazipur"}
    # Privacy: no phone or email anywhere in the response.
    assert "phone" not in r.text and "email" not in r.text
    assert "@x.t" not in r.text
    assert body["unread_count"] == 0 and body["last_message"] is None


def test_create_or_find_same_pair_and_listing(client, db):
    farmer, buyer, fid, bid = _pair(client, db)
    pid = _product(db, fid)
    r1 = _create(client, buyer, other_user_id=fid, listing_id=pid)
    r2 = _create(client, farmer, other_user_id=bid, listing_id=pid)
    assert r1.status_code == r2.status_code == 200, (r1.text, r2.text)
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["listing_name"] == "Tomato"
    # A different listing is a different thread; no listing is another one.
    pid2 = _product(db, fid, name="Potato")
    assert _create(client, buyer, other_user_id=fid, listing_id=pid2).json()["id"] != r1.json()["id"]
    assert _create(client, buyer, other_user_id=fid).json()["id"] != r1.json()["id"]
    assert db.query(models.ChatConversation).count() == 3


def test_create_conversation_with_offer_link(client, db):
    farmer, buyer, fid, bid = _pair(client, db)
    pid = _product(db, fid)
    oid = _offer(db, pid, bid, fid)
    r = _create(client, buyer, other_user_id=fid, listing_id=pid, offer_id=oid)
    assert r.status_code == 200, r.text
    assert r.json()["offer_id"] == oid
    # Same pair + same listing + same offer finds the same thread again.
    assert _create(client, farmer, other_user_id=bid, listing_id=pid, offer_id=oid).json()["id"] == r.json()["id"]
    # Same offer without the listing is a different thread (different tuple).
    assert _create(client, farmer, other_user_id=bid, offer_id=oid).json()["id"] != r.json()["id"]


def test_create_validation_errors(client, db):
    farmer, buyer, fid, bid = _pair(client, db)
    other_buyer = register(client, "b2@x.t", "buyer")
    other_farmer = register(client, "f2@x.t", "farmer")
    transporter = register(client, "t@x.t", "transporter")
    assert _create(client, buyer, other_user_id=bid).status_code == 400  # self
    assert _create(client, buyer, other_user_id=99999).status_code == 404  # missing user
    assert _create(client, buyer, other_user_id=_user_id(db, "b2@x.t")).status_code == 400  # buyer-buyer
    assert _create(client, farmer, other_user_id=_user_id(db, "f2@x.t")).status_code == 400  # farmer-farmer
    assert _create(client, transporter, other_user_id=fid).status_code == 400  # transporter
    assert _create(client, buyer, other_user_id=fid, listing_id=99999).status_code == 404
    # Listing belonging to a different farmer cannot anchor this thread.
    pid2 = _product(db, _user_id(db, "f2@x.t"))
    assert _create(client, buyer, other_user_id=fid, listing_id=pid2).status_code == 400
    # Offer belonging to another pair cannot anchor this thread.
    pid = _product(db, fid)
    oid = _offer(db, pid, _user_id(db, "b2@x.t"), fid)
    assert _create(client, buyer, other_user_id=fid, offer_id=oid).status_code == 400


def test_message_exchange_unread_counts_and_notification(client, db):
    farmer, buyer, fid, bid = _pair(client, db)
    cid = _create(client, buyer, other_user_id=fid).json()["id"]

    r = client.post(f"/api/v1/conversations/{cid}/messages", headers=buyer,
                    json={"body": "Hello, is the tomato still available?"})
    assert r.status_code == 200, r.text
    assert r.json()["sender_id"] == bid and r.json()["read_at"] is None

    # Farmer sees 1 unread (list + aggregate); buyer sees 0.
    mine = client.get("/api/v1/conversations", headers=farmer).json()
    assert len(mine) == 1 and mine[0]["unread_count"] == 1
    assert mine[0]["last_message"]["body"] == "Hello, is the tomato still available?"
    assert client.get("/api/v1/conversations/unread-count", headers=farmer).json() == {"unread": 1}
    assert client.get("/api/v1/conversations/unread-count", headers=buyer).json() == {"unread": 0}

    # A Notification was created for the recipient.
    notes = db.query(models.Notification).filter_by(user_id=fid).all()
    assert len(notes) == 1 and notes[0].title == "New message"
    assert "tomato" in notes[0].message

    # Farmer reads the thread: messages visible, mark-read clears the count.
    msgs = client.get(f"/api/v1/conversations/{cid}/messages", headers=farmer).json()
    assert len(msgs) == 1 and msgs[0]["body"].startswith("Hello")
    assert msgs[0]["sender_name"] == "User b"
    assert client.post(f"/api/v1/conversations/{cid}/read", headers=farmer).json() == {"marked_read": 1}
    assert client.get("/api/v1/conversations/unread-count", headers=farmer).json() == {"unread": 0}
    assert client.post(f"/api/v1/conversations/{cid}/read", headers=farmer).json() == {"marked_read": 0}

    # Farmer replies; now the buyer has the unread message.
    client.post(f"/api/v1/conversations/{cid}/messages", headers=farmer,
                json={"body": "Yes, still available."})
    assert client.get("/api/v1/conversations/unread-count", headers=buyer).json() == {"unread": 1}
    msgs = client.get(f"/api/v1/conversations/{cid}/messages", headers=buyer).json()
    assert [m["body"] for m in msgs] == ["Hello, is the tomato still available?",
                                         "Yes, still available."]


def test_non_participant_forbidden(client, db):
    farmer, buyer, fid, bid = _pair(client, db)
    outsider = register(client, "o@x.t", "buyer")
    cid = _create(client, buyer, other_user_id=fid).json()["id"]
    assert client.get(f"/api/v1/conversations/{cid}/messages", headers=outsider).status_code == 403
    assert client.post(f"/api/v1/conversations/{cid}/messages", headers=outsider,
                       json={"body": "hi"}).status_code == 403
    assert client.post(f"/api/v1/conversations/{cid}/read", headers=outsider).status_code == 403
    # The outsider's own inbox is empty; the thread is invisible to them.
    assert client.get("/api/v1/conversations", headers=outsider).json() == []
    # Missing conversation is 404, even for a participant.
    assert client.get("/api/v1/conversations/99999/messages", headers=buyer).status_code == 404


def test_message_body_validation(client, db):
    farmer, buyer, fid, bid = _pair(client, db)
    cid = _create(client, buyer, other_user_id=fid).json()["id"]
    url = f"/api/v1/conversations/{cid}/messages"
    assert client.post(url, headers=buyer, json={"body": "   "}).status_code == 400
    assert client.post(url, headers=buyer, json={"body": ""}).status_code == 422
    assert client.post(url, headers=buyer, json={"body": "x" * 2001}).status_code == 422
    assert client.post(url, headers=buyer, json={"body": "  padded  "}).json()["body"] == "padded"


def test_message_rate_limit(client, db, monkeypatch):
    from app.services import rate_limit
    monkeypatch.setattr(rate_limit.message_limiter, "limit", 2)
    farmer, buyer, fid, bid = _pair(client, db)
    cid = _create(client, buyer, other_user_id=fid).json()["id"]
    url = f"/api/v1/conversations/{cid}/messages"
    assert client.post(url, headers=buyer, json={"body": "one"}).status_code == 200
    assert client.post(url, headers=buyer, json={"body": "two"}).status_code == 200
    assert client.post(url, headers=buyer, json={"body": "three"}).status_code == 429
    # The limit is per sender: the farmer can still reply.
    assert client.post(url, headers=farmer, json={"body": "reply"}).status_code == 200


def test_inbox_sorted_by_recent_activity(client, db):
    farmer, buyer, fid, bid = _pair(client, db)
    buyer2 = register(client, "b2@x.t", "buyer")
    c1 = _create(client, buyer, other_user_id=fid).json()["id"]
    c2 = _create(client, buyer2, other_user_id=fid).json()["id"]
    # Newest thread first before any messages; a message bumps its thread.
    mine = client.get("/api/v1/conversations", headers=farmer).json()
    assert [c["id"] for c in mine] == [c2, c1]
    client.post(f"/api/v1/conversations/{c1}/messages", headers=buyer, json={"body": "bump"})
    mine = client.get("/api/v1/conversations", headers=farmer).json()
    assert [c["id"] for c in mine] == [c1, c2]
