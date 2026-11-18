"""Buyer offers on listings. Accepting an offer atomically reserves stock
and creates an accepted order, mirroring the conditional-update pattern in
main.place_order."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, update
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user, require_role

router = APIRouter(prefix="/api/v1/offers", tags=["offers"])


@router.post("")
def create_offer(data: schemas.OfferIn, db: Session = Depends(get_db),
                 user=Depends(require_role("buyer"))):
    p = db.query(models.Product).filter_by(id=data.product_id).first()
    if not p or p.status != "available":
        raise HTTPException(404, "Product unavailable")
    if p.farmer_id == user.id:
        raise HTTPException(400, "Cannot offer on your own product")
    offer = models.Offer(product_id=p.id, buyer_id=user.id, farmer_id=p.farmer_id,
                         quantity=Decimal(str(data.quantity)),
                         offered_price=Decimal(str(data.offered_price)),
                         message=data.message)
    db.add(offer)
    db.add(models.Notification(user_id=p.farmer_id, title="New offer",
             message=f"{user.name} offered {data.offered_price} per {p.unit} "
                     f"for {data.quantity} {p.unit} of {p.name}."))
    db.commit()
    db.refresh(offer)
    return {"id": offer.id, "status": offer.status}


@router.get("/my")
def my_offers(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role == "farmer":
        q = db.query(models.Offer).filter_by(farmer_id=user.id)
    elif user.role == "buyer":
        q = db.query(models.Offer).filter_by(buyer_id=user.id)
    else:
        return []
    rows = q.options(selectinload(models.Offer.product),
                     selectinload(models.Offer.buyer),
                     selectinload(models.Offer.farmer)).order_by(models.Offer.created_at.desc()).all()
    return [{"id": o.id, "product_id": o.product_id, "product_name": o.product.name,
             "buyer_id": o.buyer_id, "buyer_name": o.buyer.name,
             "farmer_id": o.farmer_id, "farmer_name": o.farmer.name,
             "quantity": float(o.quantity), "offered_price": float(o.offered_price),
             "message": o.message, "status": o.status,
             "created_at": o.created_at} for o in rows]


@router.patch("/{oid}")
def update_offer(oid: int, data: schemas.OfferStatusIn, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    if data.status not in ("accepted", "rejected", "cancelled"):
        raise HTTPException(400, "status must be accepted, rejected or cancelled")
    o = db.query(models.Offer).filter_by(id=oid).first()
    if not o:
        raise HTTPException(404, "Offer not found")
    if data.status in ("accepted", "rejected"):
        if user.role != "farmer" or o.farmer_id != user.id:
            raise HTTPException(403, "Only the farmer can accept or reject this offer")
    else:  # cancelled
        if user.role != "buyer" or o.buyer_id != user.id:
            raise HTTPException(403, "Only the buyer can cancel this offer")
    if o.status != "pending":
        raise HTTPException(400, "Offer is no longer pending")

    if data.status == "accepted":
        qty = float(o.quantity)
        price = float(o.offered_price)
        # Same atomic conditional stock decrement as main.place_order.
        stock_update = db.execute(
            update(models.Product)
            .where(models.Product.id == o.product_id,
                   models.Product.status == "available",
                   models.Product.quantity >= qty)
            .values(
                quantity=models.Product.quantity - qty,
                status=case(
                    (models.Product.quantity - qty <= 0, "sold"),
                    else_="available"
                )
            )
        )
        if stock_update.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Product unavailable or insufficient stock")
        order = models.Order(buyer_id=o.buyer_id, farmer_id=o.farmer_id,
                             product_id=o.product_id, quantity=qty, unit_price=price,
                             total_amount=round(qty * price, 2),
                             status="accepted", offer_id=o.id)
        db.add(order)
        o.status = "accepted"
        db.add(models.Notification(user_id=o.buyer_id, title="Offer accepted",
                 message=f"Your offer on {o.product.name} was accepted."))
        db.commit()
        db.refresh(order)
        return {"id": o.id, "status": o.status, "order_id": order.id}

    o.status = data.status
    recipient_id = o.buyer_id if data.status == "rejected" else o.farmer_id
    db.add(models.Notification(user_id=recipient_id, title=f"Offer {data.status}",
             message=f"Offer on {o.product.name} was {data.status}."))
    db.commit()
    return {"id": o.id, "status": o.status, "order_id": None}
