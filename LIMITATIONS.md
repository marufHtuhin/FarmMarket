# FarmMarket — Limitations

What this build does **not** do, what needs real keys/datasets, what is demo
data, and what was not verified in this environment. Read before demoing or
deploying.

## Needs API keys (all optional — fallbacks are labelled)

| Integration | Key / setting | Without it |
|---|---|---|
| Krishi Bondhu assistant (Gemini) | `GEMINI_API_KEY` (Google AI Studio) | Template fallback with RAG sources; replies say so |
| Legacy advisor LLM | `ANTHROPIC_API_KEY` | Template advice (en/bn/sw) |
| Road routing | `OSRM_BASE_URL` (self-hosted OSRM server) | Haversine straight-line estimates, labelled `haversine_estimate` |

Weather needs **no** key: the forecast context endpoint, logistics rain
derating and advisor weather all use keyless Open-Meteo (the old
`OPENWEATHER_API_KEY` is ignored if present in `.env` — delete the line).

Live Gemini and live OSRM were **not** tested in this VM (no key / no
OSRM server). The fallback paths are tested; the live paths are
code-reviewed only. Open-Meteo was verified live from this VM for Dhaka
and Sylhet on 2026-11-17.

Gemini uses plain HTTPS REST (`httpx`) against the Generative Language API —
the gRPC SDK was removed 2026-11-16 after it hung indefinitely from a real
user's network. The call timeout is `GEMINI_TIMEOUT_S` (default 20 s, min
5 s); if the primary model fails for any reason (timeout included) the
call retries ONCE with `gemini-3.5-flash-lite` inside the same overall bound
before falling back to the labelled template reply, and the failure is
recorded (including which models were tried). Admins can see why
template mode is active at `GET /api/v1/assistant/status` (admin-only:
key-configured flag, model name, last error + timestamp — the key is never
returned), and can run a live probe at `POST /api/v1/assistant/test`
(one tiny call, 60 s bound, returns ok/mode/latency/error plus the model
that answered and per-stage timing — connect_ms, ttfb_ms — so a stall
can be localised; never the key). Known live finding (17 Nov 2026): from
the user's machine the REST call read-timed out on BOTH Wi-Fi and a
mobile hotspot, so the ISP is ruled out — the connection opens but the
response body never arrives, even at 60 s. Update the same evening: a
curl test from that machine got a FAST 400 reply from Google (the 400
was a PowerShell quoting artefact — mangled JSON), so the network path
itself works and the hang is now more likely app-side (the httpx call)
than a network block; the probe's per-stage timing is meant to pin down
where the app's call stalls. The decisive test is a curl of the same
generateContent URL from that machine with the JSON passed via a file
(see `GEMINI_KEY_SETUP.md` §5 — never inline `-d "{...}"`, PowerShell
strips the quotes); the deployed version runs on a different network
where Gemini should work.
Replies stream token-by-token (SSE) with a non-stream fallback; streaming
fixes slow *total* time (each chunk is a separate read), but time-to-first-
token is still bounded by the read timeout — if the first token itself
takes >20 s, the stream falls back to template (labelled). Note: `.env` is
loaded once at process start, so a changed `GEMINI_API_KEY` or
`GEMINI_MODEL` does nothing until the backend restarts.

Weather has **one face now**: everything uses Open-Meteo (free, no key).
The **Weather page** shows past 7 days + current + next 7 days per hub
from a single Forecast API call with `past_days=7` (the Archive API is
not used: ERA5 reanalysis lags ~2 days). The **forecast context**
endpoint, logistics rain derating and advisor weather use the same
Open-Meteo service (`fetch_daily_outlook`, today + next 7 days). The
**OpenWeather** integration was retired 2026-11-17: `OPENWEATHER_API_KEY`
is ignored if present in `.env`. Open-Meteo was verified live from this
VM for Dhaka and Sylhet on 2026-11-17; verify live weather at
`GET /api/v1/forecast/context/dhaka` — a live response returns a list of
daily outlooks, an unreachable API returns `{"available": false, ...}`.
The `/forecast/sklearn` response contains no weather field.

## Needs real datasets

- **Vision training images**: no trained model ships. PlantVillage supplies
  *disease* labels only; *ripeness* needs your own labelled photos.
  Train with `ai_services/computer_vision/train.py` (PyTorch) or
  `backend/scripts/train_vision.py` (sklearn baseline). Until a model exists,
  `/vision/assess` returns a clear "model not trained" status.
- **Price history**: no verified price history is bundled. Load your own via
  `scripts/ingest_prices.py --csv` or `--faostat`, or enter daily prices by
  hand as admin (`POST /api/v1/prices/manual` — the realtime path).
  FAOSTAT prices are national and **annual-only** (the Producer Prices
  domain releases once a year; latest release 23 Jan 2025 covers 2020–
  2024), so they are a reference series, never a realtime source, and are
  never auto-scheduled. Hubs in one country share a FAOSTAT series.
- **Bangladesh DAM (Department of Agricultural Marketing)**: no public API
  exists, and no scraper ships. Research (see `docs/dam-prices.md`) found
  the DAM report pages render via JS/PDF with no parseable structure, and
  the only machine-readable prices are an undated ticker of ranges with no
  date, unit or market — converting those to single prices would mean
  inventing data. DAM prices are **manual-entry-only**: an admin enters
  the day's observed prices with a source note. No DAM endpoint is
  invented.
- **CGIAR datasets**: not integrated (load via CSV if useful).

## Demo / illustrative data (labelled as such)

- Seeded prices, demands, products and 2 years of weekly synthetic price
  history are illustrative demo data (`is_synthetic`), not live official rates.
  Every price response now carries source + timestamp and a REAL/DEMO label;
  a missing label renders as DEMO, never REAL. Real prices older than 48h
  show a stale warning; demo prices are never "stale".
- Forecasts on synthetic history say nothing about real markets; every
  forecast is back-tested and marked `reliable: false` if it does not beat
  naive baselines.
- Simulated sensor readings (`scripts/simulate_sensors.py`) are stored with
  `is_simulated=True` and labelled SIMULATED everywhere. Never present them
  as real measurements.
- Emission factors (0.20 empty / 0.32 full kg/km, 1.5 kg/h reefer) and
  cold-chain rules (per-crop, generic defaults 0–30 °C / RH 40–95%) are
  illustrative — supply your own for production.
- The hash chain is tamper-evident, not proof of truthful sensors; head hashes
  are not anchored to an external ledger by default.

## Not verified in this environment

- **MySQL**: no MySQL server in this VM. All tests run on SQLite; MySQL is
  config-verified only (compose YAML, pymysql driver, `schema.sql`, Alembic
  migrations written to be MySQL-compatible). Run the suite against MySQL
  before relying on it.
- **Docker**: no Docker in this VM. The multi-stage Dockerfile,
  docker-compose.yml, docker-compose.prod.yml and Caddyfile are
  config-verified only (YAML parses; build stages and proxy config
  reviewed). No image has been built or run here, and Caddy's automatic
  TLS has never been exercised. Verify on the deployment machine first.
- **Live Gemini / OpenWeather / OSRM**: see above.
- **Trained vision model**: none exists; accuracy is not claimed anywhere.
- **Playwright in this VM**: see TEST_REPORT.md for the run result.

## Known caveats

- **Messaging is in-app chat only.** Farmers and buyers can message each
  other about listings, offers and orders, but phone numbers and emails
  are never shown or shared — only the other party's name, role and
  district. Chat is farmer↔buyer only (transporter/admin cannot message).
  There is no realtime push: open threads poll every 15 s and the inbox /
  unread badge refresh on navigation. Create-or-find uniqueness is
  enforced in application code, not a DB unique constraint (listing/offer
  ids are nullable; NULLs are distinct under UNIQUE in MySQL), so
  concurrent duplicate creates could theoretically produce two threads.
  Message sends are rate-limited (30/min/user, in-process).
- **Scheduler runs in-process.** The daily price-freshness check runs
  inside the API process via APScheduler, enabled only when
  `SCHEDULER_ENABLED=true` (default false; never under pytest). Keep the
  api service at 1 replica — with more replicas the job runs on every
  replica. The job is read-only (it logs freshness, it does not change
  prices). FAOSTAT is annual-only and is never scheduled.
- **Map tiles are keyless by default.** The primary tiles are CARTO
  `light_all`, verified live with no key (both the `basemaps.cartocdn.com`
  and `rastertiles` forms return HTTP 200). OSM tiles are the fallback on
  tile errors, and a "map unavailable" message appears if both fail. If
  CARTO ever enforces keys, set `VITE_CARTO_KEY` at build time (appended
  as `?key=`). The fallback flow was verified in jsdom with simulated
  tile errors, not in a live browser against a genuinely blocked OSM
  endpoint.
- **Charts use Recharts, not Chart.js.** All charts (forecast, weather)
  are built with Recharts; Chart.js is not a dependency.
- **Protobuf pins**: `requirements-ortools.txt` pins `ortools==9.14.6206` +
  `protobuf==6.31.1` (verified: solver tests pass). The old conflict with
  the `google-generativeai`/`grpcio-status` metadata pins (protobuf <6) is
  gone — the Gemini SDK was removed 2026-11-16 (REST transport now) —
  so ortools 9.15 + protobuf ≥6.33 should install cleanly on a fresh
  environment, but the pinned combination is kept because it is the one
  that was actually tested here.
- **Bundle size**: route-level code splitting is done — the initial JS
  chunk is ~478 kB (149 kB gzip), down from a single ~1,300 kB chunk; the
  total across all lazy chunks is still ~1,286 kB (the service worker
  precaches them in the background after first load).
- **Money columns**: new tables use `DECIMAL`; legacy tables (`Product`,
  `Order`, `Demand`) keep float columns for backward compatibility. Do not
  mix the two without explicit rounding.
- **Password reset / email verification**: a mailer now exists
  (`backend/app/services/mailer.py`, stdlib smtplib) — it sends the
  password-reset link (1-hour token) and the registration verification
  link (24-hour token) when `SMTP_*` is configured (see
  `backend/.env.example`). Without SMTP, registration and password reset
  still work but no emails are sent; in dev mode the tokens are returned
  in the API responses for testing, in production never. Live Gmail
  delivery has not been tested from the sandbox yet — the first deploy
  with real SMTP settings is the live check.
- **Rate limiting**: login (10/min/IP), register (30/min/IP) and the
  assistant (10/min/user) are rate-limited, but all limiters are
  in-memory per process (single-node). A multi-worker deployment needs a
  shared store (e.g. Redis). The IP limiters trust the first
  `X-Forwarded-For` entry, which is safe only because Caddy (the edge
  proxy) ignores client-supplied `X-Forwarded-*` headers and writes the
  real client IP itself — do not put another proxy in front without
  configuring `trusted_proxies`.
- **Content-Security-Policy**: not set. The other security headers
  (nosniff, DENY framing, referrer-policy, permissions-policy) are set by
  the backend and HSTS by Caddy, but a CSP was deliberately left out: the
  SPA loads Leaflet tiles, Google Fonts and inline styles, and a wrong CSP
  breaks the UI. Add one only with a Playwright pass against the built SPA.
- **Production fail-fasts**: with `ENVIRONMENT=production` the app refuses
  to start on a missing/short/demo `SECRET_KEY`, a SQLite `DATABASE_URL`,
  or a `*` in `FRONTEND_ORIGINS`. Access tokens default to 60 minutes
  (refresh rotation keeps sessions going); minimum password length is 8.
  `seed_demo.py` refuses to run in production without `--allow-production`.
- **`max_transit_min`** is accepted by the logistics API but is a soft
  penalty in the heuristic planner, not a hard OR-Tools constraint.
- **Demo secrets**: the compose defaults and seed credentials
  (`Demo123!`, `demo-only-change-me-in-production`) are public demo values.
  Never use them in production.
- **Single-node**: no Redis/background workers are configured; sync jobs run
  in-request and are bounded. Uploads are local files (`backend/uploads/`).
- **Payments, delivery tracking, identity verification and dispute
  resolution** are not implemented. Confirm details with the other party
  before any real-world transaction.
