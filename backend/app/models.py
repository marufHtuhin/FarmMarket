from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Float, DateTime, Date, ForeignKey, Text, Boolean, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .config import utcnow
from .database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(25), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    district: Mapped[str] = mapped_column(String(100), default="")
    upazila: Mapped[str] = mapped_column(String(100), default="")
    business_name: Mapped[str] = mapped_column(String(150), default="")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Email verification (registration confirmation). Distinct from
    # is_verified, which is an ADMIN-set seller badge — never reuse it.
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    country_code: Mapped[str] = mapped_column(String(2), default="BD")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    products = relationship("Product", back_populates="farmer")
    demands = relationship("Demand", back_populates="buyer")

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    farm_id: Mapped[int | None] = mapped_column(ForeignKey("farms.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20), default="kg")
    price_per_unit: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="BDT")
    district: Mapped[str] = mapped_column(String(100), index=True)
    harvest_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    available_until: Mapped[object | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="available")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    farmer = relationship("User", back_populates="products")
    category = relationship("Category")
    farm = relationship("Farm", back_populates="products")
    images = relationship("ListingImage", back_populates="product", cascade="all, delete-orphan")

class Demand(Base):
    __tablename__ = "demand_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(100), index=True)
    required_quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20), default="kg")
    target_price: Mapped[float] = mapped_column(Float)
    district: Mapped[str] = mapped_column(String(100), index=True)
    required_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    buyer = relationship("User", back_populates="demands")

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float] = mapped_column(Float)
    total_amount: Mapped[float] = mapped_column(Float)
    delivery_address: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    transporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    delivery_status: Mapped[str] = mapped_column(String(30), default="not_assigned")
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offers.id"), nullable=True)
    proof_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    product = relationship("Product")
    offer = relationship("Offer")
    buyer = relationship("User", foreign_keys=[buyer_id])
    farmer = relationship("User", foreign_keys=[farmer_id])

class PriceRecord(Base):
    __tablename__ = "price_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_name: Mapped[str] = mapped_column(String(100), index=True)
    district: Mapped[str] = mapped_column(String(100), index=True)
    market_name: Mapped[str] = mapped_column(String(150), default="")
    price_per_unit: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20), default="kg")
    source: Mapped[str] = mapped_column(String(150), default="Demo reference data")
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(150))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# Price history + forecasting
# ---------------------------------------------------------------------------
class PriceObservation(Base):
    """One dated price observation for a crop at a trading hub."""
    __tablename__ = "price_observations"
    __table_args__ = (UniqueConstraint("hub_id", "crop", "observed_on", "source", name="uq_price_obs"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hub_id: Mapped[str] = mapped_column(String(40), index=True)
    crop: Mapped[str] = mapped_column(String(40), index=True)
    observed_on: Mapped[object] = mapped_column(Date, index=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="")
    unit: Mapped[str] = mapped_column(String(20), default="kg")
    source: Mapped[str] = mapped_column(String(150), default="")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    # Free-text note recorded with a manual price entry, e.g. "DAM Dhaka
    # retail report, 17 Nov 2026". NULL for imported / synthetic rows.
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ForecastSnapshot(Base):
    """Cached forecast result, valid while the underlying data fingerprint is unchanged."""
    __tablename__ = "forecast_snapshots"
    __table_args__ = (UniqueConstraint("hub_id", "crop", "horizon", name="uq_forecast_snapshot"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hub_id: Mapped[str] = mapped_column(String(40), index=True)
    crop: Mapped[str] = mapped_column(String(40), index=True)
    horizon: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# Vision grading (images are NOT stored; only a hash and the outcome)
# ---------------------------------------------------------------------------
class GradeAssessment(Base):
    __tablename__ = "grade_assessments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    image_sha256: Mapped[str] = mapped_column(String(64))
    ripeness: Mapped[str] = mapped_column(String(30), default="")
    disease: Mapped[str] = mapped_column(String(120), default="")
    grade: Mapped[str] = mapped_column(String(20), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    price_multiplier: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------------------
# Digital Twin: tamper-evident batch ledger
# ---------------------------------------------------------------------------
class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    crop: Mapped[str] = mapped_column(String(40))
    variety: Mapped[str] = mapped_column(String(80), default="")
    origin_district: Mapped[str] = mapped_column(String(100), default="")
    quantity_kg: Mapped[float] = mapped_column(Float, default=0.0)
    harvested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Device(Base):
    __tablename__ = "twin_devices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    label: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    moisture_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    moisture_kind: Mapped[str] = mapped_column(String(10), default="rh")  # rh | product
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    signature: Mapped[str] = mapped_column(String(64), default="")
    sealed: Mapped[bool] = mapped_column(Boolean, default=False)
    # True when the reading came from the demo simulator (scripts/simulate_sensors.py),
    # never from a real sensor. Simulated readings are labelled SIMULATED everywhere.
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)


class LedgerBlock(Base):
    __tablename__ = "ledger_blocks"
    __table_args__ = (UniqueConstraint("batch_id", "idx", name="uq_ledger_idx"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[str] = mapped_column(String(40))
    event_type: Mapped[str] = mapped_column(String(40))
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[str] = mapped_column(Text)  # canonical JSON
    prev_hash: Mapped[str] = mapped_column(String(64))
    block_hash: Mapped[str] = mapped_column(String(64))
    anchor_ref: Mapped[str] = mapped_column(String(200), default="")


# ---------------------------------------------------------------------------
# Foundation (master spec Phases 1-2): countries, farms, crops, offers,
# vehicles, refresh/reset tokens, conversations, audit log, data sources.
# Money/quantities on NEW tables use DECIMAL Numeric(12,2); legacy tables
# keep Float so existing behaviour is unchanged.
# ---------------------------------------------------------------------------
class Country(Base):
    __tablename__ = "countries"
    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(String(3))
    default_hub_id: Mapped[str] = mapped_column(String(40), default="")


class Region(Base):
    """A trading hub (city) inside a country; coordinates are city-level."""
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"), index=True)
    hub_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))


class Farm(Base):
    __tablename__ = "farms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    district: Mapped[str] = mapped_column(String(100), default="")
    upazila: Mapped[str] = mapped_column(String(100), default="")
    area_acres: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), default="BD")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    farmer = relationship("User")
    products = relationship("Product", back_populates="farm")


class Crop(Base):
    __tablename__ = "crops"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # e.g. "tomato"
    name: Mapped[str] = mapped_column(String(80))
    default_unit: Mapped[str] = mapped_column(String(20), default="kg")
    local_names = relationship("CropLocalName", back_populates="crop", cascade="all, delete-orphan")


class CropLocalName(Base):
    __tablename__ = "crop_local_names"
    __table_args__ = (UniqueConstraint("crop_id", "language", name="uq_crop_local_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crop_id: Mapped[str] = mapped_column(ForeignKey("crops.id"), index=True)
    language: Mapped[str] = mapped_column(String(10))  # bn | en | sw ...
    name: Mapped[str] = mapped_column(String(100))
    crop = relationship("Crop", back_populates="local_names")


class Harvest(Base):
    __tablename__ = "harvests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    crop_id: Mapped[str] = mapped_column(ForeignKey("crops.id"), index=True)
    harvested_on: Mapped[object | None] = mapped_column(Date, nullable=True)
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    notes: Mapped[str] = mapped_column(Text, default="")
    farm = relationship("Farm")
    crop = relationship("Crop")


class Offer(Base):
    """A buyer's price offer on a listing. farmer_id is denormalized so a
    farmer can list offers on their products without joining products."""
    __tablename__ = "offers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    offered_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    product = relationship("Product")
    buyer = relationship("User", foreign_keys=[buyer_id])
    farmer = relationship("User", foreign_keys=[farmer_id])


class OrderItem(Base):
    """Line item for future multi-item orders; the single-item Order flow
    (Order.product_id/quantity) stays as-is."""
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class ListingImage(Base):
    __tablename__ = "listing_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    product = relationship("Product", back_populates="images")


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    transporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    vehicle_type: Mapped[str] = mapped_column(String(80))
    capacity_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    refrigerated: Mapped[bool] = mapped_column(Boolean, default=False)
    plate_number: Mapped[str] = mapped_column(String(40), default="")
    transporter = relationship("User")


class RefreshToken(Base):
    """Opaque refresh token; only the SHA-256 hash is stored. Rotation
    revokes the presented token; reuse of a revoked token revokes all of
    the user's tokens (theft detection)."""
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PasswordResetToken(Base):
    """One-time password reset token; only the SHA-256 hash is stored."""
    __tablename__ = "password_reset_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailVerificationToken(Base):
    """One-time email-verification token (registration confirmation);
    only the SHA-256 hash is stored. Mirrors PasswordResetToken."""
    __tablename__ = "email_verification_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Conversation(Base):
    """Krishi Bondhu assistant conversation (RAG assistant, later phase)."""
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    language: Mapped[str] = mapped_column(String(10), default="bn")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[str] = mapped_column(Text, default="")  # JSON list
    mode: Mapped[str] = mapped_column(String(20), default="template")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    conversation = relationship("Conversation", back_populates="messages")


# ---------------------------------------------------------------------------
# User-to-user messaging (farmer <-> buyer). Separate from the Krishi Bondhu
# assistant Conversation/Message above: these are chats between two users.
# Privacy: chat is in-app only — phone numbers and email addresses are never
# exposed through the messaging API; responses carry only id/name/role/district.
# ---------------------------------------------------------------------------
class ChatConversation(Base):
    """One farmer-buyer chat thread, optionally about a listing and/or offer.

    Uniqueness of (farmer, buyer, listing, offer) is enforced in the router's
    create-or-find lookup, not by a DB constraint: listing_id/offer_id are
    nullable and NULLs are distinct under a UNIQUE constraint in MySQL.
    """
    __tablename__ = "chat_conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offers.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Bumped on every new message so the inbox sorts by recent activity.
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    farmer = relationship("User", foreign_keys=[farmer_id])
    buyer = relationship("User", foreign_keys=[buyer_id])
    listing = relationship("Product")
    offer = relationship("Offer")
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("chat_conversations.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    conversation = relationship("ChatConversation", back_populates="messages")
    sender = relationship("User")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ExternalDataSource(Base):
    """Registry of external data feeds (FAOSTAT, World Bank, OpenWeather,
    CGIAR, DAM, PlantVillage) and their sync state."""
    __tablename__ = "external_data_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(20))  # faostat|worldbank|openweather|cgiar|dam|plantvillage
    endpoint: Mapped[str] = mapped_column(String(500), default="")
    countries: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of country codes
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="never_synced")
    notes: Mapped[str] = mapped_column(Text, default="")
