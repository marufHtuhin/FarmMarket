# FarmMarket backend

FastAPI + SQLAlchemy. MySQL 8 is the documented primary database; SQLite is
the quick-demo fallback. All commands run from this `backend/` directory.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # set DATABASE_URL + SECRET_KEY
python seed_demo.py         # demo users, products, farms, crops, vehicle, offer
uvicorn app.main:app --reload
```

Demo logins (password `Demo123!` for all): `farmer@farmmarket.demo`,
`buyer@farmmarket.demo`, `transporter@farmmarket.demo`,
`admin@farmmarket.demo`. All seeded prices are illustrative demo data.

## Tests

```bash
python -m pytest -q
```

Tests use a scratch SQLite DB in a temp dir (see `tests/conftest.py`).

## Database migrations (Alembic)

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
uses `app.models.Base.metadata` as its target. The initial migration covers
every table in the ERD (`../docs/ERD.md`).

## Auth notes

- `POST /api/v1/auth/register` accepts roles `farmer`, `buyer`, `transporter`.
  `role=admin` is rejected (400); admin accounts are created by seed only.
- `POST /api/v1/auth/login` returns an access token **and** a refresh token.
  `POST /api/v1/auth/refresh` rotates the refresh token; presenting an
  already-revoked token revokes **all** of the user's refresh tokens (theft
  detection) and returns 401. Refresh lifetime: `REFRESH_TOKEN_EXPIRE_DAYS`
  (default 7).
- `POST /api/v1/auth/forgot-password` always returns 200 (no user
  enumeration). **In non-production environments the response also includes
  the plaintext `reset_token`** so the flow can be tested without an email
  sender; in production it is never included and must be delivered
  out-of-band (email/SMS). Reset tokens are random values stored only as
  SHA-256 hashes, valid for 1 hour.

## Uploads

Listing images are stored under `UPLOAD_DIR` (default `backend/uploads/`,
`uploads/products/{product_id}/<uuid>.<ext>`) and served at `/uploads`.
At most 5 images per product, jpeg/png/webp only, max 5 MB each.

## Routers

`app/main.py` auto-discovers routers: every module in `app/routers/` with a
`router` attribute is included (sorted by module name). Add a new API area
by dropping a module into that package — no edit to `main.py` is needed.
