"""Farm profiles: a farmer's plots of land. Farmer-only, ownership enforced."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/api/v1/farms", tags=["farms"])
farmer = require_role("farmer")


def _farm_out(f: models.Farm) -> dict:
    return {"id": f.id, "farmer_id": f.farmer_id, "name": f.name,
            "district": f.district, "upazila": f.upazila,
            "area_acres": float(f.area_acres) if f.area_acres is not None else None,
            "country_code": f.country_code, "created_at": f.created_at}


def _own_farm(db: Session, fid: int, user) -> models.Farm:
    f = db.query(models.Farm).filter_by(id=fid).first()
    if not f:
        raise HTTPException(404, "Farm not found")
    if f.farmer_id != user.id:
        raise HTTPException(403, "Not your farm")
    return f


@router.get("")
def list_farms(db: Session = Depends(get_db), user=Depends(farmer)):
    rows = db.query(models.Farm).filter_by(farmer_id=user.id).order_by(models.Farm.created_at.desc()).all()
    return [_farm_out(f) for f in rows]


@router.post("")
def create_farm(data: schemas.FarmIn, db: Session = Depends(get_db), user=Depends(farmer)):
    f = models.Farm(farmer_id=user.id, **data.model_dump())
    db.add(f)
    db.commit()
    db.refresh(f)
    return _farm_out(f)


@router.get("/{fid}")
def get_farm(fid: int, db: Session = Depends(get_db), user=Depends(farmer)):
    return _farm_out(_own_farm(db, fid, user))


@router.put("/{fid}")
def update_farm(fid: int, data: schemas.FarmUpdate, db: Session = Depends(get_db), user=Depends(farmer)):
    f = _own_farm(db, fid, user)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(f, k, v)
    db.commit()
    db.refresh(f)
    return _farm_out(f)


@router.delete("/{fid}")
def delete_farm(fid: int, db: Session = Depends(get_db), user=Depends(farmer)):
    f = _own_farm(db, fid, user)
    db.delete(f)
    db.commit()
    return {"message": "Farm deleted"}
