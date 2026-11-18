# Audit — Phase 7 (AI & external data) & Phase 8 (Logistics & Digital Twin)

Auditor: Phase 7–8 agent. Worktree `audit/p7-8`, based on git `163b4ee`.
Audit date: 2026-11-17. All counts below are from tests actually executed in
this worktree; anything not executed is marked BLOCKED, never PASS. Mocked
tests and live tests are kept strictly separate.

Status labels: **PASS** / **FAIL** / **BLOCKED** / **NOT IMPLEMENTED** /
**PARTIAL**. "Requires configuration" means the feature needs a key/server
the auditor does not have — it is never reported as "works".

## Environment notice (VM-wide, NOT an app bug)

Since ~07:54 UTC on 2026-11-17 the sandbox intermittently blocks `write`
syscalls with EPERM (confirmed by direct syscall probing: `open`/`fsync`/
`flock` succeed, `write`/`pwrite` fail with `PermissionError: [Errno 1]
Operation not permitted`). Consequences for this audit:

- `tempfile.gettempdir()` validation fails, so pytest cannot even start
  without a workaround. Workaround used: a `sitecustomize.py` on
  `PYTHONPATH` (at `~/workspace/farmmarket/.tmp/pysite/`, outside this
  worktree) that presets `tempfile.tempdir`, skipping the write-probe.
- SQLite writes fail with `sqlite3.OperationalError: disk I/O error`, so
  every DB-backed test errors at fixture setup (`Base.metadata.create_all`)
  while the flap is active. These are marked **BLOCKED (environment)**,
  never FAIL. Retried in fresh calls multiple times (08:00–08:06 UTC);
  the flap persisted.
- `git commit` may fail with "unable to write loose object file" for the
  same reason; see the final report for the commit status.

## Test runs (targeted suites only; no full pytest run in this worktree)

| Command (from `backend/`, `TMPDIR=~/workspace/farmmarket/.tmp`) | Result |
|---|---|
| `pytest tests/test_data_sources.py tests/test_forecasting.py tests/test_sklearn_forecast.py tests/test_matching.py -q` | 25 passed |
| `pytest tests/test_vision.py tests/test_torch_vision.py tests/test_twin.py tests/test_twin_qr.py tests/test_simulated_sensors.py -q` | 47 passed |
| `pytest tests/test_logistics.py tests/test_ortools_routing.py tests/test_assistant.py tests/test_assistant_status.py tests/test_assistant_stream.py tests/test_weather.py tests/test_manual_prices.py -q` | 86 passed |
| `pytest tests/test_audit_p78.py tests/test_matching.py tests/test_assistant.py tests/test_assistant_stream.py tests/test_data_sources.py tests/test_weather.py tests/test_logistics.py -q` (new + affected suites, after fixes) | 71 passed, **2 failed, 17 errors** — ran as the flap started ~07:52. 1 failure was a quoting bug in my own FAOSTAT test CSV (fixed, re-verified passing). The 2nd failure was not identified (output truncated by `tail`; could not rerun to identify — see below). All 17 errors were `sqlite3.OperationalError: disk I/O error` at fixture setup (environmental) |
| `pytest tests/test_audit_p78.py -q` (new tests only, after the CSV fix; retried 5× in fresh calls) | **13 passed, 10 errors** every time. The 10 errors are all DB-backed tests failing at fixture setup with `disk I/O error` → **BLOCKED (environment)**. The 13 passing tests cover all non-DB new tests |
| `npx vitest run src/components/__tests__/batch-view.test.tsx` (frontend) | 3 passed |
| `npx vitest run` (full frontend suite, after fixes) | 55 passed (52 baseline + 3 new) |
| `npx tsc --noEmit` (frontend) | clean |

Baseline (re-run, not taken on trust): the three backend batches above
reproduce the claimed 270-pytest baseline for the P7–8 subset (25 + 47 +
86 = 158 tests across the 17 P7–8 files). They ran BEFORE the flap
(07:20–07:52 UTC) and are unaffected by it.

**Still needing a clean rerun once the environment recovers:** the full
`test_audit_p78.py` (10 DB tests BLOCKED), and the affected-suite batch
above (to identify the 2nd failure and confirm the 17 errors clear).
The coordinator's post-merge full run covers both.

Live checks executed from this VM (internet, no keys): Open-Meteo,
World Bank API, Carto + OSM tiles, FAOSTAT bulk CSV download + parse.
See the per-service report below.

## Findings & status table

### P7-A — Price intelligence adapters

| Feature | Status | Test performed | Issue | Fix |
|---|---|---|---|---|
| FAOSTAT bulk CSV parse (monthly, LCU/tonne → per-kg) | PASS (live) | Downloaded the real `Prices_E_All_Data_(Normalized).zip` (11.7 MB, CSV dated 2026-10-09) and ran `read_faostat_producer_prices` on the full 214 MB file: 3,889 rows for the 10 hubs; date range 2010-01 → 2023-12; currencies per hub (BDT/GHS/KES/NGN/TZS), unit kg, `is_synthetic=False`, source labelled "national, <Area>" | None in the parser. Coverage gaps are data gaps: Uganda/Kampala has **zero** monthly producer-price rows in the file, and the newest monthly data is 2023-12 (FAOSTAT lags ~2 years) | None (data limitation, reported) |
| FAOSTAT parser edge cases | PASS | New `test_audit_p78.py`: annual rows, LCU/kg basis, negative price, unknown area all skipped; 12000 LCU/tonne → 12.00/kg | None | — |
| Duplicate prevention on ingest | PARTIAL | `upsert_prices` is exercised by the baseline forecasting/sklearn tests (which passed). The explicit idempotency test (`test_faostat_upsert_is_idempotent`: 2nd run 0 inserted / 3 skipped) is **BLOCKED (environment)** — DB fixture setup fails with `disk I/O error`. `upsert_prices` itself was not modified by this audit | None | — |
| World Bank indicator fetch | PARTIAL (live) | Live `fetch_indicator("BGD", "SP.POP.TOTL", 2020, 2024)` returned 5 yearly values. But `stability_summary` (inflation FP.CPI.TOTL.ZG) hit `ReadTimeout` twice: the API takes ~12s (population) / ~21s (inflation) from this network, over the 20s client timeout and far over the 10s sync-probe timeout | Timeouts too tight for measured latency; sync probe would fail spuriously | Raised `worldbank.TIMEOUT_S` 20 → 30s and `sync.SYNC_TIMEOUT_S` 10 → 30s; added a regression test asserting both ≥ 30 |
| World Bank malformed entries | FAIL → fixed | New test with mocked API returning null/missing/bad date/bad value/non-dict rows | `fetch_indicator` did `int(x["date"])` / `float(x["value"])` unguarded; one bad row → ValueError → 500 in `/forecast/context/{hub}` (which only catches `httpx.HTTPError`) | `fetch_indicator` now skips malformed entries; valid rows still returned |
| DAM (Bangladesh) | NOT IMPLEMENTED (correctly) | Registry test: endpoint `""`, status `not_configured`, no endpoint invented | None — honest non-implementation; see `docs/dam-prices.md` | — |
| CGIAR | NOT IMPLEMENTED (correctly) | Registry: status `manual`, "No integrated API; datasets loadable via CSV" | None | — |
| OpenWeather adapter (no key) | PASS (mocked) | `fetch_daily_outlook` returns `None` without a key; `speed_factor(None)` = 1.0 with "weather unavailable" note; never assumes clear sky | None | — |
| OpenWeather malformed 200 body | FAIL → fixed | New test: mocked 200 with invalid JSON, missing `"list"`, items missing `"dt"`/`"main"` | Only `httpx.HTTPError` was caught; a malformed body raised KeyError/ValueError → 500 in `/forecast/context`, `/logistics/plan`, `/logistics/optimize` (calls sit outside their try blocks) | Malformed body/items now degrade to `None`/skipped; `speed_factor` then reports weather unavailable |
| OpenWeather live | BLOCKED | No API key in this VM | Requires `OPENWEATHER_API_KEY` | — |
| Open-Meteo (past 7 + today + next 7) | PASS (live) | Live `fetch_weather(23.8103, 90.4125)`: 7 past days, 8 forecast days, current 29.8 °C, source `open-meteo`, fetched_at stamped; plus 11 mocked unit/endpoint tests (caching, unavailable state, missing fields → None not 0) | None | — |
| Open-Meteo non-JSON body | FAIL → fixed | New test: mocked 200 with non-JSON body | `r.json()` ValueError was not caught (only `httpx.HTTPError`), so a bad body → 500 on `/api/v1/weather/{hub}` | `fetch_weather` now returns `None` on ValueError too |
| Carto (primary) / OSM (fallback) tiles | PASS (live) | `curl`: Carto tile 200 (2049 B, 1.1s), OSM tile 200 (6725 B, 1.2s); Vitest map-tiles tests cover the Carto→OSM→unavailable fallback state machine | None | — |
| Seed/demo price labelling | PASS | Synthetic rows flagged `is_synthetic=True`, source `synthetic-demo`; forecast responses carry `synthetic_share` + SYNTHETIC warning; manual prices carry REAL/DEMO/stale labels (test_manual_prices) | None | — |
| Currency handling | PASS | FAOSTAT rows take the hub's currency; forecasts return the hub currency per pair; no cross-currency arithmetic anywhere (each hub×crop series is single-currency) | None | — |

### P7-B — Price forecasting

| Feature | Status | Test performed | Issue | Fix |
|---|---|---|---|---|
| sklearn RandomForest forecaster | PASS | 6 tests (shape, provenance, insufficient-data 422, endpoint 404s); interval ordered (`lower ≤ yhat ≤ upper`), positive forecasts, log-space fit | None | — |
| Forecast provenance: demo vs real | PARTIAL | Seeded demo series → `synthetic_share == 1.0` + SYNTHETIC warning (baseline tests pass). **New test** (`test_sklearn_forecast_prefers_real_series`: 40 weekly REAL rows → `real_only=True`, `synthetic_share == 0`) is **BLOCKED (environment)** — DB fixture setup fails with `disk I/O error`. The real-preference logic in `load_series` is pre-existing, unmodified code, code-reviewed only for this path | None | — |
| Backtest metrics (MAE / sMAPE / skill vs naive) | PASS | sklearn: 1 rolling-origin fold vs last-value naive, `reliable` only when skill > 0. Prophet: 3 folds vs naive + seasonal-naive, with interval coverage. Metrics are computed, not claimed | None | — |
| Prophet forecaster | PASS | 9 forecasting tests pass with Prophet 1.5.0 installed in the venv (fits are slow: the batch took ~5.5 min on a contended 1.5-CPU VM) | None | — |
| Insufficient-data fallback | PASS | < minimum points → `InsufficientDataError` → HTTP 422, never a made-up forecast; >20% gaps refused; Prophet-missing → 503 with pointer to sklearn endpoint | None | — |
| Accuracy claims | PASS (by absence) | No accuracy number is asserted anywhere; `reliable` is a backtest comparison, and unreliable forecasts carry a "do not rely on it" warning | None | — |

### P7-C — Vision (disease & ripeness)

| Feature | Status | Test performed | Issue | Fix |
|---|---|---|---|---|
| "Model not trained" behaviour | PASS | No `backend/models/` dir exists in the worktree. Service test + API test (`test_assess_api_503_when_no_model_at_all`): `assess` raises `ModelNotAvailableError` → HTTP 503 "No vision models are trained yet". **No fake confidence is emitted anywhere** | None | — |
| Disease vs ripeness as separate tasks | PASS | Separate `ripeness` / `disease` bundles, checkpoints and backends; `assess` picks a backend per task independently; a single missing task degrades gracefully with `notes: {task: "model_not_trained"}` and a warning; grade uses the other signal only | None | — |
| Invalid / corrupt / oversized images | PASS | Existing: non-image bytes and >5 MB rejected (`BadImageError` → 400). **New tests**: truncated PNG, header-only PNG, empty file rejected | None | — |
| Varied dimensions | PASS | **New test**: 1×1, 1000×10, 10×1000, 640×480 images all load and yield finite fixed-length features | None | — |
| Confidence thresholding / REVIEW | PASS | Grade rules tested: low confidence (<0.60) → REVIEW with no price multiplier; crop mismatch (model saw tomato, listing says banana) → REVIEW | None | — |
| Training plumbing (sklearn + torch) | PASS | 8 vision + 16 torch-vision tests: training writes model card + metrics, corrupt torch checkpoint falls back to sklearn, checkpoint-without-torch raises a clear error, 1-epoch train + evaluate smoke pass on synthetic images. **These prove plumbing only, not real-world accuracy** | None | — |
| PlantVillage labelling | PASS | Code + docs state PlantVillage has disease labels only, no ripeness labels; ripeness training requires separate `unripe|ripe|overripe` folders (enforced in `train_vision.py`) | None | — |
| Accuracy claims | PASS (by absence) | No accuracy is claimed for any shipped model, because no model ships. `evaluate.py` prints accuracy only together with n_images + class list | None | — |

### P7-D — AI assistant (Gemini REST + template + RAG)

| Feature | Status | Test performed | Issue | Fix |
|---|---|---|---|---|
| Live Gemini | BLOCKED | No key in this VM (and blocked from the user's network per prior diagnosis) | Requires `GEMINI_API_KEY` + reachable Google API | — |
| Gemini REST path (mocked) | PASS | Mocked-httpx tests: 200 → mode `gemini`, key in `x-goog-api-key` header (never in URL), 404 (retired model) → template + error recorded, hang → template within the timeout (daemon-thread join, no ThreadPoolExecutor hang) | None | — |
| Template fallback labelling | PASS | No-key chat returns mode `template`; reply header says "template advice … (no AI model was used)" in bn/en; UI shows a Template/Gemini badge per message | None | — |
| Missing-key diagnostics | PASS | Baseline tests cover it: `test_assistant_status.py` (6 tests) + `test_assistant_stream.py::test_test_endpoint_no_key` (both passed pre-flap). Admin-only (403/401 tested). The consolidated new test (`test_assistant_status_without_key_is_honest`) is **BLOCKED (environment)** — DB fixture setup fails with `disk I/O error` | None | — |
| Bengali / English questions | PASS | **New test**: Bangla question → template reply labelled in Bangla ("টেমপ্লেট"); English template path covered by existing tests | None | — |
| Irrelevant questions / hallucination risk | FAIL → fixed | **Found live**: `retrieve("What is the capital of France?")` returned `market-prices-explainer.md` at score 0.25 — higher than some genuine matches — because TF-IDF had no stop-word filtering and common words ("what/is/the") dominated. The template reply would have quoted market-price bullets as an "answer" | RAG retrieval grounded unrelated questions in unrelated notes | `TfidfVectorizer(stop_words="english")`. After fix, verified by direct service-level queries: France → `[]`; genuine queries rank better (tomato 0.48 vs 0.32 before); Bangla queries still match via Bangla titles (টমেটো). The API-level test (`test_assistant_irrelevant_question_invents_nothing`) is **BLOCKED (environment)** — DB fixture setup fails with `disk I/O error` |
| Empty / long prompts | PASS | Empty string → 422; whitespace-only → 422; >2000 chars → 422 (existing tests) | None | — |
| Timeout behaviour | PASS | Hung model call → template in ~1s bound (regression test); `GEMINI_TIMEOUT_S` env override with 5s floor; streaming has per-read + 180s total bounds | None | — |
| Streaming (SSE) | PASS (mocked) | 18 stream tests: ordered chunks, comment/`[DONE]`/empty skipping, HTTP error + 404 detail, empty stream, no-key, template-mode stream, Gemini-mode stream, pre-first-token fallback to template, mid-stream failure keeps partial reply + error event, shared rate limit with chat | None | — |
| Rate limiting | PASS | 10/min default per user, env-overridable, 429 tested via API | None | — |
| RAG price grounding | PASS | `price_context` quotes only stored `PriceRecord` rows whose product name appears in the query, with source + recorded date; no match → no prices quoted | None | — |
| Dosage / safety guardrails | PASS | System instruction forbids pesticide/fertiliser dosages and inventing prices/weather/dates; template replies end with the "ask your local extension officer" line | None | — |

### P7-E — Demand matching

| Feature | Status | Test performed | Issue | Fix |
|---|---|---|---|---|
| Score calculation & ranking | PASS | Existing 5 tests + **new tests**: exact match scores 100.0; cheaper/closer/fuller supply ranks above dearer/farther/partial supply | None | — |
| Zero / negative price | FAIL → fixed | **New test**: `price_per_unit=0` | `calculate_match` divided by `price_per_unit` unguarded; the DB column has no CHECK constraint (only the API schema enforces > 0), so a zero price would crash `GET /api/v1/matches` with ZeroDivisionError (500) | Zero/negative prices (and zero target price) now return "no match"; None names/units/districts guarded |
| Time component | FAIL → fixed | **New tests**: slack grading | `time_score` was hardcoded to 100 for every match — a constant 10-point gift — while the reasons list claimed "Availability date checked" | `time_score` now grades availability slack: 100 with no date constraint or ≥14 days slack, 50 same-day, linear between. Exact-match test still scores 100.0 |
| Explanations | FAIL → fixed | **New tests** | `reasons` was a fixed 5-item list regardless of outcome ("Price compared with buyer budget" even when the price was 2× budget) | Reasons now describe actual outcomes (full/partial quantity, within/above budget, same/different district, slack days) |
| Quality factor | NOT IMPLEMENTED | No quality/grade field exists on Product/Demand, so matching cannot score quality | Design gap, not a bug: vision grades live in `GradeAssessment`, not on the listing | Reported; not implemented (schema change, out of audit scope) |
| Distance | PARTIAL | Location is district equality only (100 same / 40 different); no coordinates are stored on products/demands | Coarse by design; documented in the module docstring | Reported; not changed |

### P8 — Logistics (OR-Tools + OSRM)

| Feature | Status | Test performed | Issue | Fix |
|---|---|---|---|---|
| Heuristic planner (multi-stop, capacity, windows, freshness, CO₂) | PASS | 11 logistics tests: every stop served once, capacity respected, deterministic per seed, infeasible inputs rejected (oversize stop, fleet too small, duplicate ids), window waiting/lateness, shelf-life penalty + reefer benefit, CO₂ rises with load, collection mode, carbon trade-off rows | None | — |
| OR-Tools VRP | PASS | 11 tests with OR-Tools installed: capacity + time windows + refrigeration enforced, computed nearest-neighbour baseline with real savings %, 503 when not installed (never silent substitution), 422 for infeasible input | None | — |
| OSRM live road data | BLOCKED | No OSRM server in this VM | Requires `OSRM_BASE_URL` pointing at a running OSRM server | — |
| OSRM parsing / unreachable handling | PASS (mocked) | Mocked OSRM table response parsed (5.0 km / 10.0 min); `null` durations → RuntimeError; >100 points rejected | None | — |
| OSRM fallback in `/optimize` | BLOCKED (environment) | **New test** (`test_optimize_osrm_failure_falls_back_to_haversine_labelled`: `OSRM_BASE_URL=http://127.0.0.1:9` closed port → 200, `distance_basis: "haversine_estimate"`, "OSRM failed … fell back" note) could not execute — DB fixture setup fails with `disk I/O error`. Fallback logic code-reviewed only | None | — |
| OSRM unconfigured | BLOCKED (environment) | **New test** (`test_plan_osrm_unconfigured_is_400_not_silent_fallback`) could not execute — same `disk I/O error`. Logic code-reviewed only | None | — |
| Straight-line labelling | PASS | Baseline test `test_optimize_haversine_response_labelled` passed pre-flap; `/plan` haversine note verified by code inspection + the same baseline coverage. The new `/plan` test (`test_plan_haversine_labels_straight_line`) is **BLOCKED (environment)** — DB fixture setup fails with `disk I/O error` | None | — |
| Invalid destinations | PASS | Coordinates validated by Pydantic (`lat -90..90`, `lon -180..180`); unknown hub for weather → 404 | None | — |
| Weather derating | PASS | `speed_factor`: heavy rain (≥10 mm) 0.75, rain (≥2 mm) 0.9, unknown weather 1.0 with explicit "weather unavailable" note | None | — |
| Emissions estimates | PASS (labelled) | Factors are illustrative defaults, labelled as such in code, API notes and `co2e_assumptions`; user-supplied per-vehicle factors supported | None | — |
| `/plan` vs `/optimize` inconsistency | PARTIAL | `/plan` returns 502 when OSRM fails; `/optimize` falls back to haversine with a label. Both are honest, but the behaviour differs | Minor inconsistency, documented here; not changed (changing `/plan` to fall back would alter its contract) | Reported only |

### P8 — Digital Twin

| Feature | Status | Test performed | Issue | Fix |
|---|---|---|---|---|
| Batch creation / unique batch ID | PARTIAL | Creation writes the genesis `harvested` block (baseline twin tests pass). The uniqueness test (`test_twin_batch_codes_are_unique`: 50 batches → 50 unique `FM-` codes) is **BLOCKED (environment)** — DB fixture setup fails with `disk I/O error` | None | — |
| QR generation + public verification page | PASS | 8 twin-qr tests: QR returns PNG, no login required, unknown code 404, public view includes `qr_url`; frontend `/verify/:code` renders `BatchView` | None | — |
| Event history / role rules | PASS | Farmer-only own-batch events; buyer only with linked order; `sensor_seal` cannot be added manually; unknown event type rejected | None | — |
| Temperature / moisture records | PASS | HMAC-signed ingestion; range validation (-40..80 °C, 0..100 %); future timestamps rejected; bad signature / unknown device / replay rejected; cold-chain excursion analysis (tomato 8–15 °C) + maize product-moisture limit tested | None | — |
| Timestamp consistency | PASS | Readings use `_iso` (second precision, no microseconds) for both signing and storage; block timestamps likewise | None | — |
| Hash chain + Merkle sealing | PASS | 12 twin tests: fresh chain verifies, Merkle root changes with any leaf | None | — |
| **Tamper test (executed)** | PASS | `test_twin.py::test_altering_a_block_is_detected` + `test_rehashing_one_block_still_breaks_the_next_link` + `test_sensor_tampering_detected_after_seal` + `test_deleting_a_sealed_reading_detected` — all executed and passing pre-flap in this worktree. The additional new end-to-end test (`test_twin_tamper_breaks_chain_end_to_end`) is **BLOCKED (environment)** — DB fixture setup fails with `disk I/O error` | None | — |
| Simulated vs real sensor labelling | PASS | `is_simulated` stored per reading; public view counts `simulated_readings`; alerts flag `simulated`; frontend shows a SIMULATED badge (bn "সিমুলেটেড" / en "Simulated") when any sealed reading is simulated or a `sensor_simulation` event exists; `simulate_sensors.py` posts `simulated: true` and records a ledger event saying so | None | — |
| Sensor history chart (frontend) | FAIL → fixed | **Found by inspection**: `public_view` sends each seal's `temp_c` as the `{min, max, avg}` summary object, but `BatchView` expected a number (`typeof ev.temp_c === "number"`), so `tempPoints` was always empty and **the sensor chart never rendered** — every batch showed "No sensor readings yet." even with sealed readings | Frontend/backend type mismatch on timeline `temp_c` | `BatchView` now reads the average from the object (plain numbers still accepted); `api.ts` type corrected; new Vitest tests (3 passed, full suite 55 passed). The backend contract test (`test_twin_public_timeline_temp_is_summary_object`) is **BLOCKED (environment)** — DB fixture setup fails with `disk I/O error`; the object shape was verified by code inspection of `public_view` |
| Anchoring / "blockchain" claims | PASS | `LocalAnchor` reports `external: false`, provider `local-unanchored`; public view says "Not yet anchored to an external ledger"; module docstring states the chain is tamper-evidence, NOT a blockchain | None | — |
| Public view privacy | PASS | No emails, user ids, actor ids, or raw coordinates in the public view (tested) | None | — |

## Per-AI-service report

| Service / model | Provider | Source | Live / demo / mock | Test | Result | Limitations |
|---|---|---|---|---|---|---|
| Gemini `gemini-3.8-flash` (chat + streaming + probe) | Google Generative Language API, REST over httpx | `services/gemini_assistant.py` | **Mocked** (live BLOCKED: no key) | Mocked-httpx success/404/timeout/hang tests; SSE stream tests; `/assistant/test` probe with no key | Mocked paths behave correctly; timeout is a real bound; failures fall back to labelled template mode and are recorded for `/assistant/status` | Live behaviour unverified from any network; known blocked from the user's network (ReadTimeout even at 60s — network-level, not latency) |
| Template fallback (Krishi Bondhu) | Local, deterministic | `services/gemini_assistant.py` + `docs/knowledge/*.md` | **Live** (no key needed) | API chat tests (bn + en), irrelevant-question test, price-context test | Always labelled "template"; quotes retrieved notes with titles; never invents prices | Only as good as the 8 short notes; no reasoning beyond retrieval |
| RAG retrieval (TF-IDF / cosine, sklearn) | Local, sklearn | `services/rag.py` over `docs/knowledge/` | **Live** | Retrieval tests + live queries run in this audit | After the stop-words fix: irrelevant questions retrieve nothing; genuine bn/en queries retrieve the right doc first | Single-word overlap can still retrieve a doc; no minimum-score threshold; 8 docs only |
| sklearn RandomForest forecaster | Local, scikit-learn | `services/sklearn_forecast.py` | **Live** (on stored data) | 6 tests + real-data test | Works; backtested vs naive; honest `reliable` flag + warnings | Recursive multi-step forecasts drift; forecasts are only as real as the stored series (demo data → demo forecast, labelled) |
| Prophet forecaster | Local, Prophet 1.5.0 | `services/forecasting.py` | **Live** (on stored data) | 9 tests | Works; 3-fold rolling-origin backtest vs naive + seasonal-naive | Slow fits; optional dependency (503 when absent); same data caveat as sklearn |
| Vision sklearn baseline (RandomForest on colour/texture) | Local, scikit-learn | `services/vision.py` | **Not trained** — no model ships | Training/inference plumbing tests on synthetic fruit images | Plumbing works; untrained state returns 503, never a fake grade | **No trained model exists; no accuracy claim is possible or made.** Synthetic-image tests prove plumbing only |
| Vision PyTorch (ResNet18 / MobileNetV3) | Local, torch 2.15.0+cpu | `services/torch_vision.py`, `ai_services/computer_vision/` | **Not trained** — no checkpoint ships | Checkpoint loading, preprocessing parity, corrupt-checkpoint fallback, 1-epoch train + evaluate smoke tests | Pipeline works end-to-end on synthetic data | No trained checkpoint; PlantVillage gives disease labels only (no ripeness); lab-background photos degrade on farm photos (documented) |
| FAOSTAT producer prices | FAO bulk CSV download | `services/datasources/prices.py` | **Live** (verified on the real file) | Full-file parse: 3,889 rows, 2010-01 → 2023-12 | Parser correct; national monthly series, LCU/tonne → per-kg | Annual data also exists but is unused (too sparse); no daily local prices; Uganda has no monthly rows; newest data 2023-12 |
| World Bank Open Data | World Bank API v2 | `services/datasources/worldbank.py` | **Live** (slow) | Live population fetch OK; inflation fetch timed out twice at 20s, succeeded via curl in 21s | API works but is slow from this network; timeouts raised to 30s | Macro context only (inflation, agri % GDP) — not prices |
| OpenWeatherMap 5-day forecast | OpenWeather (key) | `services/datasources/openweather.py` | **Mocked** (live BLOCKED: no key) | Mocked parsing + speed-factor tests; malformed-body regression tests | Degrades to "weather unknown" without a key or on any failure | Free plan is 5-day forecast only; no history; live unverified |
| Open-Meteo weather | Open-Meteo (keyless) | `services/datasources/openmeteo.py` | **Live** | Live fetch for Dhaka + 11 mocked tests | Past 7 + today + next 7 in one call; missing data → None, never invented | Forecast API past days are model-based, not station observations (documented choice vs the ERA5 Archive API) |
| DAM Bangladesh prices | — | — | **NOT IMPLEMENTED** | Registry test | Correctly reports no public API; no endpoint invented | Manual ingestion only (see `docs/dam-prices.md`) |
| CGIAR Big Data | — | — | **NOT IMPLEMENTED** | Registry test | Manual CSV only; no API integrated | — |
| OR-Tools VRP solver | Local, OR-Tools | `services/ortools_routing.py` | **Live** (installed) | 11 tests incl. HTTP level | Capacity/time-window/refrigeration constraints enforced; real computed baseline | `max_transit_min` is accepted but not a hard constraint in the OR-Tools model (soft in the heuristic planner) |
| OSRM road routing | OSRM server (self-host / demo) | `services/logistics.py` `OSRMProvider` | **Mocked** (live BLOCKED: no server) | Mocked table-response tests; fallback test with closed port | Parsing + unreachable handling correct; fallback labelled | No live road distance verified; haversine × 1.35 detour is the default and is labelled an estimate |
| Digital Twin hash chain | Local (SHA-256 chain + HMAC + Merkle) | `services/twin.py` | **Live** | 12 twin + 8 twin-qr + 3 simulated-sensor tests, incl. executed tamper tests | Tamper-evidence works; simulated readings labelled everywhere | Tamper-*evidence*, not a blockchain: a DB owner could rewrite + recompute hashes; no external anchor exists yet (`LocalAnchor` only) |

## Bugs fixed in this audit (all with regression tests)

Regression tests that need a database could not be executed because of the
environment write flap (see the Environment notice); they are listed as
BLOCKED above and must be run by the coordinator's post-merge full run.
Non-DB regression tests all pass (13/13 in `test_audit_p78.py` + 3/3 Vitest).

1. **RAG retrieval grounded unrelated questions** (`rag.py`): no stop-word
   filtering let "What is the capital of France?" retrieve market-price
   notes at 0.25. Fixed with `stop_words="english"`; verified France → `[]`,
   genuine queries rank better. Tests: `test_assistant_irrelevant_question_invents_nothing`,
   `test_rag_retrieve_returns_tomato_doc` (existing, still passes).
2. **BatchView sensor chart never rendered** (`BatchView.tsx`, `api.ts`):
   timeline `temp_c` is a `{min,max,avg}` object; the component expected a
   number. Fixed to use the average; new Vitest tests (3 passed) + backend
   contract test.
3. **Matching crashed on zero price** (`matching.py`): unguarded division by
   `price_per_unit` (DB has no CHECK constraint). Now returns "no match".
4. **Matching `time_score` hardcoded to 100** (`matching.py`): now grades
   availability slack (100 / 50–100 / 50). Reasons are now dynamic and
   describe actual outcomes.
5. **World Bank timeouts too tight** (`worldbank.py`, `sync.py`): measured
   12–21s live latency vs 20s/10s timeouts → spurious ReadTimeouts. Both
   raised to 30s.
6. **World Bank malformed entries → 500** (`worldbank.py`): one bad row
   crashed `/forecast/context/{hub}`. Malformed entries are now skipped.
7. **OpenWeather malformed body → 500** (`openweather.py`): only
   `httpx.HTTPError` was caught. Malformed bodies/items now degrade to
   "weather unknown".
8. **Open-Meteo non-JSON body → 500** (`openmeteo.py`): `r.json()` ValueError
   uncaught. Now returns `None` (unavailable state).

## Files changed

| File | Why |
|---|---|
| `backend/app/services/rag.py` | Stop-words fix (bug 1) |
| `backend/app/services/matching.py` | Zero-price guard, graded time score, dynamic reasons (bugs 3–4) |
| `backend/app/services/datasources/worldbank.py` | 30s timeout, skip malformed entries (bugs 5–6) |
| `backend/app/services/datasources/sync.py` | Probe timeout 10 → 30s (bug 5) |
| `backend/app/services/datasources/openweather.py` | Malformed-body degradation (bug 7) |
| `backend/app/services/datasources/openmeteo.py` | Non-JSON body degradation (bug 8) |
| `backend/tests/test_audit_p78.py` | **New**: 23 audit regression tests |
| `frontend/src/components/BatchView.tsx` | Temp-object handling (bug 2) |
| `frontend/src/services/api.ts` | Timeline `temp_c` type corrected (bug 2) |
| `frontend/src/components/__tests__/batch-view.test.tsx` | **New**: 3 Vitest tests (bug 2) |
| `docs/audit/p7-8-section.md` | This file |

No new dependencies were added. No files outside the P7–8 areas were edited.

## Still UNVERIFIED / unfixed

- **10 new DB-backed tests BLOCKED by the environment write flap**
  (`sqlite3.OperationalError: disk I/O error` at fixture setup) — they
  must be executed in the coordinator's post-merge full run:
  `test_faostat_upsert_is_idempotent`,
  `test_sklearn_forecast_prefers_real_series`,
  `test_assistant_irrelevant_question_invents_nothing`,
  `test_assistant_status_without_key_is_honest`,
  `test_plan_haversine_labels_straight_line`,
  `test_optimize_osrm_failure_falls_back_to_haversine_labelled`,
  `test_plan_osrm_unconfigured_is_400_not_silent_fallback`,
  `test_twin_batch_codes_are_unique`,
  `test_twin_public_timeline_temp_is_summary_object`,
  `test_twin_tamper_breaks_chain_end_to_end`.
- **One unidentified failure** in the 90-test affected-suite batch (2nd of
  2 failures; the 1st was my FAOSTAT CSV quoting bug, fixed and re-verified).
  It occurred as the flap started and is likely environmental, but it was
  not identified — the rerun must confirm it clears.
- **Live Gemini** (no key; also blocked from the user's network) — mocked only.
- **Live OpenWeather** (no key) — mocked only.
- **Live OSRM** (no server) — mocked + fallback tested only.
- **Live MySQL / Docker / first PaaS deploy** — outside P7–8, still blocked per standing list.
- **Real-browser map fallback + weather chart** — Vitest/jsdom only (chart stubbed); needs a real browser check.
- **Scheduler firing on the clock** — not P7–8 scope (Phase 11–13 area).
- **Matching quality factor** — NOT IMPLEMENTED: no quality field on Product/Demand.
- **Matching distance** — district-level only (PARTIAL by design).
- **FAOSTAT Uganda** — no monthly producer-price rows exist in the source file; Kampala cannot get a FAOSTAT series.
- **`/plan` vs `/optimize` OSRM-failure behaviour differs** (502 vs labelled fallback) — documented, intentionally not changed.
- **OR-Tools `max_transit_min`** is not a hard constraint in the OR-Tools model (soft penalty only in the heuristic planner).

## Documentation suggestions (for the coordinator — audit did not edit guides)

- `LIMITATIONS.md` / `TEST_REPORT.md`: record that the World Bank API
  measured 12–21s from the build network and timeouts were raised to 30s;
  that FAOSTAT monthly data ends 2023-12 and Uganda has no monthly rows.
- `docs/API_AND_DEMO.md`: the public twin timeline `temp_c` is a
  `{min, max, avg}` object per seal (now documented in `api.ts`).
- `README.md` / demo pack: matching now scores availability slack and
  explains itself dynamically; quality is still not a matching factor.
