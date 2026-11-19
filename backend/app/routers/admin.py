"""Admin-only endpoints: platform stats, user management, audit logs."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db, escape_like
from ..security import require_role
from ..services.audit import log_audit

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
admin = require_role("admin")


def _recent_activity(db: Session, limit: int = 8) -> list[dict]:
    """Latest platform activity across users, orders and products, newest
    first: the admin dashboard's Recent activity feed. Each item carries a
    kind + title + detail (names/numbers only — the frontend supplies the
    translated kind label) and the creation timestamp."""
    items: list[dict] = []
    for u in (db.query(models.User).order_by(models.User.created_at.desc(),
                                             models.User.id.desc()).limit(5).all()):
        items.append({"kind": "user", "title": u.name, "detail": u.role,
                      "created_at": u.created_at})
    for o in (db.query(models.Order).order_by(models.Order.created_at.desc(),
                                              models.Order.id.desc()).limit(5).all()):
        product = getattr(o, "product", None)
        detail = (f"{product.name} · {o.quantity:g} {product.unit}"
                  if product else f"{o.quantity:g}")
        items.append({"kind": "order", "title": f"#{o.id}", "detail": detail,
                      "created_at": o.created_at})
    for p in (db.query(models.Product).order_by(models.Product.created_at.desc(),
                                                models.Product.id.desc()).limit(5).all()):
        items.append({"kind": "product", "title": p.name, "detail": p.district,
                      "created_at": p.created_at})
    # created_at is a naive UTC datetime everywhere in this app; fall back
    # to datetime.min (also naive) for any row that lacks one.
    items.sort(key=lambda i: i["created_at"] or datetime.min, reverse=True)
    return items[:limit]


@router.get("/stats")
def stats(db: Session = Depends(get_db), user=Depends(admin)):
    """Platform counts for the admin dashboard. Field names match the
    frontend's AdminStats contract (total_users / total_products /
    total_orders / total_revenue / users_by_role) — a mismatch here used
    to render every counter as 0 even with data present (found in the
    19 Nov 2026 live QA). total_revenue counts accepted + completed
    orders only; recent_activity is the newest users/orders/products."""
    users = db.query(models.User).all()
    orders = db.query(models.Order).all()
    by_role: dict[str, int] = {}
    for u in users:
        by_role[u.role] = by_role.get(u.role, 0) + 1
    return {"total_users": len(users),
            "total_products": db.query(models.Product).count(),
            "total_orders": len(orders),
            "total_revenue": round(sum(o.total_amount for o in orders
                                       if o.status in ("accepted", "completed")), 2),
            "pending_orders": sum(o.status == "pending" for o in orders),
            "users_by_role": by_role,
            "recent_activity": _recent_activity(db)}


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
