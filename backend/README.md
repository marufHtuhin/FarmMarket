# FarmMarket API — Backend

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy_2-D71F00?style=flat-square&logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![MySQL](https://img.shields.io/badge/MySQL-8-4479A1?style=flat-square&logo=mysql&logoColor=white)](https://www.mysql.com/)

FastAPI + SQLAlchemy 2 backend for FarmMarket — the fair-price agricultural
marketplace. Serves the REST API (`/api/v1`), the built React SPA, and
uploaded listing images. MySQL 8 is the documented primary database; SQLite
is the quick-demo fallback.

> **New here?** Start with the [project README](../README.md) — it covers
> the product, the live demo, the full feature list and the hackathon demo
> script. This file is the backend reference.

## Contents

- [Quick start](#quick-start)
- [Project layout](#project-layout)
- [API docs](#api-docs)
- [Database & migrations](#database--migrations)
- [Auth notes](#auth-notes)
- [Uploads](#uploads)
- [Routers](#routers)
- [Environment variables](#environment-variables)
- [Testing](#testing)
- [Deployment](#deployment)

## Quick start

All commands run from this `backend/` directory.

```bash
pip install -r requirements.txt
cp .env.example .env        # set DATABASE_URL + SECRET_KEY
python seed_demo.py         # demo users, products, farms, crops, vehicle, offer
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

Demo logins (password `Demo123!` for all): `farmer@farmmarket.demo`,
`buyer@farmmarket.demo`, `transporter@farmmarket.demo`,
`admin@farmmarket.demo`. All seeded prices are illustrative demo data.
The full demo-account table is in the [project README](../README.md).

## Project layout

```
backend/
├── Dockerfile              # multi-stage: node builds the SPA, python serves it
├── .env.example            # every variable, documented
├── requirements.txt        # core; requirements-ml.txt (torch), requirements-ortools.txt,
│                           # requirements-prophet.txt (all optional)
├── seed_demo.py            # idempotent demo seed (refuses production without --allow-production)
├── alembic/                # migrations (6 revisions)
├── app/
│   ├── main.py             # FastAPI app (FARMMARKET API v1.1.0), router auto-discovery,
│   │                       # serves the SPA + /uploads; auth endpoints live here
│   ├── config.py           # hub profiles (bangladesh / sub_saharan), crops, settings
│   ├── database.py         # SQLAlchemy engine/session (MySQL or SQLite)
│   ├── models.py           # 33 tables
│   ├── schemas.py          # Pydantic request/response schemas
│   ├── security.py         # password hashing, JWTs, token hashing
│   ├── routers/            # 17 routers (catalog, farms, offers, ...)
│   └── services/           # matching, forecasting, vision, assistant, rag,
│                           # logistics, ortools_routing, twin, datasources, mailer
├── scripts/                # ingest_prices, fit_forecasts, train_vision,
│                           # seed_data_sources, simulate_sensors
└── tests/                  # pytest suite (scratch SQLite DB in a temp dir)
```

## API docs

With the server running, the full interactive reference is at `/docs`
(Swagger UI) and `/redoc`. The endpoint table in the
[project README](../README.md#api-overview) is the short version; the
Postman collection (`../postman/`, 86 requests in 15 folders) is the
executable version — see [docs/POSTMAN.md](../docs/POSTMAN.md).

## Database & migrations

`app/main.py` still calls `Base.metadata.create_all(bind=engine)` — tests and
the quick SQLite demo rely on it. For real deployments (MySQL, or any
database with data worth keeping), use Alembic instead:

```bash
# Create a migration after changing app/models.py
alembic revision --autogenerate -m "describe the change"

# Apply / roll back
alembic upgrade head
alembic downgrade -1
```

`alembic/env.py` reads `DATABASE_URL` from the environment (or `.env`) and
uses `app.models.Base.metadata` as its target. There are 6 revisions; the
initial migration covers the base schema from the ERD (`../docs/ERD.md`).
The Docker image and the Render deploy run `alembic upgrade head` on start.

## Auth notes

- `POST /api/v1/auth/register` accepts roles `farmer`, `buyer`, `transporter`.
  `role=admin` is rejected (400); admin accounts are created by seed only.
- `POST /api/v1/auth/login` returns an access token **and** a refresh token.
  `POST /api/v1/auth/refresh` rotates the refresh token; presenting an
  already-revoked token revokes **all** of the user's refresh tokens (theft
  detection) and returns 401. Refresh lifetime: `REFRESH_TOKEN_EXPIRE_DAYS`
  (default 7).
- `POST /api/v1/auth/forgot-password` always returns 200 (no user
  enumeration). The plaintext `reset_token` is returned in the response
  **only when `ENVIRONMENT` is not `production` AND no mailer is
  configured** — so the flow can be tested without an email sender. As soon
  as a mailer is configured (even in development), the inbox is the only
  delivery, exactly like production. Reset tokens are random values stored
  only as SHA-256 hashes, valid for 1 hour, rate-limited to 5/min per IP.
- Email verification: `POST /api/v1/auth/verify-email` /
  `/resend-verification`. Login stays allowed while unverified; the web app
  shows a banner instead of blocking.

## Uploads

Listing images are stored under `UPLOAD_DIR` (default `backend/uploads/`,
`uploads/products/{product_id}/<uuid>.<ext>`) and served at `/uploads`.
At most 5 images per product, jpeg/png/webp only, max 5 MB each.

## Routers

`app/main.py` auto-discovers routers: every module in `app/routers/` with a
`router` attribute is included (sorted by module name). Add a new API area
by dropping a module into that package — no edit to `main.py` is needed.
Auth endpoints (`/api/v1/auth/*`) are the exception: they live directly in
`app/main.py`.

## Environment variables

Copy `.env.example` to `.env`. Every variable is documented there; the
[project README](../README.md#environment-variables) has the table. The
only required values for a local run are `DATABASE_URL` and `SECRET_KEY`
(≥32 characters; production refuses to start without a long, non-demo key).
All integrations are optional — the API runs fully without keys (the
assistant falls back to labelled template answers, weather stays keyless
via Open-Meteo).

## Testing

```bash
python -m pytest -q
```

Tests use a scratch SQLite DB in a temp dir (see `tests/conftest.py`), so
they never touch your dev database. Latest results:
[TEST_REPORT.md](../TEST_REPORT.md).

## Deployment

The `Dockerfile` builds the frontend (`npm run build`) and serves the SPA
plus the API from one image; it runs `alembic upgrade head` before starting
uvicorn on `$PORT`. The live deployment is Render + TiDB Cloud — see
[PAAS_DEPLOY.md](../PAAS_DEPLOY.md). With `ENVIRONMENT=production` the app
refuses to start on a demo/short `SECRET_KEY`, a SQLite database, or a
wildcard CORS origin.
