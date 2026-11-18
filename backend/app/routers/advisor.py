from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import CROPS, get_hub
from ..database import get_db
from ..security import get_current_user
from ..services import advisor as A, forecasting as F, sklearn_forecast as SK
from ..services.datasources import openmeteo

router = APIRouter(prefix="/api/v1/advisor", tags=["advisor"])
limiter = A.RateLimiter(max_calls=20, window_s=3600)


class AdviceIn(BaseModel):
    report: str = Field(default="", max_length=200_000)
    crop: str
    region: str = Field(default="", max_length=100)
    language: str = "en"
    hub_id: str | None = None


@router.get("/languages")
def languages():
    return [{"code": l.code, "name": l.name, "expected_fidelity": l.expected_fidelity, "note": l.note}
            for l in A.LANGUAGES.values()]


@router.post("/advice")
def advice(data: AdviceIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if data.crop.lower() not in CROPS:
        raise HTTPException(404, f"Unknown crop '{data.crop}'")
    if data.language not in A.LANGUAGES:
        raise HTTPException(400, f"Unsupported language; choose from {sorted(A.LANGUAGES)}")
    if not limiter.allow(str(user.id)):
        raise HTTPException(429, "Advice request limit reached; try again later")
    ctx: dict = {}
    hub = get_hub(data.hub_id) if data.hub_id else None
    if data.hub_id and hub is None:
        raise HTTPException(404, f"Unknown hub '{data.hub_id}'")
    if hub:
        try:
            f = F.get_or_compute(db, hub.id, data.crop.lower(), 8)
            ctx["price_signal"], ctx["forecast_reliable"] = f["signal"], f["reliable"]
            ctx["forecast_synthetic_share"] = f["series"]["synthetic_share"]
            ctx["forecast_model"] = "prophet"
        except F.ProphetNotAvailableError:
            # Prophet is optional: fall back to the scikit-learn forecaster so
            # the advisor still gets a price signal without it.
            try:
                f = SK.forecast_sklearn(db, hub, data.crop.lower(), 8)
                ctx["price_signal"], ctx["forecast_reliable"] = f["signal"], f["reliable"]
                ctx["forecast_synthetic_share"] = f["series"]["synthetic_share"]
                ctx["forecast_model"] = SK.MODEL_NAME
            except F.InsufficientDataError:
                ctx["price_signal"] = None
        except (F.InsufficientDataError, ImportError):
            ctx["price_signal"] = None
        wx = openmeteo.fetch_daily_outlook(hub.lat, hub.lon)
        if wx:
            ctx["weather_today"], ctx["weather_outlook"] = wx[0], wx[:5]
    return A.advise(data.report, data.crop.lower(), data.region or (hub.name if hub else ""),
                    data.language, ctx)
