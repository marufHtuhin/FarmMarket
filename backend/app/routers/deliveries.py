"""Deliveries: assigning orders to transporters and tracking delivery status.

Delivery state machine: not_assigned -> assigned -> picked_up -> in_transit
-> delivered. "delivered" is only reachable from picked_up or in_transit;
delivering an accepted order also completes it.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user, require_role

router = APIRouter(prefix="/api/v1", tags=["deliveries"])

# delivery_status -> set of statuses it may transition from
ALLOWED_TRANSITIONS = {
    "picked_up": {"assigned"},
    "in_transit": {"picked_up"},
    "delivered": {"picked_up", "in_transit"},
}


@router.patch("/orders/{oid}/assign")
def assign_order(oid: int, data: schemas.AssignIn, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    o = db.query(models.Order).filter_by(id=oid).first()
    if not o:
        raise HTTPException(404, "Order not found")
    if not (user.role == "admin" or (user.role == "farmer" and o.farmer_id == user.id)):
        raise HTTPException(403, "Only the farmer or an admin can assign a delivery")
    # Only an accepted order can be handed to a transporter: assigning a
    # pending/rejected/cancelled order would dispatch goods that were never
    # agreed (audit P5 finding — the UI only shows the picker for accepted
    # orders, but the API did not enforce it).
    if o.status != "accepted":
        raise HTTPException(400, "Only accepted orders can be assigned a delivery")
    # Re-assigning is fine while the parcel still waits (assigned), but once
    # a transporter has picked it up, re-assignment would orphan them and
    # rewind the delivery state machine.
    if o.delivery_status in ("picked_up", "in_transit", "delivered"):
        raise HTTPException(400, "Delivery already in progress; cannot re-assign")
    t = db.query(models.User).filter_by(id=data.transporter_id).first()
    if not t:
        raise HTTPException(404, "Transporter not found")
    if t.role != "transporter":
        raise HTTPException(400, "User is not a transporter")
    o.transporter_id = t.id
    o.delivery_status = "assigned"
    db.add(models.Notification(user_id=t.id, title="Delivery assigned",
             message=f"Order #{o.id}: {o.product.name} delivery assigned to you."))
    db.commit()
    return {"message": "Delivery assigned", "order_id": o.id,
            "transporter_id": t.id, "delivery_status": o.delivery_status}


@router.get("/deliveries")
def my_deliveries(db: Session = Depends(get_db), user=Depends(require_role("transporter"))):
    rows = (db.query(models.Order).filter_by(transporter_id=user.id)
            .options(selectinload(models.Order.product),
                     selectinload(models.Order.buyer),
                     selectinload(models.Order.farmer))
            .order_by(models.Order.created_at.desc()).all())
    return [{"order_id": o.id, "product_id": o.product_id, "product_name": o.product.name,
             "buyer_id": o.buyer_id, "buyer_name": o.buyer.name,
             "farmer_id": o.farmer_id, "farmer_name": o.farmer.name,
             "district": o.product.district, "quantity": o.quantity,
             "unit": o.product.unit, "status": o.status,
             "delivery_status": o.delivery_status, "proof_note": o.proof_note,
             "delivery_address": o.delivery_address,
             "created_at": o.created_at} for o in rows]


@router.patch("/deliveries/{order_id}")
def update_delivery(order_id: int, data: schemas.DeliveryUpdateIn,
                    db: Session = Depends(get_db), user=Depends(require_role("transporter"))):
    if data.delivery_status not in ALLOWED_TRANSITIONS:
        raise HTTPException(400, "delivery_status must be picked_up, in_transit or delivered")
    o = db.query(models.Order).filter_by(id=order_id).first()
    if not o:
        raise HTTPException(404, "Order not found")
    if o.transporter_id != user.id:
        raise HTTPException(403, "Delivery not assigned to you")
    if o.delivery_status not in ALLOWED_TRANSITIONS[data.delivery_status]:
        raise HTTPException(400,
            f"Cannot move delivery from {o.delivery_status} to {data.delivery_status}")
    o.delivery_status = data.delivery_status
    if data.proof_note is not None:
        o.proof_note = data.proof_note
    if data.delivery_status == "delivered" and o.status == "accepted":
        o.status = "completed"
    db.commit()
    return {"message": "Delivery updated", "order_id": o.id,
            "delivery_status": o.delivery_status, "status": o.status}
