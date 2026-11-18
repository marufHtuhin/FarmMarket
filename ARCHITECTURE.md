# FarmMarket — Architecture

A full-stack platform connecting farmers, buyers, transporters and admins
across Bangladesh (primary) and five sub-Saharan markets (Kenya, Nigeria,
Ghana, Tanzania, Uganda). This document describes the system as built. For
what is *not* verified or needs real keys/datasets, see [LIMITATIONS.md](LIMITATIONS.md).

## System overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Browser (React SPA, PWA)  — http://127.0.0.1:5173 (dev)        │
│  React 19 + TypeScript + Vite + Tailwind + React Router +       │
│  TanStack Query + Recharts + Leaflet/OSM + vite-plugin-pwa      │
└──────────────────────────────┬──────────────────────────────────┘
                               │ /api/v1 (JSON, JWT)
┌──────────────────────────────▼──────────────────────────────────┐
│ FastAPI (Python 3.12)  — http://127.0.0.1:8000                  │
│  Routers (auto-discovered from app/routers/)                    │
│  Services: matching, forecasting, vision, advisor, assistant,   │
│  rag, logistics, ortools_routing, twin, datasources             │
│  SQLAlchemy 2 ORM + Alembic migrations                          │
│  Serves the built SPA (frontend/dist) in production             │
└───────┬──────────────────┬──────────────────┬───────────────────┘
        │                  │                  │
   MySQL 8 (3307)     SQLite fallback    Local files
   (compose)          (demo/dev)         uploads/, models/
```

Optional integrations (all degrade to labelled fallbacks when absent):

- **Google Gemini** (`GEMINI_API_KEY`) — Krishi Bondhu assistant answers.
- **Open-Meteo** (no key) — hub weather in forecasts, logistics derating,
  advisor context and the Weather page. (OpenWeatherMap /
  `OPENWEATHER_API_KEY` is legacy and ignored since 2026-11-17.)
- **OSRM** (`OSRM_BASE_URL`) — road distances for routing; otherwise
  haversine estimates, labelled as such.
- **Anthropic** (`ANTHROPIC_API_KEY`) — legacy advisor LLM.
- **World Bank API** — population/indicator sync for data-source status.
- **OR-Tools** (`requirements-ortools.txt`) — VRP optimisation.
- **PyTorch** (`requirements-ml.txt`) — transfer-learning vision models.

## Frontend (`frontend/`)

Vite + React 19 + TypeScript. `npm run dev` serves on :5173 with a proxy to
:8000; `npm run build` runs `tsc` + `vite build` into `frontend/dist`, which
FastAPI serves in production (same origin, so no CORS in production).

| Area | Implementation |
|---|---|
| Routing | React Router, 30 pages; `ProtectedRoute` guards by role |
| Data | TanStack Query; all calls in `src/services/api.ts` |
| i18n | `src/i18n/` — 602 keys/language (BN/EN), `fm_lang` in localStorage; legacy translations ported verbatim from `frontend-legacy/app.js` |
| Design | Warm fresh-bazar system: cream `#FBF7EF`, forest `#0C3B2E`, leaf `#1E7A4C`, marigold `#F2A33C`; Sora + Hind Siliguri |
| Layout | Desktop sidebar + mobile bottom nav; checked at 360–1440 px |
| Charts | Recharts (forecast, sensor temperature) |
| Maps | Leaflet + OpenStreetMap (hubs, logistics routes) |
| PWA | `vite-plugin-pwa`, precaches the app shell; installable |

Pages: landing, about, how-it-works, marketplace + product detail,
login/register/forgot/reset, per-role dashboards, farms, listings (multi-image
upload), offers, orders + order detail, matches, prices, quality, assistant,
logistics, batches + batch detail, public `/verify/:code`, deliveries,
vehicles, admin (dashboard/users/data-sources/audit-logs), notifications,
profile, 404. No dead buttons: every control is wired to the API; where a
backend capability is unavailable the UI says so (e.g. vision "not trained",
logistics falls back from `/optimize` to `/plan` on 404/503 with a note).

## Backend (`backend/app/`)

FastAPI, SQLAlchemy 2, Alembic. Routers are **auto-discovered** from
`app/routers/` (pkgutil scan in `main.py`), so a new feature is a new router
file — no `main.py` edit needed. `main.py` also hosts a few endpoints that
predate the router split (`/api/v1/transporters` directory, `/api/v1/orders/{id}`).

### Routers

| Router | Endpoints |
|---|---|
| `auth.py` | register, login, logout, refresh, me, forgot/reset password |
| `catalog.py` | countries, regions, crops |
| `products.py` | listings CRUD + multi-image upload |
| `products_ext.py` | product detail extensions |
| `farms.py` | farm CRUD (farmer-owned) |
| `offers.py` | buyer offers, accept/reject/cancel |
| `orders.py` | orders, order items, status |
| `deliveries.py` | assign transporter, delivery state machine |
| `vehicles.py` | transporter vehicle CRUD |
| `demands.py`, `matches.py` | buyer demands, explainable matching |
| `forecast.py` | Prophet + scikit-learn forecasts, hubs |
| `vision.py` | photo grading (sklearn + optional torch) |
| `advisor.py` | legacy template/Anthropic advisor |
| `assistant.py` | Gemini chat (template fallback uses RAG notes), photo disease detection via Gemini vision (`/chat-image`, no template fallback), conversation history |
| `data_sources.py` | admin data-source status + sync |
| `logistics.py` | heuristic plan + OR-Tools optimize |
| `twin.py` | batches, events, devices, readings, seal, verify, QR, alerts, public view |
| `admin.py` | stats, users, verification, audit logs |
| `notifications.py`, `dashboard.py` | notifications, role dashboards |

### Services

| Service | Role |
|---|---|
| `matching.py` | Deterministic weighted supply/demand scoring (not ML) |
| `forecasting.py`, `sklearn_forecast.py` | Prophet + RandomForest price forecasts, back-tested vs naive baselines |
| `vision.py`, `torch_vision.py` | sklearn RandomForest baseline; optional PyTorch inference |
| `advisor.py`, `gemini_assistant.py`, `rag.py` | Template/Anthropic advisor; Gemini chat; TF-IDF/cosine RAG over `docs/knowledge/` |
| `logistics.py`, `ortools_routing.py` | Heuristic planner; OR-Tools VRP (capacity, time windows, refrigeration) |
| `twin.py` | Hash-chained ledger, HMAC sensor ingestion, Merkle sealing, alerts |
| `datasources.py` | FAOSTAT/World Bank/OpenWeather adapters |

### Data model

30 tables (see [docs/ERD.md](docs/ERD.md)). Key entities:

- **Identity**: `User` (roles farmer/buyer/transporter/admin),
  `RefreshToken` (rotation + reuse detection), `PasswordResetToken`,
  `Farm`, `Vehicle`, `AuditLog`.
- **Marketplace**: `Product`, `ListingImage`, `Demand`, `Offer`, `Order`,
  `OrderItem`, `Crop`, `CropLocalName`, `Harvest`, `Country`, `Region`.
- **Intelligence**: `PriceRecord`, `PriceObservation`, `Forecast`,
  `Conversation`, `Message`, `ExternalDataSource`.
- **Twin**: `Batch`, `Device`, `SensorReading`, `LedgerBlock`, `Anchor`.

Money/quantities use `DECIMAL` on new tables; legacy float columns are kept
working for backward compatibility (see LIMITATIONS.md).

### Auth & security

- JWT access tokens (default 1440 min) + **refresh-token rotation**: each
  refresh issues a new refresh token and invalidates the old one; reuse of a
  rotated token revokes all tokens for the user (theft detection).
- Password reset via single-use tokens (dev responses include the token;
  production sends it by email via the stdlib SMTP mailer — `SMTP_*` must
  be configured). Registration confirmation uses the same mailer
  (24h verification tokens; `User.email_verified`).
- Passlib (bcrypt) password hashing; role checks via `require_role(...)`.
- Uploads validated (type jpeg/png/webp, ≤5 MB, ≤5 files) and served from
  `backend/uploads/`.
- Assistant is rate-limited (10 messages/user/minute, configurable).

## AI / ML

- **Forecasting**: scikit-learn RandomForest is the reliable forecaster on
  demo data; Prophet is optional (`requirements-prophet.txt`). Every forecast
  is back-tested against naive baselines and marked `reliable: false` when it
  does not beat them. Synthetic history is flagged `is_synthetic`.
- **Vision**: `ai_services/computer_vision/` (train.py, dataset.py, model.py,
  evaluate.py) — ResNet18/MobileNetV3 transfer learning with train/val split,
  augmentation, class balancing and per-class precision/recall + confusion
  matrix. No trained model ships. Inference tries torch first per task and
  falls back to the sklearn baseline; when neither exists the API returns a
  clear "model not trained" status (never fake accuracy).
- **Assistant**: Gemini over plain HTTPS REST (httpx, key from env only —
  the `google-generativeai` SDK's gRPC transport hung indefinitely from
  the user's network, so it was removed 2026-11-16), answering from its
  own knowledge like the Gemini app (stored price rows are still included
  for price questions; the RAG notes were removed from the Gemini prompt
  2026-11-17 at the user's request). Template fallback built from the
  notes (RAG-lite TF-IDF/cosine over `docs/knowledge/`) when no key is
  set or Gemini fails. Answers never invent prices, weather or facts.
  Photo disease detection (`POST /api/v1/assistant/chat-image`) sends a
  crop photo to Gemini vision over the same REST transport and returns a
  structured cause/solution/prevention analysis — with no template
  fallback: no key is a 503 and a Gemini failure is a 502, never a
  fabricated diagnosis.

## Logistics

Two solvers behind one scenario schema:

- `POST /logistics/plan` — heuristic planner (always available).
- `POST /logistics/optimize` — OR-Tools VRP: capacity, hard time windows,
  refrigeration, weighted objective (time/distance/CO₂e), baseline
  nearest-neighbour comparison. Returns 503 with a clear message when
  OR-Tools is not installed; 422 on infeasible input.

Distances come from OSRM when `OSRM_BASE_URL` is set, otherwise haversine
(straight-line) estimates labelled `distance_basis: "haversine_estimate"`.
Emission factors are illustrative (0.20 empty / 0.32 full kg/km, 1.5 kg/h
reefer) and stated in every response.

## Digital Twin

Per-batch hash-chained ledger (`LedgerBlock`): every event links to the
previous block's hash; sensor readings are HMAC-signed by registered devices,
sealed in batches with Merkle roots, and verified by `verify_chain`. It is
**tamper-evident, not a public blockchain** — head hashes are not anchored to
an external ledger unless an `AnchorProvider` is configured, and the API says
so.

- QR code per batch (`GET /twin/batches/{code}/qr`, PNG) encoding
  `{PUBLIC_BASE_URL}/verify/{code}` — or the host of the incoming request
  when `PUBLIC_BASE_URL` is unset (there is no localhost default, so a
  scanned QR never points at the phone's own localhost); the public page shows crop, batch,
  harvest, grade, timeline, sensor history and chain status — no private
  farmer/buyer data.
- Threshold alerts (`GET /twin/batches/{code}/alerts`) use per-crop cold-chain
  rules with documented illustrative generic defaults (0–30 °C, RH 40–95%).
- `scripts/simulate_sensors.py` posts **SIMULATED** readings through the real
  HMAC device API; they are stored with `is_simulated=True` and labelled
  SIMULATED in the UI and API. Never present them as real measurements.

## Data sources

FAOSTAT (bulk CSV), World Bank (live API sync) and OpenWeatherMap adapters
live in `services/datasources.py`; admin status/sync endpoints in
`routers/data_sources.py` and the admin data-sources page show source,
coverage, last sync and freshness. Bangladesh DAM has **no public API** that
we found — it is documented as `not_configured` with an empty endpoint and no
endpoint is invented.

## Configuration

All settings via environment (see `backend/.env.example`): `DATABASE_URL`,
`SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`,
`ASSISTANT_RATE_LIMIT_PER_MIN`, `UPLOAD_DIR`, `HUB_PROFILE`
(bangladesh/sub_saharan), `GEMINI_API_KEY`,
`OSRM_BASE_URL`, `PUBLIC_BASE_URL`, `MODEL_DIR`, `ANTHROPIC_API_KEY`.

A startup sanitizer in `backend/app/__init__.py` strips bracketed IPv6
entries from `NO_PROXY` (httpx cannot parse `[::1]`-style entries).

## Deployment

- **Local dev**: `uvicorn app.main:app` (backend, :8000) + `npm run dev`
  (frontend, :5173, proxied to :8000). SQLite fallback needs no database.
- **Docker Compose**: multi-stage `backend/Dockerfile` (node builds the React
  app, python serves it); `docker-compose.yml` runs MySQL 8 on host port 3307
  + the API on :8000; the container runs `alembic upgrade head` before
  starting uvicorn.
- **Migrations**: Alembic (`backend/alembic/`), two revisions — initial schema
  (30 tables) + `sensor_readings.is_simulated`. `Base.metadata.create_all`
  is kept in `main.py` so tests and the SQLite demo work without migrations.

## Testing

See [TEST_REPORT.md](TEST_REPORT.md): pytest (backend), Vitest + React Testing
Library (frontend), Playwright E2E (core marketplace flow + smoke specs),
`tsc --noEmit` and `vite build`.
