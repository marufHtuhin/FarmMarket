# FarmMarket — Test Report

Last full run: **17 Nov 2026**, in the build VM (Linux, Python 3.12.3,
Node v24.22.1). All tests run on SQLite; MySQL/Docker were not available in
this VM (see "Not verified"). This run covers the feature batch on top of
the production-hardened build: farmer-buyer messaging, Open-Meteo weather,
admin manual prices + REAL/DEMO labelling, Gemini streaming + test probe,
CARTO map tiles, and the in-app scheduler.

## Summary

| Suite | Result |
|---|---|
| pytest (backend) | **270 passed, 0 failed** (29 min 51 s) |
| Vitest (frontend) | **52 passed, 0 failed** (11 files) |
| `tsc --noEmit` + `vite build` | **pass** (initial chunk 490 kB / 153 kB gzip; 61 chunks, ~1,357 kB total; PWA precache 66 entries) |
| Playwright E2E | **10 passed, 0 failed** (1.3 min) |
| Live uvicorn smoke test (new endpoints) | **26 passed, 0 failed** (`scripts/smoke_new_endpoints.py`) |
| Alembic migrations | upgrade → downgrade → upgrade verified on SQLite (single head `5a6223da9538`) |

## pytest (backend) — 270 passed

Command (note the `TMPDIR`: `/tmp` is a 512 MB tmpfs in this VM and the
torch tests exhaust it; the run must use a disk-backed temp dir):

```bash
cd backend
TMPDIR=~/workspace/farmmarket/.tmp python -m pytest -q
# 270 passed in 1791.83s (0:29:51)
```

| File | Tests | Covers |
|---|---|---|
| test_foundation.py | 27 | Roles, farms, crops, offers, refresh tokens, password reset, vehicles, deliveries, admin, Alembic schema |
| test_hardening.py | 24 | Security headers, CORS fail-closed, production fail-fast, reset-token production behaviour, auth rate limits, DB-aware health, seed guard, password min length, 60-min access tokens, generic 500 handler |
| test_scheduler.py | 21 | **New (this batch):** APScheduler gating (only when `SCHEDULER_ENABLED=true`, never under pytest), lifespan start/stop, daily price-freshness job; asserts exactly one job and no FAOSTAT sync job |
| test_assistant_stream.py | 18 | **New (this batch):** mocked-httpx SSE stream unit tests, admin-only `POST /assistant/test` (60 s probe, 403/401, key never returned), stream endpoint (template/gemini/fallback/mid-stream-error/401/422/rate-limit) |
| test_assistant.py | 17 | Assistant chat, template fallback, RAG sources, conversations, rate limit, Gemini REST transport (success, 404 fallback + error recording, timeout bound, `GEMINI_TIMEOUT_S` env/floor) |
| test_torch_vision.py | 16 | PyTorch model/dataset/train/eval, torch inference, sklearn fallback |
| test_twin.py | 12 | Hash chain, tamper detection, sealing, HMAC readings, public view privacy |
| test_manual_prices.py | 12 | **New (this batch):** admin-only manual price entry (create 201 / re-entry update 200, validation 404/422), source/timestamp stored, REAL/DEMO labels, staleness |
| test_weather.py | 11 | **New (this batch):** Open-Meteo service (single Forecast call with `past_days=7`, past/future split, missing fields → None), endpoint shape, 404, unreachable degradation, 10-min cache + TTL expiry, failures not cached |
| test_ortools_routing.py | 11 | VRP capacity, time windows, refrigeration, baseline/savings, 503/422 |
| test_logistics.py | 11 | Heuristic planner, haversine labelling, emissions |
| test_messaging.py | 9 | **New (this batch):** conversation create-or-find, exchange + unread counts + notification, non-participant 403, body validation, send rate limit 429, inbox ordering |
| test_forecasting.py | 9 | Prophet + sklearn forecasts, back-testing, reliability flags |
| test_contract_fixes.py | 9 | Register refresh token, farm_id, transporter directory, order detail, notification read |
| test_vision.py | 8 | sklearn vision grading, model-not-trained status |
| test_twin_qr.py | 8 | QR PNG, qr_url, threshold alerts, alert permissions |
| test_api.py | 8 | Marketplace, orders, notifications, dashboard |
| test_advisor.py | 8 | Template/Anthropic advisor, language handling |
| test_sklearn_forecast.py | 6 | RandomForest forecaster |
| test_database_url.py | 6 | `mysql://` → `mysql+pymysql://` + `charset=utf8mb4` normalization (PaaS) |
| test_assistant_status.py | 6 | Admin-only `GET /assistant/status` (key flag, model, last error incl. timeouts; 403/401; key never returned) |
| test_matching.py | 5 | Explainable match scoring |
| test_data_sources.py | 5 | Source registry, World Bank sync, DAM not_configured |
| test_simulated_sensors.py | 3 | is_simulated flag, public-view counts, simulation ledger event |

Count vs the 16 Nov report (193): +6 `test_database_url.py` (PaaS commit),
+18 stream/probe, +9 messaging, +11 weather, +12 manual prices,
+21 scheduler = 270. Per-file counts verified with `--collect-only`.

## Vitest (frontend) — 52 passed

```bash
cd frontend && npm run test
# Test Files  11 passed (11)
#      Tests  52 passed (52)
```

Covers login/register forms, protected routes, marketplace filters, listing
form validation, loading/error states (React Testing Library), error
boundary (3 tests), plus this batch: 6 map-tile fallback tests (CARTO →
OSM → unavailable, incl. a full `HubsMap` render test), 10 weather tests
(page states, condition mapping, dictionary parity), 5 messaging tests
(list + unread badge, thread send + mark-read, MessageButton navigation),
4 SSE-parser tests, 8 price-badge tests, and the dictionary key-set test
(BN/EN parity, no empty values).

## TypeScript + build

```bash
cd frontend && npm run build   # tsc --noEmit && vite build
```

Passes. Route-level code splitting (all pages lazy, incl. the new Messages
and Weather pages) keeps the initial JS chunk at **490.36 kB (152.51 kB
gzip)**; total JS across 61 chunks is ~1,357 kB (the service worker
precaches lazy chunks in the background after first load, so total bytes
transferred eventually are similar — the win is critical-path load).
Largest lazy chunks: charts 433.14 kB (recharts), HubsMap 156.54 kB
(Leaflet), validation 92.33 kB (zod). PWA precaches 66 entries (was 61).

## Playwright E2E — 10 passed

```bash
cd frontend
npm run build                    # dist is served by uvicorn during E2E
npx playwright install chromium  # one-time browser download
npx playwright test
# 10 passed (1.3m)
```

| Spec | What it does |
|---|---|
| core-flow.spec.ts | Farmer registers → farm → listing → buyer searches → offer → farmer accepts → order → farmer assigns transporter → transporter picks up → in transit → delivered → farmer creates batch → public `/verify/:code` shows the batch with an intact chain. Now also asserts the buyer/farmer names and the transporter tile render on the order page (regression cover for the OrderDetail fix below). |
| messaging.spec.ts (2 tests) | **New (this batch):** demo buyer messages the Tomato farmer from the listing page, farmer sees the unread badge + replies, buyer sees the reply; demo phone numbers never appear on chat pages. Plus login-required / transporter-blocked guard test. |
| smoke.spec.ts (7 tests) | Landing + Bangla toggle; protected-route redirect; role-guard "Access denied"; assistant template-mode reply; quality page "model not trained"; prices chart renders; unknown-batch verify error |

Notes:
- The E2E server is uvicorn serving the built SPA + API on :8000 with a
  scratch seeded SQLite DB (`e2e/serve.sh`).
- Playwright runs with `channel: "chromium"` (full Chromium build): the
  headless-shell download fails in this VM's sandboxed network (tried twice;
  the full Chromium download works). On a machine where the shell installs,
  the `channel` line can be removed.
- External services run in fallback mode (no keys): template assistant,
  haversine routing, no trained vision model.
- **Fix during this run:** the first full run failed the messaging spec —
  `core-flow.spec.ts` runs first and creates its own Tomato listing for an
  "E2E Farmer", so the unscoped first-Tomato selector messaged the wrong
  farmer (it passed standalone in the workstream). The test now scopes the
  card by farmer name + crop, with an explanatory comment; the app is
  unchanged. Full suite re-run green after the fix.

## Live uvicorn smoke test (new endpoints) — 26 passed

`scripts/smoke_new_endpoints.py` (stdlib-only; run against a seeded scratch
SQLite DB on port 8107): health incl. `db: ok`, SPA serving incl. the
`/weather` fallback route, **live Open-Meteo weather for Dhaka** (`available:
true`, `source: open-meteo`, 7 past + 8 forecast days, real current values)
and unknown-hub 404, farmer/buyer/admin/transporter logins, the full
messaging flow (create conversation → send → buyer reads → unread count
1 → mark read → unread count 0 → non-participant 403 → inbox lists it),
manual price entry (admin 201 with `source: manual` + `label: real`,
`/prices/latest` shows it, re-entry updates with 200, farmer 403),
assistant status as admin (200, key not configured) and the test probe
(no key → `ok: false` with a key error; farmer 403), and the streaming
endpoint returning template SSE with an `event: done`. **26 passed,
0 failed.**

The 42-check smoke test from the 16 Nov production overhaul is not
re-run here (its script was not kept in the repo); its coverage is
subsumed by the pytest suite, the Playwright suite, and this script.

## Bugs found and fixed in this batch

1. **OrderDetail buyer/farmer tiles never rendered (real bug, found by the
   messaging workstream, fixed in the audit).** `GET /orders/{id}` returns
   nested `buyer`/`farmer`/`transporter` objects (the tested contract),
   but the page read flat `o.buyer_name` / `o.farmer_name` /
   `o.transporter_id`, which no orders endpoint returns — both tiles and
   the assigned-transporter line were dead. Fixed frontend-only (nested
   objects + a transporter tile); 3 Playwright regression assertions added
   to core-flow. Checked the same pattern elsewhere: `Deliveries.tsx` is
   **not** a bug (`/deliveries` does return flat names).
2. **App INFO logs were invisible under uvicorn** (root logger has no INFO
   handler), so the assistant latency lines and scheduler startup lines
   never appeared in server logs. Fixed with
   `logging.basicConfig(level=logging.INFO)` in `main.py`; verified live.
3. **Alembic had two heads after merging** — the messaging and manual-price
   migrations both branched from `f6bbf6f95040`. Linearized (price-note
   migration now follows the chat migration); upgrade → downgrade →
   upgrade verified (see below).
4. **Chart.js is not in this app** (doc correction, not a bug): all charts
   use Recharts. The weather chart was built with Recharts following the
   existing ForecastChart pattern; no new dependency was added.
5. **Two doc bugs fixed in the setup guides** (not app bugs): the weather
   verification URL (sklearn endpoint has no weather field — use
   `/forecast/context/{hub}`) and the DEPLOY.md claim that `seed_demo.py`
   has no production guard (the guard exists and is tested).

## Alembic migrations

```bash
cd backend
DATABASE_URL="sqlite:////tmp/fm_alembic3.db" alembic upgrade head
DATABASE_URL="sqlite:////tmp/fm_alembic3.db" alembic downgrade -1
DATABASE_URL="sqlite:////tmp/fm_alembic3.db" alembic upgrade head
# current: 5a6223da9538 (head), single head
```

Four revisions: `96249ebd1d8a` (initial schema, 30 tables),
`f6bbf6f95040` (`sensor_readings.is_simulated`),
`0b194a30001e` (chat conversations + messages, this batch) and
`5a6223da9538` (`price_observations.note`, this batch). Upgrade →
downgrade → upgrade verified on SQLite on 17 Nov.

## Live external-service checks

- **Open-Meteo (new, this batch)**: live-verified from this VM, no key —
  Forecast API with `past_days=7&forecast_days=8` returned full daily data
  for Dhaka (17 Nov: 28.9 °C, clear, at 11:15; yesterday 29.4/21.9 °C)
  and Sylhet; the live endpoint smoke check confirms the same through the
  app's own `/api/v1/weather/{hub}`.
- **CARTO tiles (new, this batch)**: live-verified keyless from this VM —
  `light_all` tiles return HTTP 200 with no key (both the
  `basemaps.cartocdn.com` and `rastertiles` forms).
- **World Bank sync**: the admin data-source sync performed a real bounded
  fetch (SP.POP.TOTL for BGD, 5 yearly values) and reported status ok
  (15 Nov).
- **Gemini / OpenWeather / OSRM**: not tested live (no keys / no OSRM server
  in this VM). Fallback paths are covered by tests and the E2E suite; the
  Gemini REST + streaming paths are covered by mocked tests only. Live
  Gemini behaviour from the user's network is still the open question —
  the admin test probe (`POST /api/v1/assistant/test`) is the diagnostic.

## Not verified in this environment

- MySQL (no server here): tests run on SQLite; MySQL is config-verified
  only (compose YAML, pymysql, `schema.sql`, Alembic). The two new
  migrations were verified on SQLite only.
- Docker (no Docker here): the multi-stage Dockerfile, dev compose file,
  production compose file (`docker-compose.prod.yml`) and Caddyfile are
  config-verified only (YAML parses; build stages and proxy config
  reviewed). No image has been built or run here; Caddy automatic TLS has
  never been exercised. The PaaS configs (`railway.json`, `render.yaml`)
  are likewise config-verified only — no live deploy has happened.
- Live Gemini, live OpenWeather, live OSRM (see above).
- Trained vision model: none exists; no accuracy is claimed.
- Real-browser map fallback behaviour (verified in jsdom with simulated
  tile errors only) and the Weather page/chart rendering in a real browser
  (no browser access in this VM).
- The scheduler has never fired on the clock in production (startup +
  direct job invocation verified only).
