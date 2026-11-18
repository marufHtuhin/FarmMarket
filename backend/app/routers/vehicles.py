"""Transporter vehicles: the fleet a transporter can offer for deliveries."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/api/v1/vehicles", tags=["vehicles"])
transporter = require_role("transporter")


def _vehicle_out(v: models.Vehicle) -> dict:
    return {"id": v.id, "transporter_id": v.transporter_id,
            "vehicle_type": v.vehicle_type, "capacity_kg": float(v.capacity_kg),
            "refrigerated": v.refrigerated, "plate_number": v.plate_number}


@router.post("")
def create_vehicle(data: schemas.VehicleIn, db: Session = Depends(get_db),
                   user=Depends(transporter)):
    v = models.Vehicle(transporter_id=user.id, vehicle_type=data.vehicle_type,
                       capacity_kg=Decimal(str(data.capacity_kg)),
                       refrigerated=data.refrigerated, plate_number=data.plate_number)
    db.add(v)
    db.commit()
    db.refresh(v)
    return _vehicle_out(v)


@router.get("")
def list_vehicles(db: Session = Depends(get_db), user=Depends(transporter)):
    rows = db.query(models.Vehicle).filter_by(transporter_id=user.id).all()
    return [_vehicle_out(v) for v in rows]


@router.delete("/{vid}")
def delete_vehicle(vid: int, db: Session = Depends(get_db), user=Depends(transporter)):
    v = db.query(models.Vehicle).filter_by(id=vid).first()
    if not v:
        raise HTTPException(404, "Vehicle not found")
    if v.transporter_id != user.id:
        raise HTTPException(403, "Not your vehicle")
    db.delete(v)
    db.commit()
    return {"message": "Vehicle deleted"}
