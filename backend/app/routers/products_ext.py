"""Product detail and listing-image uploads.

Images are stored under <UPLOAD_DIR>/products/{id}/<uuid>.<ext> and served
by the /uploads StaticFiles mount in main.py.
"""
import io
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from .. import models
from ..config import upload_dir
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/api/v1/products", tags=["products"])

MAX_IMAGES_PER_PRODUCT = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


@router.get("/{pid}")
def product_detail(pid: int, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter_by(id=pid).first()
    if not p:
        raise HTTPException(404, "Product not found")
    return {"id": p.id, "farmer_id": p.farmer_id,
            "farmer": {"id": p.farmer.id, "name": p.farmer.name,
                       "district": p.farmer.district, "is_verified": p.farmer.is_verified},
            "name": p.name, "quantity": p.quantity, "unit": p.unit,
            "price_per_unit": p.price_per_unit, "currency": p.currency,
            "district": p.district, "description": p.description,
            "image_url": p.image_url, "status": p.status,
            "created_at": p.created_at,
            "images": [{"id": i.id, "url": i.url} for i in p.images],
            "farm": {"id": p.farm.id, "name": p.farm.name} if p.farm else None}


@router.post("/{pid}/images")
def upload_images(pid: int, files: list[UploadFile] = File(...),
                  db: Session = Depends(get_db), user=Depends(require_role("farmer"))):
    p = db.query(models.Product).filter_by(id=pid).first()
    if not p:
        raise HTTPException(404, "Product not found")
    if p.farmer_id != user.id:
        raise HTTPException(403, "Not your product")
    existing = db.query(models.ListingImage).filter_by(product_id=pid).count()
    if existing + len(files) > MAX_IMAGES_PER_PRODUCT:
        raise HTTPException(400, f"At most {MAX_IMAGES_PER_PRODUCT} images per product")
    # Validate every file before writing anything, so a bad file in the
    # batch leaves no orphan files on disk.
    validated: list[tuple[str, bytes]] = []
    for f in files:
        ext = ALLOWED_TYPES.get((f.content_type or "").lower())
        if not ext:
            raise HTTPException(400, f"Unsupported image type: {f.content_type} (jpeg/png/webp only)")
        # Read at most one byte over the limit: an unbounded read() lets a
        # single huge upload exhaust server memory before the size check
        # runs (P10 audit finding). Same bounded-read pattern as vision.
        data = f.file.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "Image larger than 5MB")
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.load()
        except Exception:
            raise HTTPException(400, "Unreadable image file")
        validated.append((ext, data))
    dest_dir = upload_dir() / "products" / str(pid)
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for ext, data in validated:
        name = f"{uuid.uuid4().hex}{ext}"
        (dest_dir / name).write_bytes(data)
        img = models.ListingImage(product_id=pid, filename=name,
                                  url=f"/uploads/products/{pid}/{name}")
        db.add(img)
        saved.append(img)
    db.commit()
    for img in saved:
        db.refresh(img)
    return {"images": [{"id": i.id, "url": i.url} for i in saved]}
