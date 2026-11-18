# FarmMarket — Postman Guide

Collection: `postman/FarmMarket.postman_collection.json` (Postman Collection Format v2.1).
86 requests in 15 folders: Health, Auth, Marketplace, Orders, Forecast (Prophet +
scikit-learn), Vision (photo grading), Advisor (Krishi Bondhu), Logistics, Digital Twin,
Farms & Offers, Deliveries & Vehicles, Assistant & Data Sources, Admin, Messaging,
Weather & Prices.

## Import

1. In Postman, choose **Import** → select `postman/FarmMarket.postman_collection.json`.
2. Start the API first (from `backend/`): `uvicorn app.main:app --reload`
   (or `docker compose up --build` from the repo root).
3. Seed the demo data first (`python seed_demo.py` from `backend/`), so the demo
   logins below exist.

## Variables (filled in automatically as you run the collection)

| Variable | Purpose |
|---|---|
| `base_url` | Default `http://127.0.0.1:8000`. Change it if the API runs elsewhere. |
| `farmer_token` / `farmer_refresh_token` | Saved by **Auth → Login farmer** (test script). |
| `buyer_token` / `buyer_refresh_token` | Saved by **Auth → Login buyer** (test script). |
| `transporter_token` / `admin_token` | Saved by **Auth → Login transporter / Login admin**. |
| `reset_token` | Saved by **Auth → Forgot password** (dev mode only). |
| `verification_token` | Saved by **Auth → Register farmer** (dev mode only). |
| `product_id` | Saved by **Marketplace → Create product**; used by Update/Delete. |
| `order_id` | Saved by **Orders → Place order**; used by Accept/Complete/Cancel. |
| `farm_id` / `offer_id` / `vehicle_id` | Saved by the Farms & Offers / Deliveries & Vehicles requests. |
| `conversation_id` | Saved by **Assistant & Data Sources → Chat with Krishi Bondhu**. |
| `batch_code` | Saved by **Digital Twin → Create batch**; used by the twin flow. |
| `device_id` | Saved by **Digital Twin → Register sensor device**. |

Two role tokens are used (instead of a single `{{token}}`) because farmer and buyer
endpoints require different roles — with one token you would have to keep re-logging
in. The collection authenticates with `{{farmer_token}}` by default; buyer requests
override it with `{{buyer_token}}`.

## Auth

- **Farmer token** — Create/Update/Delete Product, Vision Assess, Twin Create Batch /
  Devices / Seal / Anchor, Accept + Complete Order.
- **Buyer token** — Create Demand, Place Order, Cancel Order.
- **Any logged-in token** — Me, List Demands, Matches, My Orders, Notifications,
  Dashboard, Advisor Advice, Logistics Plan.
- **Public** — Health, List Products, Prices, Forecast Hubs/Overview/Forecast,
  Vision Status, Advisor Languages, Twin Public Lookup, Twin Verify.
- **Email verification** — **Auth → Verify email** confirms the address with
  the `verification_token` (in dev, saved automatically by **Register
  farmer**; in production the token arrives only by email, so SMTP must be
  configured). **Auth → Resend verification** (any logged-in token) sends a
  fresh verification link. Login still works for unverified users.

## Suggested run order

1. **Health → Health check** — confirms the API is up.
2. **Auth → Login farmer** (`farmer@farmmarket.demo` / `Demo123!`) and
   **Auth → Login buyer** (`buyer@farmmarket.demo` / `Demo123!`). Both test scripts
   save their JWTs automatically — no copy-pasting.
3. **Marketplace** — List Products, Create Product (saves `product_id`), Update/Delete
   Product, List Demands, Create Demand, Smart Matches, Price Records.
4. **Orders** — Place Order (saves `order_id`), My Orders, Accept Order (farmer),
   Complete Order (farmer, only after accept). A buyer can Cancel Order only while
   it is still pending; reserved stock is returned on cancel/reject. Then
   Notifications and Dashboard.
5. **Forecast** — Hubs, Forecast Overview, Prophet Forecast, scikit-learn Forecast,
   Hub Context.
6. **Vision** — Vision Status, then Assess Photo (see the 503 note below).
7. **Advisor** — Supported Languages, Planting Advice (Bangla).
8. **Logistics** — Plan Dispatch (Dhaka depot → Gazipur, Khulna).
9. **Digital Twin** — Create Batch (saves `batch_code`), My Batches, Add Batch Event,
   Register Sensor Device (saves `device_id`), Submit Sensor Reading, Seal Batch,
   Anchor Batch, Verify Batch, Public Batch View.

## Notes

- **Logins save their tokens automatically.** If a request returns 401, re-run the
  matching Login (tokens expire — default lifetime is 1440 minutes).
- **Vision Assess returns 503 without a trained model.** No trained model ships with
  the repo; train one with `scripts/train_vision.py` first. Attach a real image file
  to the `image` form-data field before sending.
- **Prophet Forecast returns 503 if Prophet is not installed.** Prophet is an optional
  dependency (`requirements-prophet.txt`). Use **scikit-learn Forecast** instead — same
  params (`hub`, `crop`, `horizon`) and response shape, no extra install needed.
- **Submit Sensor Reading needs an HMAC signature.** See the device-signing formula in
  the README (`signature = hex(HMAC-SHA256(device_key, ...))`); the `device_key`
  comes from Register Sensor Device. An invalid signature returns 401.
- **Forecasts use synthetic demo history** unless you ingest real prices
  (`scripts/ingest_prices.py --csv` or `--faostat`). Synthetic data is flagged
  in every forecast response; treat it as pipeline demo data, not market advice.
- All seeded prices are **illustrative demo data**, not live market rates.
