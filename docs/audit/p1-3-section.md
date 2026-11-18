# FarmMarket audit — Phases 1–3 (structure/config, startup/infrastructure, database)

Auditor: Phase 1–3 subagent. Worktree: `~/workspace/farmmarket/audit-p13`,
branch `audit/p1-3`, base `163b4ee`. Venv: shared `~/workspace/farmmarket/.venv`
(Python 3.12.3); no packages installed into it. Test ports: backend 8011,
frontend dev 5111 (never 8000/5173).

Status labels: PASS / FAIL / BLOCKED / NOT IMPLEMENTED / PARTIAL.
A status of PASS means the auditor executed the check and verified the result.
Items that cannot be run in this VM are BLOCKED, never PASS.

> **Standing BLOCKED items in this VM:** live MySQL (no server — all DB work
> on throwaway SQLite), Docker build/run, live Gemini (no key), live
> OpenWeather (no key), live OSRM (no server), first PaaS deploy.
> Live-testable here (internet, no keys): Open-Meteo, Carto/OSM tiles,
> FAOSTAT bulk CSV.

---

## Phase 1 — Project structure & config

### 1.1 Layout (PASS)

- Backend: `backend/app/` — `main.py` (auth + core marketplace endpoints),
  `config.py`, `database.py`, `models.py`, `schemas.py`, `security.py`,
  `routers/` (18 modules, auto-discovered by `main.py` via `pkgutil`),
  `services/` (advisor, forecasting, gemini_assistant, logistics, matching,
  ortools_routing, price_labels, rag, rate_limit, scheduler,
  sklearn_forecast, torch_vision, twin, vision, audit, `datasources/`).
- Frontend: React 19 + TypeScript + Vite 6, `frontend/src/` with
  `pages/` (32), `components/`, `services/api.ts`, `i18n/`, `contexts/`.
- Alembic migrations: 4 revisions, linear chain
  `96249ebd1d8a` (initial) → `f6bbf6f95040` (sensor `is_simulated`) →
  `0b194a30001e` (chat) → `5a6223da9538` (price-observation note, head).
- `frontend-legacy/` (plain HTML/JS) is dead code kept in the repo; it is
  never served (`main.py` serves only `frontend/dist`, and only when built).
  Kept deliberately as history — not removed by this audit.
- `ai_services/computer_vision/` (train/evaluate/dataset/model) is the
  PyTorch training side; imported only by `test_torch_vision.py` and
  referenced by `services/torch_vision.py` docstrings. No trained model
  ships with the repo — no accuracy is claimed anywhere (verified by grep:
  no accuracy numbers in code/docs for the vision model).

### 1.2 Dependencies (PASS with notes)

- `backend/requirements.txt`: FastAPI 0.115.6, uvicorn 0.34.0, SQLAlchemy
  2.0.36, Alembic 1.20.1, PyMySQL 1.1.1, pydantic 2.10.4, python-jose,
  passlib+bcrypt 4.0.1, numpy/pandas/scikit-learn, Pillow, qrcode,
  httpx, APScheduler 3.11.0, anthropic, pytest. Optional extras split into
  `requirements-ml.txt` (torch), `requirements-ortools.txt`
  (ortools 9.14.6206 + protobuf 6.31.1, pinned tested combination),
  `requirements-prophet.txt`. All imports in `app/` resolve against the
  shared venv (verified: full `app.main` import + router auto-discovery
  succeeds — see P2).
- `frontend/package.json`: React 19, react-router-dom 7, axios, leaflet +
  react-leaflet 5, recharts, react-hook-form + zod + resolvers,
  @tanstack/react-query, vite-plugin-pwa, Vitest 3, Playwright 1.65.
  Every declared dependency is imported by at least one source file
  (checked: react-hook-form 3 files, zod 4, react-query 34, recharts 1,
  leaflet 5). No unused frontend dependency found.
- `anthropic` is a declared backend dependency used only by the legacy
  advisor service; the Krishi Bondhu assistant uses Gemini REST (httpx).
  Kept — the advisor endpoint is live, not dead code.

### 1.3 Environment variables (PARTIAL — 2 findings fixed, see F1/F2)

All env vars read by code were enumerated (grep over `os.getenv`,
`os.environ`, `config.env`) and compared with `backend/.env.example`:

| Var | In code | In .env.example | Notes |
|---|---|---|---|
| DATABASE_URL | yes | yes | MySQL primary, SQLite fallback |
| SECRET_KEY | yes | yes | prod fail-fast ≥32 chars |
| ACCESS_TOKEN_EXPIRE_MINUTES | yes (default 60) | yes — **was 1440** | **F1: fixed to 60** |
| REFRESH_TOKEN_EXPIRE_DAYS | yes (default 7) | yes | |
| ASSISTANT_RATE_LIMIT_PER_MIN | yes | yes | |
| UPLOAD_DIR | yes | yes | |
| ENVIRONMENT | yes | yes | |
| FRONTEND_ORIGINS | yes | yes | prod fail-closed, `*` refused |
| HUB_PROFILE | yes | yes | bangladesh / sub_saharan |
| ANTHROPIC_API_KEY / ADVISOR_MODEL | yes | yes | advisor only |
| GEMINI_API_KEY / GEMINI_MODEL / GEMINI_TIMEOUT_S | yes | yes | gemini-3.8-flash |
| OPENWEATHER_API_KEY | yes | yes | |
| OSRM_BASE_URL | yes | yes | |
| PUBLIC_BASE_URL | yes | yes | QR codes |
| MODEL_DIR | yes | yes | |
| SCHEDULER_ENABLED / _HOUR / _DAYS | yes | yes (commented) | off by default |
| SMTP_* | no (reserved) | yes (commented, marked NOT used) | no mailer exists |
| KNOWLEDGE_DIR | yes (`services/rag.py`) | **no** | **F2: added** |
| HTTPS_PROXY / https_proxy / HTTP_PROXY / http_proxy | yes (`datasources/sync.py`) | no | standard proxy vars; documented in F2 note, not added to example |
| PYTEST_CURRENT_TEST | yes (scheduler guard) | n/a | test-only |

### 1.4 Secrets (PASS)

- Grep over tracked files for API-key patterns (`AIza…`, `sk-ant-…`,
  `sk-proj-…`, `password = "…"`, `api_key = "…"`) found only demo/test
  values: `DEMO_PASSWORD = "Demo123!"` in `seed_demo.py` (public demo
  credentials, documented, seed refuses production) and test passwords in
  `backend/tests/`. No real keys in tracked files.
- `git log --all -p` grepped for the same patterns: no keys ever committed.
- `.gitignore` covers `.env`, `*.db`, `backend/uploads/`, `frontend/dist/`,
  `*.joblib` models, `node_modules/`, `__pycache__/`.
- `docker-compose.yml` contains demo-only MySQL credentials
  (`farmmarket_demo`), explicitly labelled demo-only. Acceptable for a
  local demo stack; production compose requires real values (fail-fast).
- `DEMO_SECRET_KEYS` blocklist in `main.py` + `security.py` production
  guard both reject known demo secrets.

### 1.5 Hardcoded URLs / base URLs (PASS)

- Frontend: `services/api.ts` uses relative `baseURL: "/api/v1"`; no
  hardcoded localhost/ports anywhere in `frontend/src`. Dev proxy in
  `vite.config.ts` points `/api` at `http://127.0.0.1:8000` (dev-only,
  correct for the documented dev setup).
- Backend: `PUBLIC_BASE_URL` default `http://127.0.0.1:8000` used only for
  QR-code URLs, overridable by env. Tile URLs (Carto primary, OSM
  fallback) are public keyless endpoints, verified live in P2.
- Assistant HTTP timeout is coherent: axios default 30s, assistant
  chat/test calls 90s (`ASSISTANT_HTTP_TIMEOUT_MS`), streaming bypasses
  axios via fetch (no cap). This matches the 2026-11-17 fix for the
  30s-cap bug.

### 1.6 CORS (PASS)

- `main.py:get_cors_origins()` — production fail-closed: unset origins →
  empty allow-list (same-origin only); `*` in production raises at
  startup. Development default is the two `:5500` live-server origins.
  `.env.example` lists the `:5173` dev origins. Verified by code
  inspection + existing `test_hardening.py` coverage (targeted run, P2).

### 1.7 Circular imports / broken imports (PASS)

- `python -c "from app.main import app"` succeeds in the worktree venv;
  all 18 router modules import via auto-discovery with no circular-import
  error. `python -m compileall` over `backend/app` passes (P2).

### 1.8 Duplicate / unused code (notes, no action)

- `models.Category`: table exists, no router/service references it — dead
  table (products carry `category_id` but nothing populates categories).
- `models.OrderItem`: explicitly documented as "future multi-item orders";
  unused by design.
- `models.Harvest`: no router/service references it — dead table.
- No duplicate endpoint paths found (router auto-discovery + `main.py`
  routes checked for path collisions during P2 boot — FastAPI would warn
  on duplicates; none observed).
- `database/schema.sql` only creates the database + charset; tables are
  created by SQLAlchemy/Alembic. Not drifted, just minimal by design.

### 1.9 `datetime.utcnow` deprecation (PARTIAL — fixed in audit scope)

- Python 3.12 deprecates `datetime.utcnow` (36 call sites across 10
  files). Values are naive datetimes stored in naive `DateTime` columns,
  so behaviour is unchanged, but the deprecation warnings will become
  errors in a future Python. **F3:** replaced with a behaviour-preserving
  `utcnow()` helper (naive UTC) in the audit's scope — `models.py`,
  `security.py`, `main.py` — and left service/router call sites for a
  follow-up (they are other phases' areas). `pytest.ini` already ignores
  `DeprecationWarning`, so tests were not failing on this.

### 1.10 Migration docstring drift (fixed, F4)

- `5a6223da9538_add_price_observations_note.py` docstring said
  "Revises: f6bbf6f95040" while `down_revision` is `0b194a30001e`
  (the real chain). Docstring corrected to match the code.

---

## Phase 2 — Startup & infrastructure

Backend booted for real with uvicorn on port 8011 (throwaway SQLite DB
`/tmp/p13/boot.db`, `SECRET_KEY` test value, `ENVIRONMENT=development`).
Frontend built with `npm ci` + `npm run build` (tsc + vite) and smoke-tested
with vite dev on port 5111.

| Check | Result |
|---|---|
| Backend boot (uvicorn 8011) | PASS — startup complete, no errors/tracebacks in log, scheduler correctly disabled |
| `GET /api/health` | PASS — `{"status":"ok","project":"FARMMARKET","db":"ok"}` |
| OpenAPI surface | PASS — 76 paths served |
| Register + login + create product + list products (live curl) | PASS — JWT issued, product created (id 1), searchable |
| Security headers | PASS — nosniff, DENY, strict-origin-when-cross-origin, Permissions-Policy present |
| CORS preflight, allowed origin (`http://localhost:5500`, the dev default) | PASS — 200 + `access-control-allow-origin` echoed |
| CORS preflight, disallowed origin (`http://localhost:5173` not in default allow-list; `http://evil.example.com`) | PASS — 400 / no ACAO header (fail-closed as designed) |
| Upload dir auto-creation | PASS — `/tmp/p13/uploads` created at startup; `/uploads/nonexistent.jpg` → 404 |
| `vite build` (tsc --noEmit + vite) | PASS — built in 13.31s; initial `index` chunk 490 kB, code-split route chunks, PWA precache 66 entries |
| SPA serving from backend (after build, restarted backend) | PASS — `/` 200 HTML with `#root`; `/marketplace` client-route fallback 200; `/assets/index-*.js` 200; `/sw.js` 200; `/api/v1/nope` still 404 (API wins over SPA fallback); `/%2E%2E` traversal → 404 |
| Vite dev server on 5111 | PASS — `http://localhost:5111/` 200 with `#root` (binds localhost/`::1`; `127.0.0.1` returns 000, normal vite behaviour, not a bug); `/api` proxy route exists (500 only because the proxy target `:8000` is intentionally not running in this audit) |
| MySQL connection | BLOCKED — no MySQL server in this VM. Config path verified by inspection + unit tests: `normalize_database_url()` rewrites bare `mysql://` → `mysql+pymysql://` + `charset=utf8mb4` and is shared by `app/database.py` and `alembic/env.py` (`test_database_url.py` targeted run, see below) |
| Docker build/run | BLOCKED — not attempted in this VM |
| Port conflicts / crashes / missing env vars | None observed |

## Phase 3 — Database audit

All DB work on throwaway SQLite files under `/tmp/p13/`; no production data
touched, no destructive operations.

### 3.1 Models reviewed (all 32 tables)

Every model in `backend/app/models.py` was read. PKs present on all tables;
FKs declared for all ID references except the two documented loose
references (see R4). Unique constraints: `users.email`, `batches.batch_code`,
`twin_devices.device_id`, `refresh_tokens.token_hash`,
`password_reset_tokens.token_hash`, `regions.hub_id`, `categories.name`,
`external_data_sources.name`, `crop_local_names(crop_id, language)`,
`price_observations(hub_id, crop, observed_on, source)`,
`forecast_snapshots(hub_id, crop, horizon)`, `ledger_blocks(batch_id, idx)`.
Verified live against the seeded DB via `PRAGMA index_list` /
`PRAGMA foreign_key_list` — inventory matches the models exactly.

### 3.2 Alembic (PARTIAL — 1 drift bug found and fixed, F5)

- Single head: `5a6223da9538` (`alembic heads`). Linear chain of 4
  revisions, no branches.
- `alembic upgrade head` on a throwaway SQLite DB: PASS (all 4 revisions
  applied; 33 tables incl. `alembic_version`; `price_observations.note`
  and `sensor_readings.is_simulated` present).
- `alembic downgrade -1` → `0b194a30001e`, then `upgrade head` again:
  PASS, back at head.
- `alembic check` (models vs migrated DB): **FAILED before fix** —
  `ix_chat_conversations_id` exists in models (`ChatConversation.id`
  has `index=True`) but migration `0b194a30001e` never created it.
  **F5:** new migration `a1b2c3d4e5f6` (see below) adds the missing index
  plus the missing FK indexes in F6. After the fix, `alembic check`
  passes (re-run recorded in the status table).
- Full `downgrade base` → `upgrade head` cycle also run after the fix:
  PASS (see status table).

### 3.3 Missing indexes on hot foreign keys (fixed, F6)

`PRAGMA index_list` on the seeded DB showed no index on:
`orders.buyer_id`, `orders.farmer_id`, `orders.product_id`,
`orders.transporter_id` (all filtered by `/orders/my`, dashboard, and
order-detail queries), `products.farmer_id` (farmer dashboard / my
listings), `demand_requests.buyer_id` (buyer demand listing). Every other
FK in the schema is indexed. **F6:** `index=True` added on those model
columns + the same new migration creates the indexes. (PK indexes are
redundant by nature but the codebase indexes PKs consistently, so the
`ix_chat_conversations_id` fix follows that convention rather than
removing `index=True` from the model.)

### 3.4 CRUD verification

CRUD for users, farms, listings, offers, orders, conversations, prices
and batches is exercised by the existing targeted test files (run in this
audit, see status table) plus live curl checks in P2 (register → product
create → product list) and the seed run below. No CRUD bug was found by
this audit beyond the index/drift items above.

**Post-fix targeted pytest (PARTIAL — environment aborted the run):**
`pytest tests/test_database_url.py tests/test_foundation.py
tests/test_hardening.py tests/test_messaging.py tests/test_manual_prices.py
tests/test_twin.py -q` — 61 tests passed, then the run aborted with exit
code 120 and no summary. Root cause is environmental, not the code: at
~07:54 UTC the sandbox began denying all regular-file writes by Python
(and Node) processes with `PermissionError: [Errno 1] Operation not
permitted` — `tempfile.gettempdir()` fails, pytest's capture cannot start
a new run, and the already-running uvicorn backend started returning 500
on DB-write endpoints (reads still fine). Shell builtins and coreutils
(bash redirects, dd, tee, cp) still write normally, and the same Python
binary wrote files fine earlier in this session (seed, alembic, live
smoke). The 61 passing tests cover `test_database_url` (6),
`test_foundation` (27), `test_hardening` (24) and the first 4 of
`test_messaging`. The remaining 29 tests (`test_messaging` 5,
`test_manual_prices` 12, `test_twin` 12) did NOT run — BLOCKED by the
environment, not failed. The single `E` in the output coincides with the
moment the sandbox restriction appeared and cannot be attributed to the
audit's changes; it must be re-run once the environment is restored.
No test failed on its merits at any point in this audit.

### 3.5 Money / quantities

- New tables (`offers`, `order_items`, `farms.area_acres`,
  `harvests.quantity_kg`, `vehicles.capacity_kg`) use
  `Numeric(12,2)` / `Numeric(10,2)` — correct Decimal precision.
- Legacy tables (`products`, `orders`, `demands`, `price_records`,
  `price_observations`, `batches.quantity_kg`) use `Float`, documented
  as intentional; order totals are `round(..., 2)` at write time.
  See R3 — flagged, not migrated.
- No currency mixing: seed products and price observations are all BDT;
  `Product.currency` defaults to `BDT`; countries carry their own
  currency (BDT/KES/NGN/GHS/TZS/UGX) with no cross-currency arithmetic
  anywhere in the code (grep verified: no conversion code exists).

### 3.6 Seed data (PASS)

`seed_demo.py` run twice against a throwaway SQLite DB:
- Run 1: 12 users, 6 countries, 10 regions, 11 crops (+11 Bangla names),
  2 farms, 1 vehicle, 1 offer, 10 products, 6 demands, 10 price records,
  2600 synthetic price observations inserted.
- Run 2: 0 new everywhere, 2600 observations skipped — idempotent.
- Countries correct: BD/Bangladesh/BDT/dhaka, GH/Ghana/GHS/accra,
  KE/Kenya/KES/nairobi, NG/Nigeria/NGN/lagos, TZ/Tanzania/TZS/
  dar_es_salaam, UG/Uganda/UGX/kampala.
- All products BDT + kg; all 2600 observations synthetic (`is_synthetic`
  = True), BDT, 5 BD hubs × 5 forecast crops; price records labelled
  "Illustrative demo data - replace with verified source".
- Production guard verified by code inspection (refuses without
  `--allow-production`); not executed against a production DB (none exists).

### 3.7 Datetime handling (PARTIAL)

- All timestamps are naive UTC `DateTime` columns with
  `datetime.utcnow` defaults; JWT expiry uses timezone-aware UTC
  (`security.py`) — the two are never compared against each other, so
  no naive/aware comparison bug exists. Refresh-token expiry compares
  naive DB values against naive `datetime.utcnow()` consistently.
- `datetime.utcnow` is deprecated in Python 3.12: see F3 (fixed in
  models/security/main; service/router sites left for owning phases, R2).
- `harvest_date` / `available_until` / `required_date` / `observed_on`
  are `Date` columns — correct for calendar dates.


---

## Status table

| # | Item | Status | Test performed | Issue | Fix |
|---|---|---|---|---|---|
| P1-01 | Project layout / architecture | PASS | Manual inspection of backend + frontend trees | — | — |
| P1-02 | Backend dependencies resolve | PASS | `python -c "from app.main import app"` + targeted pytest (see P2) | — | — |
| P1-03 | Frontend dependencies used | PASS | grep: every dep imported by ≥1 source file | — | — |
| P1-04 | Env vars vs `.env.example` | PARTIAL | Enumerated all `os.getenv`/`env()` reads, diffed vs example | F1: `ACCESS_TOKEN_EXPIRE_MINUTES=1440` contradicted 60-min hardening; F2: `KNOWLEDGE_DIR` undocumented | `.env.example`: 1440 → 60 with comment; added `KNOWLEDGE_DIR` |
| P1-05 | Secrets in tracked files / git history | PASS | grep tracked files + `git log --all -p` for key patterns | Only public demo/test credentials | — |
| P1-06 | Hardcoded URLs / base URLs | PASS | grep `frontend/src` + backend for localhost/ports | Dev proxy only, correct | — |
| P1-07 | CORS config | PASS | Code inspection + `test_hardening.py` targeted run | — | — |
| P1-08 | Circular / broken imports | PASS | Full app import + compileall | — | — |
| P1-09 | Duplicate / unused code | PASS | grep for Category/OrderItem/Harvest usage | 3 unused tables (Category, Harvest unused; OrderItem by design) | Reported only; no table deletion (needs migration + product decision) |
| P1-10 | `datetime.utcnow` deprecation | PARTIAL | grep: 36 sites, Python 3.12 | Deprecation warnings; naive-UTC semantics must be preserved | F3: `utcnow()` helper in config.py, used by models/security/main; service/router sites left for follow-up (R2) |
| P1-11 | Migration docstring drift | PASS | Read all 4 migrations | `5a6223da9538` docstring named wrong parent | F4: docstring fixed |
| P2-01 | Backend boots (uvicorn, port 8011) | PASS | Live boot ×3 (pre-fix, post-build, post-fix); no tracebacks in any log | Slow startup under CPU throttle only (VM load, not app) | — |
| P2-02 | `/api/health` + DB check | PASS | Live curl: `{"status":"ok","project":"FARMMARKET","db":"ok"}` | — | — |
| P2-03 | Frontend `vite build` passes | PASS | `npm ci` + `npm run build` (tsc + vite): built in 13.31s, PWA precache 66 entries | — | — |
| P2-04 | Frontend dev smoke (port 5111) + API proxy | PASS | `npx vite --port 5111`: `http://localhost:5111/` 200 with `#root`; `/api` proxy route exists (500 only because proxy target `:8000` intentionally not running) | vite binds localhost/`::1`, so `127.0.0.1:5111` returns 000 — normal vite behaviour, not a bug | — |
| P2-05 | Upload dir auto-creation + static serving | PASS | `/tmp/p13/uploads` created at startup; `/uploads/nonexistent.jpg` → 404 | — | — |
| P2-06 | MySQL config path | BLOCKED | Code inspection + `test_database_url.py` (targeted run) | No MySQL server in VM; cannot connect | `normalize_database_url` shared by app + Alembic, unit-tested |
| P2-07 | SPA fallback / static files | PASS | Live curl after build: `/` 200, `/marketplace` 200 fallback, `/assets/index-*.js` 200, `/sw.js` 200, `/api/v1/nope` 404, traversal 404 | — | — |
| P2-08 | CORS behaviour live | PASS | Live preflight: allowed origin 200 + ACAO; disallowed origin 400 / no ACAO | — | — |
| P2-09 | Docker build/run | BLOCKED | Not attempted in this VM | No Docker daemon here | — |
| P3-01 | Alembic single head | PASS | `alembic heads` → `a1b2c3d4e5f6` (head) after fix migration; linear chain of 5 | — | — |
| P3-02 | upgrade → downgrade → upgrade (throwaway SQLite) | PASS | `upgrade head` (5 revs) → `downgrade base` (5 revs) → `upgrade head` (5 revs), back at head; also `-1`/re-upgrade cycle; seed_demo.py runs clean on the migration-built DB and `create_all` is a no-op on it (schema equivalence) | — | — |
| P3-03 | Models vs migrations drift (`alembic check`) | PASS (after fix) | `alembic check` FAILED pre-fix (`ix_chat_conversations_id` missing), clean post-fix, clean after full cycle | F5: chat index drift | New migration `a1b2c3d4e5f6` adds it |
| P3-04 | CRUD: users/farms/listings/offers/orders/conversations/prices/batches | PARTIAL | Targeted pytest: 61 passed (database_url 6, foundation 27, hardening 24, messaging 4), then the run was aborted by a sandbox write block (see §3.4); remaining 29 tests NOT RUN — BLOCKED (environment), not failed. Live curl register→product→list passed pre- and post-fix | Sandbox denied Python file writes from ~07:54 UTC | Re-run the 29 remaining tests once the environment is restored; no code change needed on current evidence |
| P3-05 | Money/quantity Decimal precision | PASS | Inspected all models: new tables Numeric(12,2)/(10,2); legacy Float documented intentional (R3) | — | — |
| P3-06 | FKs, unique constraints, indexes, cascades | PASS (after fix) | `PRAGMA foreign_key_list`/`index_list` inventory on seeded DB vs models; all FKs/unique constraints present | F6: 6 hot FKs unindexed (orders×4, products.farmer_id, demands.buyer_id) | `index=True` in models + migration `a1b2c3d4e5f6`; all 7 indexes verified PRESENT |
| P3-07 | Seed data country/currency/unit correctness | PASS | `seed_demo.py` ×2 on throwaway DB: 6 countries/currencies correct, 10 regions, 11 crops, all products BDT/kg, 2600 synthetic BDT observations, idempotent rerun | — | — |
| P3-08 | Datetime handling | PARTIAL | Inspected all models + token flows: naive UTC consistent; JWT aware-UTC never compared to DB timestamps | `datetime.utcnow` deprecated (F3/R2) | F3 fixed in audit scope |

---

## Environment limitation (sandbox write block, ~07:54 UTC 17 Nov 2026)

Partway through this audit the sandbox began denying regular-file writes
by Python and Node processes (`PermissionError: [Errno 1] Operation not
permitted` on any `write()` to a regular file, on both tmpfs `/tmp` and
the home filesystem), while shell builtins and coreutils kept writing
normally. Effects on this audit:

- The post-fix targeted pytest run aborted after 61 passing tests (exit
  120, no summary); the remaining 29 tests are BLOCKED, not failed.
- A fresh pytest run cannot even start (`tempfile.gettempdir()` fails
  when pytest's capture tries to create a temp file).
- The already-running uvicorn backend returns 500 on DB-write endpoints
  (reads fine) — the restriction hits live processes too, not just new
  ones.
- All verification completed BEFORE ~07:54 stands: alembic cycles,
  `alembic check`, seed runs (incl. seed-on-migrated-DB), live boot/smoke
  tests, `vite build`, Vitest `api.test.ts` (4 passed).

This is a sandbox/environment fault, not a FarmMarket defect. The
coordinator should re-run the 29 remaining targeted tests (and the final
full suite) once the environment is restored. Nothing in this audit's
changes depends on the blocked tests for its own verification: the
migration/index changes are verified by `alembic check` + the full
upgrade/downgrade cycle + index presence checks, and the `utcnow` change
is verified by app import + live register/product flow.

## Findings fixed in this audit

- **F1** — `.env.example`: `ACCESS_TOKEN_EXPIRE_MINUTES` 1440 → 60, matching
  the 60-minute short-lived token hardening in `security.py` (comment there
  says "short-lived (60 min)"). A user copying the example as-is would have
  silently reverted the hardening to 24-hour tokens.
- **F2** — `.env.example`: documented `KNOWLEDGE_DIR` (RAG knowledge base
  override read by `services/rag.py`).
- **F3** — `datetime.utcnow` → naive-UTC `utcnow()` helper in `config.py`,
  used by `models.py`, `security.py`, `main.py` (behaviour-preserving;
  naive `DateTime` columns unchanged). Verified: app imports, live
  register/product flow works post-fix, no tracebacks.
- **F4** — Migration `5a6223da9538` docstring parent corrected
  (`f6bbf6f95040` → `0b194a30001e`).
- **F5** — Models/migrations drift: `ix_chat_conversations_id` existed in
  models but not in migration `0b194a30001e` (`alembic check` failed).
  Fixed by new migration `a1b2c3d4e5f6`; `alembic check` now clean.
- **F6** — Missing indexes on hot FKs (`orders.buyer_id/farmer_id/
  product_id/transporter_id`, `products.farmer_id`,
  `demand_requests.buyer_id`): `index=True` added in models +
  migration `a1b2c3d4e5f6`; all 7 indexes verified present after
  `upgrade head` on a throwaway DB.

## Findings reported, not fixed (need a decision / another phase)

- **R1** — `Category` and `Harvest` tables are unused (no router/service
  references). Either wire them up or drop them in a future migration;
  dropping tables is a product decision, not an audit fix.
- **R2** — `datetime.utcnow` remains in service/router files outside this
  audit's scope (`routers/conversations.py`, `services/datasources/sync.py`,
  `services/forecasting.py`, `services/sklearn_forecast.py`,
  `services/twin.py`, `services/vision.py`). Same helper should be applied
  there by the owning phases.
- **R3** — Legacy tables (`products`, `orders`, `price_records`,
  `price_observations`, `demands`) store money/quantities as `Float`,
  not `Numeric`. Documented as intentional ("legacy tables keep Float so
  existing behaviour is unchanged"). Float rounding is mitigated by
  `round(..., 2)` at write time in the order flow. A migration to
  `Numeric(12,2)` is a larger change; flagged, not attempted.
- **R4** — No FK from `SensorReading.device_id` (string) to
  `Device.device_id`, and `LedgerBlock.actor_user_id` is a plain integer
  with no FK to `users.id`. Both are by-design loose references (readings
  may arrive before device registration; ledger actors may be system
  events) but orphaned values are possible. Flagged, not changed.
- **R5** — No `ON DELETE` cascades / ORM delete cascades on most
  relationships (e.g. deleting a user would orphan products/orders).
  There is no user-delete endpoint, so this is latent, not live. Flagged.
