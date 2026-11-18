import json
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models
from ..config import model_dir
from ..database import get_db
from ..security import require_role
from ..services import torch_vision as TV
from ..services import vision as V

router = APIRouter(prefix="/api/v1/vision", tags=["vision"])


@router.get("/status")
def status():
    cards = {}
    for task in ("ripeness", "disease"):
        p = model_dir() / f"{task}.card.json"
        cards[task] = json.loads(p.read_text()) if p.exists() else None
    torch_models = {task: TV.torch_model_version(task) for task in ("ripeness", "disease")}
    return {"models": cards, "sklearn_models": cards,
            "torch_installed": TV.torch_available(), "torch_models": torch_models,
            "grade_table": V.GRADE_TABLE, "min_confidence": V.MIN_CONFIDENCE}


@router.post("/assess")
def assess(image: UploadFile = File(...), crop: str = Form(""), reference_price: float | None = Form(None),
           product_id: int | None = Form(None), apply_price: bool = Form(False),
           db: Session = Depends(get_db), user=Depends(require_role("farmer"))):
    data = image.file.read(V.MAX_IMAGE_BYTES + 1)
    try:
        result = V.assess(data, crop or None)
    except V.BadImageError as e:
        raise HTTPException(400, str(e))
    except V.ModelNotAvailableError as e:
        raise HTTPException(503, str(e))
    product = None
    if product_id is not None:
        product = db.get(models.Product, product_id)
        if not product or product.farmer_id != user.id:
            raise HTTPException(404, "Product not found")
    if reference_price is not None and reference_price <= 0:
        raise HTTPException(400, "reference_price must be positive")
    suggested = V.suggest_price(reference_price, result["price_multiplier"]) if reference_price else None
    result["suggested_price"] = suggested
    result["price_applied"] = False
    if apply_price:
        if product is None or suggested is None:
            raise HTTPException(400, "apply_price needs product_id, reference_price and a confident grade")
        product.price_per_unit = suggested          # explicit opt-in only; never automatic
        result["price_applied"] = True
    db.add(models.GradeAssessment(user_id=user.id, product_id=product_id, image_sha256=result["image_sha256"],
                                  ripeness=result.get("ripeness") or "", disease=result.get("disease") or "",
                                  grade=result["grade"], confidence=result["confidence"],
                                  price_multiplier=result["price_multiplier"], model_version=result["model_version"]))
    db.commit()
    return result
