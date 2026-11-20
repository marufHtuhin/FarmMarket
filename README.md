# 🌾 FARMMARKET — Fair-Price Market Access for Farmers

[![Live Demo](https://img.shields.io/badge/Live_Demo-2E7D32?style=for-the-badge&logo=render&logoColor=white)](https://farmmarket-gdcm.onrender.com)
[![CI](https://github.com/marufHtuhin/FarmMarket/actions/workflows/ci.yml/badge.svg)](https://github.com/marufHtuhin/FarmMarket/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![MySQL](https://img.shields.io/badge/MySQL-8-4479A1?style=flat-square&logo=mysql&logoColor=white)](https://www.mysql.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

A responsive, bilingual (বাংলা / English) full-stack platform connecting
farmers directly with buyers, transporters and admins: fair-price listings,
demand matching, offers, price forecasts, photo-based produce grading, a
Bangla/English AI assistant, delivery optimisation, and a tamper-evident
Digital Twin batch ledger with QR verification.

Built by **Team Agronexis** for a hackathon. Primary market:
**Bangladesh (BDT)**. Also configured for Kenya (KES), Nigeria (NGN),
Ghana (GHS), Tanzania (TZS) and Uganda (UGX) — per-market pricing only,
currencies are never mixed.

## 🚀 Live Demo

**https://farmmarket-gdcm.onrender.com**

> The demo runs on free-tier hosting, so the first load can take ~30 seconds
> while the server wakes up. Demo accounts are listed in
> [Demo accounts](#demo-accounts) below — no sign-up needed to try it.

## 📸 Screenshots

| Homepage | Marketplace |
|---|---|
| ![FarmMarket homepage](docs/screenshots/homepage.png) | ![FarmMarket marketplace](docs/screenshots/marketplace.png) |

## 📑 Table of Contents

- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Quick Start](#-quick-start)
- [Demo Accounts](#-demo-accounts)
- [Demo Script (for judges)](#-demo-script-for-judges)
- [API Overview](#-api-overview)
- [Postman](#-postman)
- [Testing](#-testing)
- [Environment Variables](#-environment-variables)
- [Deployment](#-deployment)
- [Honesty and Limitations](#-honesty-and-limitations)
- [Team](#-team)
- [License](#-license)

## ✨ Features

### Farmer
- Register/login with district and upazila; manage farms.
- Publish produce listings with quantity, unit, asking price, district,
  harvest/availability dates, description and up to 5 photos.
- View buyer demands and explainable matching scores; receive and accept or
  reject offers (accepting creates an order with atomic stock reservation).
- Assign a transporter to an accepted order; track deliveries.
- Message buyers in-app about listings, offers and orders (no phone
  numbers are shown — chat only).
- Photo grade check, price forecasts, Krishi Bondhu assistant, Digital Twin
  batches with QR codes and simulated-sensor readings.

### Buyer
- Search produce by name and district; view product detail with photos.
- Make offers on listings; place direct orders; publish demands.
- Message farmers in-app about listings, offers and orders (no phone
  numbers are shown — chat only).
- View orders, offers and spending; verify any batch on the public page.

### Transporter
- Register with business name; manage vehicles (type, capacity, refrigeration).
- View assigned deliveries; update status (picked up → in transit →
  delivered) with a proof note.

### Admin
- Dashboard stats, user management + verification, audit logs, data-source
  monitoring (source, coverage, last sync, freshness), dispatch oversight.
- Enter daily market prices by hand (crop × hub × date) — the realtime
  price path; every price carries source + timestamp and a REAL/DEMO label.

### Intelligence
- **Price forecasting** — scikit-learn RandomForest (built in) and Prophet
  (optional) for five Bangladeshi hubs × five crops, back-tested against
  naive baselines; synthetic history is flagged `is_synthetic`. The
  forecaster trains on real ingested prices when enough exist, otherwise
  on the mixed series with a SYNTHETIC warning. Prices carry source +
  timestamp and a REAL/DEMO label; real prices older than 48h show a
  stale warning.
- **Photo grade check** — PyTorch transfer learning (ResNet18/MobileNetV3)
  with a scikit-learn RandomForest baseline; no trained model ships.
- **Krishi Bondhu assistant** — Google Gemini answering from its own knowledge,
  like the Gemini app; template fallback from the FarmMarket notes without
  a key. Replies stream token-by-token (SSE) with a non-stream fallback; admins can run a
  live probe at `POST /api/v1/assistant/test` and check
  `GET /api/v1/assistant/status` for the last error. Farmers can also send a
  crop photo (`POST /api/v1/assistant/chat-image`) for Gemini vision disease
  detection — structured cause/solution/prevention analysis, no key means a
  clear error, never a fabricated diagnosis.
- **Weather (past / present / future)** — Open-Meteo, no API key needed:
  past 7 days + current conditions + next 7 days per hub, from a single
  Forecast API call (`past_days=7`); every value carries source +
  timestamp, and an unreachable service shows a labelled unavailable state.
- **Logistics** — heuristic planner plus OR-Tools VRP (capacity, time
  windows, refrigeration) with baseline-vs-optimised comparison and stated
  emission factors; OSRM road routing when configured, haversine estimates
  otherwise (labelled).
- **Digital Twin** — per-batch hash chain with HMAC-signed sensor readings,
  Merkle sealing, threshold alerts, QR codes and a public verification page.
- **Auto-update** — an in-app scheduler (APScheduler, off by default,
  `SCHEDULER_ENABLED=true` in production) runs a daily read-only
  price-freshness check. FAOSTAT is annual-only and is never scheduled.

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19 + TypeScript + Vite, Tailwind CSS, React Router, TanStack Query, Recharts, Leaflet/OSM, PWA |
| Backend | Python 3.12 + FastAPI, SQLAlchemy 2 + Alembic |
| Database | MySQL 8 (SQLite fallback for the quick demo) |
| Auth | JWT access + refresh-token rotation, Passlib (bcrypt) |
| AI/ML | Prophet + scikit-learn forecasting; PyTorch + scikit-learn vision; Google Gemini assistant (template fallback, no key needed) |
| Logistics | OR-Tools VRP + OSRM (haversine fallback) |
| Deployment | Render + TiDB Cloud (live), Docker Compose (local), Caddy + VPS (alternative) |
| API Testing | Postman (86 requests, 15 folders) |
| Tests | pytest, Vitest, Playwright |

## 📁 Project Structure

```
FARMMARKET/
├── README.md / ARCHITECTURE.md / LIMITATIONS.md / TEST_REPORT.md
├── .github/workflows/ci.yml    # GitHub Actions CI (pytest subset + tsc/build/Vitest)
├── docker-compose.yml          # MySQL (host :3307) + API (:8000)
├── database/schema.sql         # CREATE DATABASE farmmarket_db (utf8mb4)
├── docs/                       # API_AND_DEMO, ERD, POSTMAN, knowledge/ (RAG docs)
├── postman/                    # 86-request collection
├── ai_services/computer_vision/# PyTorch train/eval pipeline
├── frontend/                   # React + TS + Vite (build -> frontend/dist)
│   ├── src/                    # 35 pages, components, i18n (EN + BN)
│   ├── e2e/                    # Playwright specs + serve script
│   └── dist/                   # built SPA (gitignored — build it with `npm run build`)
├── frontend-legacy/            # original vanilla-JS frontend (reference only)
└── backend/
    ├── Dockerfile              # multi-stage: node builds SPA, python serves it
    ├── .env.example
    ├── requirements.txt        # core; requirements-ml.txt (torch), requirements-ortools.txt
    ├── requirements-prophet.txt
    ├── seed_demo.py            # idempotent demo seed
    ├── alembic/                # migrations (6 revisions)
    ├── app/
    │   ├── main.py             # FastAPI app, router auto-discovery, serves SPA (auth endpoints live here)
    │   ├── config.py           # hub profiles (bangladesh / sub_saharan), crops
    │   ├── database.py         # SQLAlchemy engine/session (MySQL or SQLite)
    │   ├── models.py           # 33 tables
    │   ├── schemas.py / security.py
    │   ├── routers/            # 17 routers (catalog, farms, offers, ...)
    │   └── services/           # matching, forecasting, vision, assistant, rag,
    │                           # logistics, ortools_routing, twin, datasources
    ├── scripts/                # ingest_prices, fit_forecasts, train_vision,
    │                           # seed_data_sources, simulate_sensors
    └── tests/                  # pytest suite
```

## ⚡ Quick Start

### A — SQLite demo (fastest, no database server)

Windows PowerShell:

```powershell
cd FARMMARKET\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env: set DATABASE_URL=sqlite:///./farmmarket.db
python seed_demo.py
uvicorn app.main:app
```

Then open http://127.0.0.1:8000 — the API serves the built React app from
`frontend/dist`. A fresh clone does not include `dist` (gitignored), so
build it first:

```powershell
cd FARMMARKET\frontend
npm install
npm run build
```

For frontend development (hot reload), run `npm install` and `npm run dev`
in `frontend/` and open http://127.0.0.1:5173 (proxied to :8000).

macOS/Linux: same commands with `source venv/bin/activate` and
`cp .env.example .env`.

- Web app: http://127.0.0.1:8000
- API documentation: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

> The documented primary database is MySQL (see `.env.example`). SQLite is the
> quick-demo fallback only.

### B — MySQL via Docker Compose

```powershell
cd FARMMARKET
docker compose up --build
docker compose exec api python seed_demo.py
```

This starts MySQL 8 (`farmmarket_db`, utf8mb4, reachable on the host at
**127.0.0.1:3307**) and the API on http://127.0.0.1:8000. The container runs
`alembic upgrade head` before starting uvicorn.

Compose credentials are demo-only (`MYSQL_ROOT_PASSWORD` defaults to
`farmmarket_demo`); change them before any real use. To run MySQL without
Docker, create the database with `database/schema.sql` and set `DATABASE_URL`
in `backend/.env`:

```dotenv
DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@127.0.0.1:3307/farmmarket_db?charset=utf8mb4
```

Set a unique, randomly generated `SECRET_KEY` (at least 32 characters).

### Optional installs

```bash
pip install -r requirements-prophet.txt   # Prophet forecaster (optional)
pip install -r requirements-ortools.txt   # OR-Tools VRP optimiser (optional)
pip install --index-url https://download.pytorch.org/whl/cpu -r requirements-ml.txt  # PyTorch (CPU, optional)
```

Without OR-Tools, `/logistics/optimize` returns 503 with a clear message and
the UI falls back to the heuristic planner. Without torch, vision uses the
sklearn baseline.

## 👥 Demo Accounts

After running `python seed_demo.py` (password `Demo123!` for all):

| Role | Email | Name / Business | District |
|---|---|---|---|
| Farmer | farmer@farmmarket.demo | Rahim Uddin | Gazipur |
| Farmer | karima@farmmarket.demo | Karima Begum | Bogura |
| Farmer | abdul.malek@farmmarket.demo | Abdul Malek | Chattogram |
| Farmer | nasrin@farmmarket.demo | Nasrin Akter | Rajshahi |
| Farmer | jamal@farmmarket.demo | Jamal Hossain | Khulna |
| Farmer | sabina@farmmarket.demo | Sabina Yasmin | Sylhet |
| Farmer | rafiqul@farmmarket.demo | Rafiqul Islam | Cumilla |
| Buyer | buyer@farmmarket.demo | Dhaka Fresh Mart | Dhaka |
| Buyer | chattogram.bazar@farmmarket.demo | Chattogram Bazar Ltd | Chattogram |
| Buyer | rajshahi.agro@farmmarket.demo | Rajshahi Agro Traders | Rajshahi |
| Transporter | transporter@farmmarket.demo | Dhaka Cold Chain | Dhaka |
| Admin | admin@farmmarket.demo | Admin | Dhaka |

The seed also creates 10 product listings, 6 buyer demands, 10 price records,
2 farms, 1 vehicle, 1 offer and 2 years of weekly synthetic price history
(5 hubs × 5 crops × 104 weeks = 2,600 rows) for the forecasters. These are
public demo credentials — change/remove them before deployment.

## 🎬 Demo Script (for judges)

1. **Toggle Bangla** — open the web app, switch between বাংলা and English, and
   browse the seeded marketplace (10 listings across 8 districts).
2. **Offer + order** — log in as the buyer (`buyer@farmmarket.demo` /
   `Demo123!`), open a listing and make an offer.
3. **Farmer accepts + assigns** — log in as the farmer
   (`farmer@farmmarket.demo` / `Demo123!`), accept the offer from Offers
   (an order is created), open the order and assign the demo transporter.
4. **Transporter delivers** — log in as the transporter
   (`transporter@farmmarket.demo` / `Demo123!`), open Deliveries and move the
   order through picked up → in transit → delivered with a proof note.
5. **Digital Twin + QR** — as the farmer, create a batch on the Batches page,
   then run `python scripts/simulate_sensors.py --batch-code FM-... --seal`
   for SIMULATED cold-chain readings. Scan the batch QR (or open
   `/verify/FM-...`) to see the public verification page with the SIMULATED
   badge and the intact hash chain.
6. **Forecast + assistant** — open Prices for the Dhaka/tomato forecast chart
   (labelled illustrative demo data), then ask Krishi Bondhu a question in
   Bangla or English (template mode without a Gemini key).
7. **Logistics optimisation** — open Logistics, run an OR-Tools optimisation
   (if installed) and compare it with the heuristic baseline on the map.

## 🔌 API Overview

Base path: `/api/v1` (health at `/api/health`). Full interactive docs at
`/docs` when the server is running. See also `docs/API_AND_DEMO.md`.

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/api/health` | Public | Health check |
| POST | `/api/v1/auth/register` | Public | Create farmer/buyer/transporter account |
| POST | `/api/v1/auth/login` | Public | Access + refresh JWTs |
| POST | `/api/v1/auth/refresh` | Refresh token | Rotate tokens (reuse revokes all) |
| POST | `/api/v1/auth/logout` | JWT | Revoke refresh token |
| POST | `/api/v1/auth/forgot-password` | Public | Request reset token |
| POST | `/api/v1/auth/reset-password` | Token | Reset password |
| GET | `/api/v1/auth/me` | JWT | Current account |
| GET | `/api/v1/countries` | Public | 6 markets with hubs |
| GET | `/api/v1/crops` | Public | Crop catalogue (EN + BN names) |
| GET | `/api/v1/transporters` | Public | Transporter directory (no contact details) |
| GET | `/api/v1/farms` | Farmer | Own farms |
| POST | `/api/v1/farms` | Farmer | Create farm |
| GET | `/api/v1/products` | Public | Browse listings (`?search=&district=`) |
| POST | `/api/v1/products` | Farmer | List produce |
| POST | `/api/v1/products/{id}/images` | Farmer owner | Upload up to 5 photos |
| GET | `/api/v1/offers/my` | JWT | Own offers (incoming for farmers) |
| POST | `/api/v1/offers` | Buyer | Make an offer |
| PATCH | `/api/v1/offers/{id}` | Farmer owner | Accept/reject (accept creates an order) |
| GET | `/api/v1/orders/my` | JWT | Own orders |
| GET | `/api/v1/orders/{id}` | Order party | Order detail |
| PATCH | `/api/v1/orders/{id}/assign` | Farmer/admin | Assign a transporter |
| GET | `/api/v1/deliveries` | Transporter | Assigned deliveries |
| PATCH | `/api/v1/deliveries/{order_id}` | Transporter | Update delivery status |
| GET/POST | `/api/v1/vehicles` | Transporter | Vehicle management |
| GET | `/api/v1/forecast/sklearn?hub=&crop=&horizon=` | Public | scikit-learn forecast |
| GET | `/api/v1/forecast?hub=&crop=&horizon=` | Public | Prophet forecast (503 if not installed) |
| GET | `/api/v1/vision/status` | Public | Vision model availability |
| POST | `/api/v1/vision/assess` | Farmer | Grade a crop photo |
| POST | `/api/v1/assistant/chat` | JWT | Krishi Bondhu chat (Gemini or template) |
| POST | `/api/v1/assistant/chat/stream` | JWT | Streaming chat (SSE tokens; template fallback instant) |
| POST | `/api/v1/assistant/chat-image` | JWT | Crop-photo disease detection via Gemini vision (503 without a key, 502 on Gemini failure — never a fabricated diagnosis) |
| POST | `/api/v1/assistant/test` | Admin | One tiny live Gemini probe: ok/mode/latency/error (never the key) |
| GET | `/api/v1/assistant/status` | Admin | Gemini diagnostics: key configured, model, last error (never the key) |
| GET | `/api/v1/assistant/conversations` | JWT | Chat history |
| GET | `/api/v1/weather/{hub}` | Public | Open-Meteo past 7d + current + next 7d (no key needed) |
| POST | `/api/v1/conversations` | Farmer/buyer | Create-or-find a chat with the other party |
| GET | `/api/v1/conversations` | Farmer/buyer | My chats (unread counts + last message) |
| GET | `/api/v1/conversations/{id}/messages` | Participant | Thread messages |
| POST | `/api/v1/conversations/{id}/messages` | Participant | Send a message (rate-limited) |
| POST | `/api/v1/conversations/{id}/read` | Participant | Mark thread read |
| POST | `/api/v1/prices/manual` | Admin | Enter a daily market price (source + timestamp stored) |
| GET | `/api/v1/prices/manual` | Admin | Recent manual price entries |
| GET | `/api/v1/prices/latest` | Public | Latest price per hub × crop (source + REAL/DEMO label) |
| POST | `/api/v1/logistics/plan` | JWT | Heuristic route plan |
| POST | `/api/v1/logistics/optimize` | JWT | OR-Tools VRP (503 if not installed) |
| POST | `/api/v1/twin/batches` | Farmer | Create a Digital Twin batch |
| GET | `/api/v1/twin/batches/{code}/qr` | Public | Batch QR code (PNG) |
| GET | `/api/v1/twin/batches/{code}/alerts` | Farmer/admin | Threshold alerts |
| GET | `/api/v1/twin/public/{code}` | Public | Consumer batch view |
| GET | `/api/v1/admin/stats` | Admin | Platform statistics |
| GET | `/api/v1/admin/users` | Admin | User management |
| GET | `/api/v1/admin/data-sources` | Admin | Data-source status |
| POST | `/api/v1/admin/data-sources/{id}/sync` | Admin | Sync a data source |

## 📬 Postman

Import `postman/FarmMarket.postman_collection.json` (86 requests in 15
folders). Login requests save their JWTs and refresh tokens to collection
variables automatically; Create Farm/Offer/Vehicle/Batch save their ids.
Full instructions: [docs/POSTMAN.md](docs/POSTMAN.md).

## 🧪 Testing

```bash
cd backend && python -m pytest -q          # backend suite
cd frontend && npm run test                # Vitest + React Testing Library
cd frontend && npm run build               # tsc --noEmit + vite build
cd frontend && npm run test:e2e            # Playwright (needs `npm run build` first)
```

See [TEST_REPORT.md](TEST_REPORT.md) for the latest run results. GitHub
Actions runs the backend subset + frontend checks on every push and pull
request (`.github/workflows/ci.yml`); the full backend suite takes 55–70
minutes, so it runs locally before a release, not in CI.

## ⚙️ Environment Variables

Copy `backend/.env.example` to `backend/.env`. All integrations are optional:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | MySQL (primary) or SQLite fallback |
| `SECRET_KEY` | JWT signing (change in production) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | Token lifetimes |
| `ASSISTANT_RATE_LIMIT_PER_MIN` | Assistant rate limit (default 10) |
| `HUB_PROFILE` | `bangladesh` (default) or `sub_saharan` |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Krishi Bondhu assistant (default chain: gemini-3.8-flash → gemini-3.5-flash-lite) |
| `GEMINI_TIMEOUT_S` | Gemini call timeout in seconds (default 20, min 5) |
| `GEMINI_TEST_TIMEOUT_S` | Admin test-probe bound, fixed at 60s in code (not an env var) |
| `OPENWEATHER_API_KEY` | **Legacy, ignored** — weather now uses keyless Open-Meteo; delete the line if present |
| `SCHEDULER_ENABLED` | In-app daily price-freshness check (default false; true in production) |
| `OSRM_BASE_URL` | Road routing (else haversine estimates) |
| `PUBLIC_BASE_URL` | Base URL encoded in batch QR codes (if unset, the host of the incoming request is used — no localhost default) |
| `ANTHROPIC_API_KEY` | Legacy advisor LLM |
| `MODEL_DIR` | Where trained vision models live |

## 🚢 Deployment

**Live deployment (PaaS, free tier):** backend on
[Render](https://render.com) + MySQL on [TiDB Cloud](https://tidbcloud.com),
serving the built SPA itself. Full steps: [PAAS_DEPLOY.md](PAAS_DEPLOY.md).
The Render service auto-deploys on push to `main`.

**VPS alternative:** [`DEPLOY.md`](DEPLOY.md) walks through a production
stack step by step (domain + DNS, env file, `docker-compose.prod.yml` with
MySQL + API + Caddy automatic HTTPS, backups, updates, rollback):

```powershell
cp backend/.env.example .env   # at the REPO ROOT, then fill in DOMAIN,
                               # SECRET_KEY, MYSQL_ROOT_PASSWORD, FRONTEND_ORIGINS
docker compose -f docker-compose.prod.yml up -d --build
```

With `ENVIRONMENT=production` the app refuses to start on a demo/short
`SECRET_KEY`, a SQLite database, or a wildcard CORS origin, and
`seed_demo.py` refuses to run without `--allow-production` — demo accounts
must never land in a production database. The production compose file,
Dockerfile and Caddyfile are config-verified only in this repo (no Docker
here); verify them on the deployment machine first.

## ⚠️ Honesty and Limitations

This is a hackathon-grade build, not a production trading, payments or
logistics system. The short version:

- **Market prices / forecasts:** seeded records and synthetic history are
  illustrative demo data, flagged `is_synthetic`. No live Bangladesh
  market-price feed is connected; the DAM has no public API and none is
  invented — admin daily entry is the realtime path (see
  `docs/dam-prices.md`). Every price carries source + timestamp and a
  REAL/DEMO label; real prices older than 48h show a stale warning. Do not
  present sample records as current official rates.
- **Weather page:** Open-Meteo (keyless) past/present/future per hub; the
  separate OpenWeather integration still has no UI surface.
- **Matching:** a deterministic weighted heuristic, not a trained ML model
  and not a guarantee of a successful trade.
- **Image grading:** no trained model ships; the API returns a clear
  "model not trained" status until you train one. No accuracy is claimed.
- **Assistant:** Gemini answers from its own knowledge, like the Gemini app
  (stored price rows are still included so price questions use real
  records); without a key, clearly-labelled template answers built from
  the FarmMarket notes. It never invents prices, weather or facts.
- **Logistics:** haversine distances are straight-line estimates, not road
  distances. Emission factors and cold-chain rules are illustrative.
- **Digital Twin:** tamper-evident, not a public blockchain; head hashes are
  not anchored externally by default. Simulated sensor readings are labelled
  SIMULATED everywhere.
- **Payments, identity verification and dispute resolution:** not implemented.

Full details: [LIMITATIONS.md](LIMITATIONS.md). Architecture:
[ARCHITECTURE.md](ARCHITECTURE.md).

## 👥 Team

Built by **Team Agronexis** — Md. Maruf Hasan Tuhin.

## 📄 License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for
details.
