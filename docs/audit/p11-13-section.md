# Audit Phases 11 + 13 — Automated testing improvement + bug-fixing support

Branch: `audit/p11-13` (based on git `163b4ee`). Worktree:
`~/workspace/farmmarket/audit-p1113`. Ports used: backend **8016** (never
8000/5173 — other agents' ports). No existing test file was edited; all
additions are NEW files. No runtime dependencies added. No app code was
changed — see "Bugs found" below.

## Coverage audit: what was thin, what was added

Existing suite at baseline (per handoff; targeted reruns only — no full
pytest run in this worktree, the final full run happens after merge):
pytest 270, Vitest 52, Playwright 10, live smoke 26.

Audited `backend/tests/` (25 files), `frontend/src/**/*.test.*` (11 files),
`frontend/e2e/` (3 specs). Thin areas found and addressed:

| Thin area | Before | Added (Phase 11) |
|---|---|---|
| Auth edge cases | refresh rotation + reset happy path only | `backend/tests/test_p1113_auth_edges.py` — 20 tests: duplicate email 409, invalid email/short name/missing password 422, password >72 UTF-8 bytes 422, unknown role 400, wrong-password/unknown-email login 401 (same message, no enumeration), `/auth/me` with no/malformed/wrong-key/expired/nonexistent-user token 401, expired refresh token 401 + revoked, expired reset token 400, forgot-password invalidates earlier token, reset revokes refresh tokens |
| Marketplace ownership / validation / filters / empty states | product create + farm ownership only | `backend/tests/test_p1113_marketplace_edges.py` — 29 tests: empty product/demand/match/order lists, search+district filters, removed listings excluded, buyer create 403, non-positive quantity/price 422 (parametrized), bad unit 422, edit/delete other farmer's product 403 + 404s, demand scoping (buyer sees own, farmer sees all) + validation, match scoping per viewer + empty/incompatible, order role/404/409/422, full state-machine invalid transitions, stock release on reject (once) and on cancel (sold→available), order detail for admin, dashboard empty zeros, price filters |
| Admin pagination | role/search filter only, no paging | `backend/tests/test_p1113_admin_pagination.py` — 8 tests: page 1/2/3 disjoint + total, past-end empty page, defaults (page 1, size 20), bounds 422 (page 0/-1, size 0/101; size 100 OK), role+search combined, verify unknown user 404, empty audit logs, empty-platform stats zeros |
| External-service failures (ALL MOCKED — see note) | weather + Gemini failure paths only | `backend/tests/test_p1113_external_failures.py` — 10 tests: forecast-context with mocked World Bank `httpx.HTTPError` → macro unavailable (200), mocked OpenWeather None → weather unavailable, unknown hub 404, `fetch_daily_outlook` mocked httpx error → None, no-key → None, `/logistics/plan` mocked OSRM failure → 502, `/logistics/optimize` mocked OSRM failure → haversine fallback with `distance_basis` + note, plan/optimize unknown hub 404, plan validation boundaries (lat, 61 stops, bad mode, no vehicles), DB failure on `/products` → generic 500 with no leak |
| Frontend component tests | PriceBadge, MapTiles, Messages, ErrorBoundary only | `frontend/src/components/__tests__/product-card.test.tsx` — 13 tests: renders name/price/district/farmer/quantity, detail link, low-stock badge boundary (qty 0/1/5/6/100), buyer-only Order/Make-offer buttons (hidden for farmer, logged-out, out-of-stock), modal opening |
| Frontend utils | crops, validation, weather only | `frontend/src/utils/format.test.ts` — 26 tests: `unitLabel` (en/bn, case-insensitive, null default, unknown passthrough), `statusTone` (all mappings + fallback), `apiErrorMessage` (string/array detail, message fallback, generic), `apiStatus`/`isNotFound`, `formatPriceTaka` |
| Playwright E2E | smoke, core-flow, messaging only | `frontend/e2e/weather-prices.spec.ts` — 6 tests: weather page live Open-Meteo (current conditions + past-7-days + chart), hub switch to Chattogram, prices page crop/hub change, wrong-password login error + stays on /login, duplicate-email register error + stays on /register, logged-in farmer reaches weather page |

**Mocked vs live, strictly separated.** The external-failure tests are
labelled `[MOCKED]` in docstrings and prove only that the app degrades
honestly when a dependency fails — they never claim the real service works.
Live checks: Open-Meteo (weather page E2E + smoke) and Carto/OSM tiles are
live-tested; Gemini, OpenWeather, OSRM, MySQL, Docker and the first PaaS
deploy remain BLOCKED in this VM (no key/server) and are not claimed.

**Scheduler behaviour** was already covered (14 tests in
`test_scheduler.py`, incl. empty-DB freshness job and threshold env) — no
new scheduler tests added. **Pagination** exists only on
`GET /api/v1/admin/users`; all other list endpoints are unpaginated by
design (documented observation, not changed).

## Status table

| Area | Status | Tests added | Result |
|---|---|---|---|
| Auth edge cases (pytest) | PASS | 20 | 20 passed |
| Marketplace edges (pytest) | PASS | 29 | 29 passed |
| Admin pagination (pytest) | PASS | 8 | 8 passed |
| External-service failures, mocked (pytest) | PASS | 10 | 10 passed (1 fixed during run, see below) |
| ProductCard (Vitest) | PASS | 13 | 13 passed |
| format utils (Vitest) | PASS | 26 | 26 passed |
| Weather/prices E2E (Playwright, port 8016) | PASS | 6 | 6 passed (2 locator fixes during run, see below) |
| Live smoke script (`scripts/smoke_new_endpoints.py`, port 8016) | PASS | — | 26 passed, 0 failed |
| Full Vitest suite (baseline 52 + 39 new) | PASS | — | 91 passed (13 files) |
| Full pytest suite | NOT RUN | — | Per task: targeted runs only; final full run happens once after merge by the coordinator |

## Test commands run (exact) + results

```bash
# New backend tests (4 files, 67 tests) — 24 min wall time: the VM was at
# load 9-14 with 12 concurrent pytest processes from parallel audit agents,
# and the SQLite test DB sits on btrfs (write amplification). The suite
# itself is fast; the environment was not.
cd backend
TMPDIR=~/workspace/farmmarket/.tmp ~/workspace/farmmarket/.venv/bin/python -m pytest \
  tests/test_p1113_auth_edges.py tests/test_p1113_marketplace_edges.py \
  tests/test_p1113_admin_pagination.py tests/test_p1113_external_failures.py -q
# → 1 failed, 66 passed in 1458.08s

# Re-run of the single fixed test:
TMPDIR=~/workspace/farmmarket/.tmp ~/workspace/farmmarket/.venv/bin/python -m pytest \
  tests/test_p1113_external_failures.py::test_optimize_mocked_osrm_failure_falls_back_to_haversine -q
# → 1 passed in 75.47s

# New Vitest files:
cd frontend && npx vitest run src/utils/format.test.ts \
  src/components/__tests__/product-card.test.tsx
# → 39 passed (13 ProductCard + 26 format)

# Full Vitest suite:
npx vitest run
# → Test Files 13 passed (13); Tests 91 passed (91)

# Frontend build (needed for SPA-serving smoke + Playwright):
npm ci && npm run build
# → ✓ built in 23.67s (PWA precache 66 entries)

# Live smoke against backend on 8016 (seeded scratch SQLite DB):
cd backend
DATABASE_URL=sqlite:////home/hatch/workspace/farmmarket/.tmp/p1113-smoke.db \
  SECRET_KEY=p1113-smoke-secret-key-do-not-use-in-prod \
  python seed_demo.py
DATABASE_URL=<same> python -m uvicorn app.main:app --host 127.0.0.1 --port 8016
cd .. && python scripts/smoke_new_endpoints.py http://127.0.0.1:8016
# → 26 passed, 0 failed (health, SPA, live Open-Meteo weather, logins,
#    messaging, manual prices, assistant status/probe/stream)

# New Playwright spec (override config on port 8016 — the standard config
# hardcodes port 8000, which other agents use):
cd frontend
npx playwright test --config playwright.p1113.config.ts e2e/weather-prices.spec.ts
# → 6 passed (28.8s)
```

The new spec only uses `baseURL`-relative navigation, so it also runs
unchanged under the standard `playwright.config.ts` (port 8000) — that
configuration was NOT executed in this worktree because port 8000 is
reserved for other agents. The override files are additive and do not
touch the standard config:
`frontend/playwright.p1113.config.ts` + `frontend/e2e/serve-p1113.sh`
(port 8016, own scratch DB `e2e/.e2e-p1113.db`, gitignored).

## Bugs found (Phase 13)

**No real application bug was found.** Every failure encountered during
this phase was a defect in a NEW test written here, fixed in the test:

1. `test_optimize_mocked_osrm_failure_falls_back_to_haversine` — my
   assertion read `s["stop_id"]`, but `/optimize` returns stops as plain
   id strings (unlike `/plan`, which returns dicts). Fixed the assertion
   to the real shape; the app's fallback behaviour
   (`distance_basis == "haversine_estimate"` + "OSRM failed" note) was
   correct. Proof: single-test rerun → 1 passed.
2. `weather-prices.spec.ts` — three Playwright strict-mode violations in
   MY locators: `getByText("Past 7 days")` and
   `getByText("Current conditions")` also matched the page subtitle, and
   `getByText("Chattogram")` also matched the hidden `<option>`. Switched
   to role/text-exact locators. The pages rendered live weather correctly
   throughout. Proof: rerun → 6 passed.
3. `format.test.ts` — wrong import path (`../format` instead of
   `./format`). Fixed; 26 passed.

**Observations for the coordinator (not fixed — out of scope / by design):**

- `/logistics/plan` returns route stops as dicts (`stop_id`, …) while
  `/logistics/optimize` returns them as plain id strings. Both shapes are
  asserted by existing tests, so this is the established contract, but it
  is an API inconsistency worth noting in API docs.
- Only `GET /api/v1/admin/users` paginates; `/products`, `/demands`,
  `/prices`, `/matches`, `/orders/my`, `/notifications` (limit 30) return
  full lists. Fine for the demo scale, but unbounded growth is a
  follow-up if the catalogue grows.
- The 4-file pytest run took 24 minutes wall time under the shared-VM
  load (load 9–14, 12 concurrent pytest processes, btrfs write
  amplification on the SQLite test DB — ~838 MB of block writes for a
  416 KB test DB). Consider scheduling the coordinator's final full run
  when fewer agents are testing concurrently.

## Files changed (all NEW, none modified)

| File | Why |
|---|---|
| `backend/tests/test_p1113_auth_edges.py` | 20 auth edge-case tests |
| `backend/tests/test_p1113_marketplace_edges.py` | 29 marketplace edge-case tests |
| `backend/tests/test_p1113_admin_pagination.py` | 8 admin pagination tests |
| `backend/tests/test_p1113_external_failures.py` | 10 mocked external-failure tests |
| `frontend/src/components/__tests__/product-card.test.tsx` | 13 ProductCard tests |
| `frontend/src/utils/format.test.ts` | 26 format-util tests |
| `frontend/e2e/weather-prices.spec.ts` | 6 Playwright tests (live weather + prices + auth errors) |
| `frontend/playwright.p1113.config.ts` | E2E override config on port 8016 |
| `frontend/e2e/serve-p1113.sh` | Backend+SPA server for the override config (port 8016) |
| `docs/audit/p11-13-section.md` | This file |

## What remains UNVERIFIED / unfixed

- Full pytest suite (270 baseline + 67 new): NOT run here by design;
  coordinator runs it once after merge.
- New Playwright spec under the standard port-8000 config: NOT run here
  (port reserved); the spec is baseURL-relative and should run unchanged.
- Live MySQL, Docker build/run, live Gemini, live OpenWeather, live OSRM,
  first PaaS deploy: BLOCKED in this VM (no server/key) — unchanged.
- Real-browser map-tile fallback and scheduler firing on the clock: not
  in this phase's scope (other audit groups).
- No unfixed bugs: the three failures found were test-side defects, all
  fixed and re-verified.
