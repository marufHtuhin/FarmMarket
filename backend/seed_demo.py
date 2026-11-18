"""Seed FarmMarket with realistic Bangladeshi demo data.

Run from the backend/ directory:

    python seed_demo.py

ALL data seeded here is illustrative demo data for the hackathon demo:
prices are NOT live market rates, phone numbers are demo numbers, and the
price history is synthetic (flagged is_synthetic=True, source="synthetic-demo").
Replace it with verified sources before any real-world use.

The script is idempotent: re-running it skips existing users (by email),
products (by farmer + name), demands (by buyer + product name), farms (by
farmer + name), crops (by id), countries/regions (by code/hub id), vehicles
(by transporter + plate) and offers (by buyer + product + pending status),
and price observations (via upsert on the unique hub/crop/date/source key).
PriceRecord rows are only inserted when that table is empty.
"""
from datetime import date, timedelta
from decimal import Decimal
import argparse
import os
import sys

from app.config import COUNTRY_ORDER, CROP_CATALOG, HUB_PROFILES, get_hub
from app.database import Base, engine, SessionLocal
from app import models
from app.security import hash_password
from app.services.datasources import prices, synthetic

DEMO_PASSWORD = "Demo123!"
PRICE_SOURCE = "Illustrative demo data - replace with verified source"
TODAY = date.today()

# --- Demo users ------------------------------------------------------------
# (email, name, role, district, phone[, business_name]). Phones are clearly demo numbers.
USERS = [
    ("farmer@farmmarket.demo", "Rahim Uddin", "farmer", "Gazipur", "01710000001"),
    ("buyer@farmmarket.demo", "Dhaka Fresh Mart", "buyer", "Dhaka", "01710000002"),
    ("karima@farmmarket.demo", "Karima Begum", "farmer", "Bogura", "01710000003"),
    ("abdul.malek@farmmarket.demo", "Abdul Malek", "farmer", "Chattogram", "01710000004"),
    ("nasrin@farmmarket.demo", "Nasrin Akter", "farmer", "Rajshahi", "01710000005"),
    ("jamal@farmmarket.demo", "Jamal Hossain", "farmer", "Khulna", "01710000006"),
    ("sabina@farmmarket.demo", "Sabina Yasmin", "farmer", "Sylhet", "01710000007"),
    ("rafiqul@farmmarket.demo", "Rafiqul Islam", "farmer", "Cumilla", "01710000008"),
    ("chattogram.bazar@farmmarket.demo", "Chattogram Bazar Ltd", "buyer", "Chattogram", "01710000009"),
    ("rajshahi.agro@farmmarket.demo", "Rajshahi Agro Traders", "buyer", "Rajshahi", "01710000010"),
    ("transporter@farmmarket.demo", "Transporter", "transporter", "Dhaka", "01710000011", "Dhaka Cold Chain"),
    ("admin@farmmarket.demo", "Admin", "admin", "Dhaka", "01710000012"),
]

# --- Demo products ---------------------------------------------------------
# (farmer email, English name, Bangla name, price ৳/kg, quantity kg, days available)
# English names go in `name` (the frontend maps them to emoji/Bangla display);
# Bangla names go in the description. All prices are illustrative demo values.
PRODUCTS = [
    ("farmer@farmmarket.demo", "Tomato", "টমেটো", 38, 600, 5),
    ("karima@farmmarket.demo", "Potato", "আলু", 32, 1200, 10),
    ("nasrin@farmmarket.demo", "Onion", "পেঁয়াজ", 65, 800, 7),
    ("rafiqul@farmmarket.demo", "Rice", "ধান/চাল", 68, 2000, 10),
    ("jamal@farmmarket.demo", "Banana", "কলা", 55, 500, 5),
    ("nasrin@farmmarket.demo", "Mango", "আম", 120, 300, 6),
    ("sabina@farmmarket.demo", "Brinjal", "বেগুন", 45, 400, 5),
    ("jamal@farmmarket.demo", "Chili", "মরিচ", 180, 200, 8),
    ("karima@farmmarket.demo", "Cauliflower", "ফুলকপি", 40, 600, 5),
    ("abdul.malek@farmmarket.demo", "Jute", "পাট", 55, 1500, 10),
]

PRODUCT_BLURBS = {
    "Tomato": "fresh, firm tomatoes, harvested this week",
    "Potato": "clean, medium-sized potatoes, good for storage",
    "Onion": "dry, well-cured onions from this season's harvest",
    "Rice": "milled rice, well dried and ready for delivery",
    "Banana": "ripe, sweet bananas, freshly cut bunches",
    "Mango": "sweet, tree-ripened mangoes, carefully packed",
    "Brinjal": "glossy, fresh brinjals, picked this morning",
    "Chili": "hot green chilies, fresh and crisp",
    "Cauliflower": "firm white cauliflower heads, freshly harvested",
    "Jute": "good-grade jute fibre, sun-dried and bundled",
}

# --- Demo demands ----------------------------------------------------------
# (buyer email, product name, quantity kg, target price ৳/kg, district, days until required)
DEMANDS = [
    ("buyer@farmmarket.demo", "Tomato", 500, 42, "Gazipur", 3),
    ("buyer@farmmarket.demo", "Onion", 800, 70, "Dhaka", 4),
    ("buyer@farmmarket.demo", "Potato", 1000, 35, "Dhaka", 5),
    ("rajshahi.agro@farmmarket.demo", "Mango", 300, 130, "Rajshahi", 3),
    ("chattogram.bazar@farmmarket.demo", "Banana", 400, 60, "Chattogram", 4),
    ("buyer@farmmarket.demo", "Chili", 200, 190, "Khulna", 3),
]

# --- Demo farms ------------------------------------------------------------
# (farmer email, farm name, district, upazila, area in acres)
FARMS = [
    ("farmer@farmmarket.demo", "Uddin Farm — Gazipur Sadar", "Gazipur", "Gazipur Sadar", Decimal("2.5")),
    ("farmer@farmmarket.demo", "Uddin Farm — Kapasia", "Gazipur", "Kapasia", Decimal("1.75")),
]

# --- Demo vehicle ----------------------------------------------------------
# (transporter email, vehicle type, capacity kg, refrigerated, plate)
VEHICLES = [
    ("transporter@farmmarket.demo", "Refrigerated truck", Decimal("2000"), True, "DHK-1234"),
]

# --- Demo offer ------------------------------------------------------------
# (buyer email, farmer email, product name, quantity kg, offered price ৳/kg, message)
OFFERS = [
    ("buyer@farmmarket.demo", "farmer@farmmarket.demo", "Tomato", Decimal("100"), Decimal("40"),
     "Regular buyer — can collect this week."),
]

# Bangladeshi hubs x forecast crops for the synthetic weekly price history.
BD_HUB_IDS = ["dhaka", "chattogram", "rajshahi", "khulna", "sylhet"]


def main(argv=None):
    """Seed the demo data. Refuses to run when ENVIRONMENT=production
    unless --allow-production is passed: demo accounts with a public
    password (Demo123!) must never be seeded into a production database
    by accident."""
    parser = argparse.ArgumentParser(description="Seed FarmMarket demo data.")
    parser.add_argument("--allow-production", action="store_true",
                        help="allow seeding even when ENVIRONMENT=production")
    args = parser.parse_args(argv)
    if (os.getenv("ENVIRONMENT", "development").lower() == "production"
            and not args.allow_production):
        print("ERROR: refusing to seed demo data in production (public demo "
              "credentials must not land in a production database). Re-run "
              "with --allow-production if you really mean it.",
              file=sys.stderr)
        raise SystemExit(2)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        users = {}
        new_users = 0
        for row in USERS:
            email, name, role, district, phone = row[:5]
            business_name = row[5] if len(row) > 5 else ""
            existing = db.query(models.User).filter_by(email=email).first()
            if existing:
                users[email] = existing
                continue
            user = models.User(email=email, name=name, role=role, district=district,
                               password_hash=hash_password(DEMO_PASSWORD), phone=phone,
                               business_name=business_name)
            db.add(user)
            db.commit()
            db.refresh(user)
            users[email] = user
            new_users += 1

        # Countries + regions (trading hubs) from config.py.
        new_countries = new_regions = 0
        hubs_by_iso3: dict[str, list] = {}
        for profile in HUB_PROFILES.values():
            for h in profile:
                hubs_by_iso3.setdefault(h.iso3, []).append(h)
        for iso3, code in COUNTRY_ORDER:
            hubs = hubs_by_iso3.get(iso3, [])
            if not hubs:
                continue
            if not db.query(models.Country).filter_by(code=code).first():
                db.add(models.Country(code=code, name=hubs[0].country,
                                      currency=hubs[0].currency, default_hub_id=hubs[0].id))
                new_countries += 1
            for h in hubs:
                if not db.query(models.Region).filter_by(hub_id=h.id).first():
                    db.add(models.Region(country_code=code, hub_id=h.id, name=h.name,
                                         lat=h.lat, lon=h.lon, currency=h.currency))
                    new_regions += 1
        db.commit()

        # Crop catalog with Bangla local names.
        new_crops = 0
        for c in CROP_CATALOG:
            if db.query(models.Crop).filter_by(id=c["id"]).first():
                continue
            db.add(models.Crop(id=c["id"], name=c["name"], default_unit=c["unit"]))
            db.add(models.CropLocalName(crop_id=c["id"], language="bn", name=c["bn"]))
            new_crops += 1
        db.commit()

        # Farms for Rahim Uddin.
        new_farms = 0
        for farmer_email, name, district, upazila, area in FARMS:
            farmer = users[farmer_email]
            if db.query(models.Farm).filter_by(farmer_id=farmer.id, name=name).first():
                continue
            db.add(models.Farm(farmer_id=farmer.id, name=name, district=district,
                               upazila=upazila, area_acres=area, country_code="BD"))
            new_farms += 1
        db.commit()

        # Vehicle for the transporter.
        new_vehicles = 0
        for transporter_email, vtype, capacity, refrig, plate in VEHICLES:
            t = users[transporter_email]
            if db.query(models.Vehicle).filter_by(transporter_id=t.id, plate_number=plate).first():
                continue
            db.add(models.Vehicle(transporter_id=t.id, vehicle_type=vtype,
                                  capacity_kg=capacity, refrigerated=refrig, plate_number=plate))
            new_vehicles += 1
        db.commit()

        new_products = 0
        for farmer_email, name, bn_name, price, qty, days in PRODUCTS:
            farmer = users[farmer_email]
            if db.query(models.Product).filter_by(farmer_id=farmer.id, name=name).first():
                continue
            db.add(models.Product(
                farmer_id=farmer.id, name=name, quantity=qty, unit="kg",
                price_per_unit=price, district=farmer.district,
                harvest_date=TODAY, available_until=TODAY + timedelta(days=days),
                description=f"{bn_name} — {PRODUCT_BLURBS[name]}. Illustrative demo listing."))
            new_products += 1
        db.commit()

        new_demands = 0
        for buyer_email, product_name, qty, target, district, days in DEMANDS:
            buyer = users[buyer_email]
            if db.query(models.Demand).filter_by(buyer_id=buyer.id, product_name=product_name).first():
                continue
            db.add(models.Demand(
                buyer_id=buyer.id, product_name=product_name, required_quantity=qty,
                unit="kg", target_price=target, district=district,
                required_date=TODAY + timedelta(days=days),
                notes="Good quality required. Illustrative demo demand."))
            new_demands += 1
        db.commit()

        # Sample pending offer (buyer -> tomato).
        new_offers = 0
        for buyer_email, farmer_email, product_name, qty, price, message in OFFERS:
            buyer = users[buyer_email]
            farmer = users[farmer_email]
            product = db.query(models.Product).filter_by(farmer_id=farmer.id, name=product_name).first()
            if not product:
                continue
            if db.query(models.Offer).filter_by(buyer_id=buyer.id, product_id=product.id, status="pending").first():
                continue
            db.add(models.Offer(product_id=product.id, buyer_id=buyer.id, farmer_id=farmer.id,
                                quantity=qty, offered_price=price, message=message))
            new_offers += 1
        db.commit()

        new_price_records = 0
        if db.query(models.PriceRecord).count() == 0:
            for farmer_email, name, _bn, price, _qty, _days in PRODUCTS:
                district = users[farmer_email].district
                db.add(models.PriceRecord(
                    product_name=name, district=district,
                    market_name=f"{district} demo market",
                    price_per_unit=price, unit="kg", source=PRICE_SOURCE))
                new_price_records += 1
            db.commit()

        # Synthetic WEEKLY price history (2 years) for the forecasters:
        # 5 Bangladeshi hubs x 5 forecast crops x 104 weeks = 2600 rows.
        # Flagged is_synthetic=True / source="synthetic-demo" by the generator.
        hubs = [h for h in (get_hub(h) for h in BD_HUB_IDS) if h is not None]
        rows = synthetic.synthetic_rows(hubs=hubs, years=2, freq="W",
                                        end=TODAY.isoformat(), seed=7)
        history = prices.upsert_prices(db, rows)

        print("Demo data ready.")
        print(f"  users: {len(USERS)} total ({new_users} new)")
        print(f"  countries: {new_countries} new, regions: {new_regions} new")
        print(f"  crops: {new_crops} new")
        print(f"  farms: {new_farms} new, vehicles: {new_vehicles} new, offers: {new_offers} new")
        print(f"  products: {len(PRODUCTS)} total ({new_products} new)")
        print(f"  demands: {len(DEMANDS)} total ({new_demands} new)")
        print(f"  price records: {new_price_records} new (inserted only when table was empty)")
        print(f"  synthetic price history: {history['inserted']} inserted, "
              f"{history['skipped']} skipped ({len(rows)} rows generated)")
        print("  Demo logins (password Demo123! for all):")
        print("    farmer: farmer@farmmarket.demo (Rahim Uddin, Gazipur)")
        print("    buyer:  buyer@farmmarket.demo (Dhaka Fresh Mart, Dhaka)")
        print("    transporter: transporter@farmmarket.demo (Dhaka Cold Chain, Dhaka)")
        print("    admin:  admin@farmmarket.demo")
        print("  All prices are illustrative demo data, not live market rates.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
