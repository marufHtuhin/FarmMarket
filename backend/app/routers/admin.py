"""Admin-only endpoints: platform stats, user management, audit logs."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db, escape_like
from ..security import require_role
from ..services.audit import log_audit

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
admin = require_role("admin")


@router.get("/stats")
def stats(db: Session = Depends(get_db), user=Depends(admin)):
    users = db.query(models.User).all()
    orders = db.query(models.Order).all()
    return {"users_total": len(users),
            "farmers": sum(u.role == "farmer" for u in users),
            "buyers": sum(u.role == "buyer" for u in users),
            "transporters": sum(u.role == "transporter" for u in users),
            "products": db.query(models.Product).count(),
            "orders": len(orders),
            "pending_orders": sum(o.status == "pending" for o in orders),
            "total_sales": round(sum(o.total_amount for o in orders
                                     if o.status in ("accepted", "completed")), 2)}


@router.get("/users")
def list_users(search: str = Query(""), role: str = Query(""),
               page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
               db: Session = Depends(get_db), user=Depends(admin)):
    q = db.query(models.User)
    if role:
        q = q.filter_by(role=role)
    if search:
        like = escape_like(search)
        q = q.filter(or_(models.User.name.ilike(like, escape="\\"),
                         models.User.email.ilike(like, escape="\\")))
    total = q.count()
    rows = (q.order_by(models.User.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    return {"items": [{"id": u.id, "name": u.name, "email": u.email, "role": u.role,
                       "district": u.district, "is_verified": u.is_verified,
                       "country_code": u.country_code, "created_at": u.created_at}
                      for u in rows],
            "total": total, "page": page, "page_size": page_size}


@router.patch("/users/{uid}/verify")
def verify_user(uid: int, data: schemas.VerifyIn, db: Session = Depends(get_db),
                user=Depends(admin)):
    target = db.query(models.User).filter_by(id=uid).first()
    if not target:
        raise HTTPException(404, "User not found")
    target.is_verified = data.is_verified
    db.commit()
    log_audit(db, user.id, "user_verified" if data.is_verified else "user_unverified",
              f"user_id={uid}")
    return {"id": target.id, "is_verified": target.is_verified}


@router.get("/audit-logs")
def audit_logs(db: Session = Depends(get_db), user=Depends(admin)):
    rows = (db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc())
            .limit(100).all())
    return [{"id": a.id, "user_id": a.user_id, "action": a.action,
             "details": a.details, "created_at": a.created_at} for a in rows]
