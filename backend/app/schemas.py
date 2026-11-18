from datetime import date
from pydantic import AliasChoices, BaseModel, EmailStr, Field, field_validator

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(default="", max_length=30)
    # Minimum length 6, no letter/digit complexity rule: any 6+ character
    # password is accepted (user decision, 18 Nov 2026). The 72-byte cap
    # below is a bcrypt limit, not a complexity rule.
    password: str = Field(min_length=6, max_length=72)

    @field_validator("password")
    @classmethod
    def bcrypt_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value

    role: str
    district: str = Field(default="", max_length=100)
    upazila: str = Field(default="", max_length=100)
    business_name: str = Field(default="", max_length=150)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ProductIn(BaseModel):
    name: str = Field(max_length=150)
    quantity: float = Field(gt=0)
    unit: str = Field(default="kg", pattern="^(kg|quintal|ton|piece)$")
    price_per_unit: float = Field(gt=0)
    district: str = Field(max_length=100)
    harvest_date: date | None = None
    available_until: date | None = None
    description: str = Field(default="", max_length=5000)
    image_url: str = Field(default="", max_length=2048)
    farm_id: int | None = None

class DemandIn(BaseModel):
    product_name: str = Field(max_length=150)
    required_quantity: float = Field(gt=0)
    unit: str = Field(default="kg", pattern="^(kg|quintal|ton|piece)$")
    target_price: float = Field(gt=0)
    district: str = Field(max_length=100)
    required_date: date | None = None
    notes: str = Field(default="", max_length=2000)

class OrderIn(BaseModel):
    product_id: int
    quantity: float = Field(gt=0)
    delivery_address: str = Field(default="", max_length=500)

class StatusIn(BaseModel):
    status: str


# --- Auth: refresh tokens + password reset (Phases 1-2) ---
class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class VerifyEmailIn(BaseModel):
    token: str


class ResetPasswordIn(BaseModel):
    token: str
    # Same policy as registration: minimum 6 characters, no complexity rule.
    new_password: str = Field(min_length=6, max_length=72)

    @field_validator("new_password")
    @classmethod
    def bcrypt_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


# --- Farms ---
class FarmIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    district: str = ""
    upazila: str = ""
    area_acres: float | None = Field(default=None, gt=0)
    country_code: str = "BD"


class FarmUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    district: str | None = None
    upazila: str | None = None
    area_acres: float | None = Field(default=None, gt=0)
    country_code: str | None = None


# --- Offers ---
class OfferIn(BaseModel):
    product_id: int
    quantity: float = Field(gt=0)
    offered_price: float = Field(gt=0)
    message: str = Field(default="", max_length=2000)


class OfferStatusIn(BaseModel):
    status: str  # accepted | rejected | cancelled


# --- Farmer-buyer messaging ---
class ConversationIn(BaseModel):
    other_user_id: int
    listing_id: int | None = None
    offer_id: int | None = None


class ChatMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


# --- Vehicles ---
class VehicleIn(BaseModel):
    vehicle_type: str = Field(min_length=1, max_length=80)
    capacity_kg: float = Field(gt=0)
    refrigerated: bool = False
    plate_number: str = Field(default="", max_length=30)


# --- Deliveries ---
class AssignIn(BaseModel):
    transporter_id: int


class DeliveryUpdateIn(BaseModel):
    delivery_status: str  # picked_up | in_transit | delivered
    proof_note: str | None = Field(default=None, max_length=1000)


# --- Admin ---
class VerifyIn(BaseModel):
    is_verified: bool


# --- Manual price entry (admin) ---
class ManualPriceIn(BaseModel):
    crop: str
    hub: str
    price: float = Field(gt=0)
    # The market day the price applies to. Accepted under the key "date"
    # (or "observed_on"); defaults to today. Named observed_on here because
    # a field named `date` would shadow the imported date type.
    observed_on: date | None = Field(default=None,
                                     validation_alias=AliasChoices("date", "observed_on"))
    # Optional source note, e.g. "DAM Dhaka retail report". Stored verbatim
    # on the observation; the source column itself is always "manual".
    note: str | None = Field(default=None, max_length=200,
                             validation_alias=AliasChoices("note", "source_note"))
