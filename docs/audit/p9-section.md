# Phase 9 — Responsive UI audit

Worktree `audit-p9` (branch `audit/p9`, based on git `163b4ee`). Backend on
port 8014, vite dev on 5114 (see "Environment notes"). Repeatable checks:
`frontend/e2e/responsive.spec.ts`, run with
`npx playwright test -c playwright.config.p9.ts` (server must already be
running; see the config header). The spec covers 6 viewports
(360 / 390 / 430 / 768 / 1024 / 1440 px) × 37 pages × 4 roles, plus 18
interaction (dead-button) tests and 12 screenshots.

Status labels: PASS / FAIL / BLOCKED / NOT IMPLEMENTED / PARTIAL.
**BLOCKED (environment)** means the VM-wide EPERM write flap (see below),
never an app defect.

## Results summary

| Run | Command | Result |
| --- | --- | --- |
| 390px matrix (pre-fix build) | `playwright test -c playwright.config.p9.ts -g "viewport 390px"` | 35 passed, 2 failed (both fixed since, see bugs 2–3) |
| Prices + Assistant × 6 viewports (after fixes 1–4) | `-g "(Prices\|Assistant) — layout"` | 12 passed |
| Full matrix, old build (before Weather fix) | `playwright test -c playwright.config.p9.ts` | 86 passed, 1 failed (Weather @ 360 — bug 5, fixed in source since); run killed at test 87/242 by the ~8 min exec cap |
| Full matrix, fixed build | — | BLOCKED (environment): Chromium itself is killed by the sandbox on launch (SIGTRAP, SI_KERNEL) — see "Environment notes" §5 |
| Weather — layout × 6 viewports (fixed build) | `-g "Weather — layout"` | BLOCKED (environment): same Chromium SIGTRAP; beforeAll auth was unblocked via minted JWTs (see §4) but no browser can start |

Per-viewport detail from the full run (old build):

| Viewport | Pages run | Passed | Failed |
| --- | --- | --- | --- |
| 360px | 37 / 37 | 36 | 1 — Weather (bug 5) |
| 390px | 37 / 37 | 37 | 0 |
| 430px | 13 / 37 (Landing → Farms) | 13 | 0 |
| 768px | 2 / 37 (Prices, Assistant only) | 2 | 0 |
| 1024px | 2 / 37 (Prices, Assistant only) | 2 | 0 |
| 1440px | 2 / 37 (Prices, Assistant only) | 2 | 0 |

Interaction tests (18) and screenshots (12): NOT RUN — BLOCKED
(environment): Chromium SIGTRAP on launch (see "Environment notes"
§5). The transform-cache and login blockers were both solved (§3–§4);
the browser itself is the remaining blocker.

## Bugs found and fixed

All fixes are CSS/layout (plus one `aria-label`); no backend or logic
changes. Each fix was re-verified by rerunning the affected spec subset
unless noted.

### 1. App topbar overflows at 360/390px — FIXED, verified
- **Symptom:** farmer dashboard @ 390px: `document scrollWidth 414px`;
  the user-menu button's right edge at 414px (logo + hamburger + language
  toggle + bell + user menu exceed the viewport).
- **Fix:** `frontend/src/components/layout/brand.tsx` — new `compact`
  prop on `Logo` hides the "FarmMarket" wordmark below 420px (icon stays);
  `AppLayout.tsx` topbar uses `<Logo compact />`. Sidebar / public header
  / footer keep the full wordmark.
- **Proof:** Dashboard (farmer) @ 360 and @ 390 PASS in the full run;
  all 4 dashboards PASS at 360/390/430.

### 2. Price-chart product select has no accessible label — FIXED, verified
- **Symptom:** Prices page: `select[type=select-one]` with no label /
  aria-label (the chart's product picker, `Prices.tsx:141`).
- **Fix:** added `aria-label={t("selectCropLabel")}` ("Select a crop").
- **Proof:** Prices PASS at all 6 viewports in the fix4 rerun.

### 3. Assistant chat-language select overflows at 390px — FIXED, verified
- **Symptom:** Assistant @ 390px: the language `<select>` measured
  `left=109 right=433`. Root cause: the shared `Select` field class sets
  `w-full`, which beats the `w-24` passed as `className` in Tailwind's
  stylesheet order.
- **Fix:** `frontend/src/pages/Assistant.tsx` — width moved to a wrapper
  `<div className="w-24 shrink-0">`; the select fills it. Only place in
  the app passing a width class to `Select`/`Input`.
- **Proof:** Assistant PASS at all 6 viewports in the fix4 rerun.

### 4. Bottom-nav "Marketplace" label overflows at 360px — FIXED, verified
- **Symptom:** @ 360px the first bottom-nav label measured `left=-3`:
  "Marketplace" (11px bold + padding ≈ 78px) exceeds its 72px grid cell,
  and as a flex item with default `min-width: auto` it cannot shrink, so
  `truncate` never engages.
- **Fix:** `frontend/src/components/layout/BottomNav.tsx` — label span
  gains `min-w-0 max-w-full` so it shrinks and truncates with an ellipsis.
- **Proof:** 360px full matrix PASS (36/37, only Weather failed); 360px
  Prices + Assistant PASS in the fix3 rerun.

### 5. Weather forecast rows overflow at 360px — FIXED, verification BLOCKED
- **Symptom:** Weather @ 360px: `document scrollWidth 388px`. The
  forecast day rows have five fixed columns (date 96 + temp ~91 + rain 64
  + chance 48 + 4×12 gaps ≈ 348px) against a 288px card width. The
  "Rain chance" header label (~70px) also overflowed its 48px column.
- **Fix:** `frontend/src/pages/Weather.tsx` — row/header gaps
  `gap-2 sm:gap-3`; date column `w-20 sm:w-24` (dates are short numeric
  strings, ~70px); rain-chance column hidden below 420px
  (`hidden min-[420px]:block`, header + rows); chance header label
  shortened to "Rain %" reusing the existing `wxRain` key (fits in both
  languages). Rain mm, temp range, condition glyph and date all remain
  visible on phones.
- **Proof:** NOT YET VERIFIED — the fix landed after the last green
  build; re-verification is blocked by the environment (Chromium
  SIGTRAP, see "Environment notes" §5). The fix was checked by
  arithmetic: at 360px the row now measures 80 (date) + ~91 (temp) +
  64 (rain) + 3×8 gaps = ~259px against a 288px card width (29px
  headroom); the rain-chance column is hidden below 420px. This
  arithmetic is supporting analysis only, NOT a test pass.

## Spec (test-harness) issues fixed along the way

These were defects in the audit harness, not the app:
- Leaflet's zoom `+`/`−` controls use `href="#"` by design — excluded
  from the dead-link check.
- Map markers / sidebar links below a scroll fold were flagged as
  "outside viewport" / "covered" — the checks now intersect each
  element's rect with its clipping ancestors (`visibleBox`), so only the
  actually visible part is judged.
- Images/tiles failing in the browser with
  `net::ERR_TUNNEL_CONNECTION_FAILED` are verified out-of-band with a
  direct fetch; URLs returning HTTP 200 are recorded as environmental
  (`env-image-fail`), not app bugs. All 7 Unsplash + Carto URLs flagged
  this way verified 200 via curl.
- Login rate limit (10/min/IP) vs per-test logins — tokens are now
  cached (in-memory + gitignored `e2e/.p9-tokens.json`, validated via
  `/auth/me`) with a 429 retry.
- Prices @ 1440 hit the 60s test timeout during URL verification —
  verification is now cached per URL with a shorter timeout, and layout
  tests get a 120s budget.

## Console-error findings

No JavaScript console errors and no uncaught page errors were recorded
on any page × viewport combination that ran (86 + 12 + 35 test runs).
The only console output was `Failed to load resource:
net::ERR_TUNNEL_CONNECTION_FAILED` for external images/tiles/fonts —
the VM egress proxy dropping tunnels (environmental; the same URLs
return HTTP 200 from curl/Node fetch). These are classified via
`requestfailed` events with URLs in `p9-results.json` (`env-*` kinds).

## Dead-button list

None found among the buttons exercised by the 18 interaction tests
(they are written and ready to run; execution is BLOCKED, see below).
Buttons covered: language toggle, auth links, marketplace search /
sort / card links, order + offer modals (open/close incl. Escape),
Message farmer, all five bottom-nav items, mobile drawer, user menu,
weather hub select, prices crop select, message send, mark-all-read,
assistant send, quality assess, admin price-entry submit, desktop
sidebar nav, notifications bell. No dead buttons were observed during
the layout runs either (every page's interactives passed the
clickability probe where run).

## Screenshots

`docs/audit/screenshots/` — 12 shots planned (landing, login,
marketplace, listing detail, weather, farmer dashboard × 1440 + 390,
JPEG q70, total budget < 5 MB). NOT CAPTURED yet — BLOCKED
(environment): the browser cannot start (Chromium SIGTRAP, see
"Environment notes" §5), and even if it could, the screenshot file
writes go through the poisoned Playwright worker process (see §3).
The screenshot tests are part of the spec and run automatically with
the full suite once the environment recovers.

## Environment notes (BLOCKED items, not app bugs)

1. **VM-wide EPERM write flap since ~07:54 UTC 17 Nov 2026**
   (coordinator notice). Root cause pinned down by experiment during
   this audit: **any read from the workspace mount, the network, or a
   pipe poisons ALL later file writes in the whole process group**
   (verified: a 1.2KB workspace read, a 2.8MB workspace read, a curl
   download, and a child process's workspace read each made the
   parent's next `writeFileSync` fail with EPERM; reads from `/tmp`
   and plain CPU/memory load do NOT poison). Consequences:
   - `vite build` fails (reads workspace sources, then cannot write
     `node_modules/.vite-temp`, `dist/`, or the workbox SW file).
     `dist/` was wiped by a failed build; the app is instead served
     for testing from the vite dev server on 5114 (see §2).
   - `npx` fails at startup (npm log-file write EPERM) — use the direct
     CLI: `node node_modules/@playwright/test/cli.js test ...`.
   - `git add`/`git commit` fail ("unable to write loose object
     file") — git reads the workspace, then cannot write objects.
     All P9 work is uncommitted on disk; see "Files changed".
   - The backend (uvicorn, started before the window) can no longer
     commit SQLite writes: **login returns HTTP 500** because it
     inserts a refresh-token row (`issue_refresh_token`). Any
     DB-backed flow (login, messaging, price entry) fails the same
     way — BLOCKED (environment), not FAIL. Read-only endpoints
     (`/auth/me`, `/products`, `/api/health`) still return 200.
   - The uvicorn access log stopped updating (the poisoned process
     cannot write its log file).
2. **Test serving:** the P9 backend (8014) serves the SPA from
   `frontend/dist` when a build exists; since the build is blocked,
   the vite dev server on 5114 (temp config `vite.config.p9.mjs`,
   NOT committed: plain-JS config + PWA stub + `optimizeDeps.disabled`
   + `/api` proxy → 8014, started with
   `node node_modules/vite/bin/vite.js --config vite.config.p9.mjs
   --configLoader native --port 5114 --host 127.0.0.1`) serves the
   fixed sources live. Run the spec with
   `P9_BASE_URL=http://127.0.0.1:5114`. Both servers were left running
   for the rerun (backend pid 4262, vite pid ~33416); the backend
   serves scratch SQLite `/tmp/p9-e2e.db` with
   `SECRET_KEY=p9-audit-secret-do-not-use-in-production`.
3. **Playwright transform cache — SOLVED.** Two separate traps:
   (a) the spec's cache entry was missing (0-byte `.map`); the
   Playwright process reads the workspace, so it cannot write its
   own cache. Solved by pre-populating the entry: the spec was
   transpiled+minified with the esbuild native binary (19,890
   bytes, sha1 `c9a0efd8756d63b8309e07fd6b4d60eb10eae468`), carried
   through the agent context in 5 verified slices (all slice sha1s
   matched), and written to
   `/tmp/playwright-transform-cache-0/de/de3574aacb_3df48c0_responsivespec.js`
   with the `// <sha1>` header by a clean process (reads `/tmp`
   only). Entry name verified against Playwright's hash formula
   (`esm` + content + path + `1.65.1` + `define` +
   `{"jsx":"react-jsx"}`); header verified with Playwright's own
   `calculateSha1`. (b) `TMPDIR=~/workspace/farmmarket/.tmp` (from
   the pytest instructions) redirects Playwright's cache to
   `~/workspace/farmmarket/.tmp/playwright-transform-cache-0`,
   where no entries exist — **do NOT set TMPDIR when running
   Playwright**; the default `/tmp` cache has all three entries
   (config `5a9d5548fb`, helpers `68af916f20`, spec `de3574aacb`).
   Proof: `playwright test -c playwright.config.p9.ts --list`
   enumerates all 242 tests. The `.map` file is not required
   (Playwright's cache-read path never reads it).
4. **Login 500 — WORKED AROUND with minted JWTs.** The spec's
   `beforeAll` needs 4 role tokens; login is 500 (see §1). Real
   HS256 tokens were minted directly with the audit SECRET_KEY
   (`{"sub": user_id, "exp": now+4h}`, ids farmer=1, buyer=2,
   transporter=11, admin=12 from the scratch DB) and written to the
   gitignored `frontend/e2e/.p9-tokens.json` (savedAt 2026-11-17
   ~08:39 UTC). Verified: `/api/v1/auth/me` with the minted farmer
   token returns 200 with the farmer's profile. Caveat: the spec
   trusts the file for 50 min (until ~09:29 UTC); after that
   `beforeAll` re-attempts login. Re-mint with the same one-liner
   (see "What remains") or rerun once the window clears (login will
   work again). The tokens are for the scratch DB + throwaway
   secret only and are gitignored — never commit them.
5. **Chromium cannot start — BLOCKER, no workaround.** Since the
   window opened, headless Chromium is killed during startup:
   `process did exit: exitCode=null, signal=SIGTRAP` (Playwright
   log) and strace shows `SIGTRAP {si_signo=SIGTRAP,
   si_code=SI_KERNEL}` right after opening `/proc/self/mem`,
   i.e. the OUTER sandbox (kernel seccomp) traps a syscall Chrome
   makes in early init. `chrome --version` still works; any
   headless run (`--dump-dom`, Playwright launch) dies silently
   in <100ms. Chrome flags cannot bypass an outer seccomp policy
   (`--no-sandbox` is already passed by Playwright), and no other
   browser is installed. This blocks ALL remaining browser
   verification (Weather fix, 430/768/1024/1440 matrix, 18
   interaction tests, screenshots) until the environment recovers.
   It worked before ~07:54 UTC (86 tests ran green) and is purely
   environmental.
6. **Exec cap:** background exec commands are killed after ~8 min;
   the full spec (~20 min) must be split per viewport (each ~2–4
   min) or launched detached. Note: a detached Playwright run
   cannot redirect its stdout to a file (the poisoned worker's
   writes fail) — run in the foreground and capture via the tool,
   or wait for the window to clear.
7. **External images in-browser:** Unsplash/Carto/Open-Meteo are
   reachable from the VM (curl 200), but Chromium's proxy tunnels
   drop intermittently — see "Console-error findings".
8. **Spec's own file writes fail under the window:** the `afterAll`
   `p9-results.json` write (no try/catch) throws EPERM at the end
   of every run — this does NOT invalidate the test results, but
   `p9-results.json` stays 0 bytes and the run exits non-zero.
   The token-cache write is try/catch'd (fails silently). The
   screenshot tests' JPEG writes would fail the same way.

## Files changed

- `frontend/src/components/layout/brand.tsx` — `Logo compact` prop (bug 1)
- `frontend/src/components/layout/AppLayout.tsx` — topbar uses `<Logo compact />` (bug 1)
- `frontend/src/pages/Prices.tsx` — chart-select aria-label (bug 2)
- `frontend/src/pages/Assistant.tsx` — language-select wrapper (bug 3)
- `frontend/src/components/layout/BottomNav.tsx` — label `min-w-0` (bug 4)
- `frontend/src/pages/Weather.tsx` — forecast-row responsive fix (bug 5)
- `frontend/e2e/responsive.spec.ts` — NEW: viewport matrix + interactions + screenshots
- `frontend/playwright.config.p9.ts` — NEW: P9 config (port 8014, `P9_BASE_URL` override)
- `frontend/e2e/.p9-tokens.json` — gitignored token cache (test-only);
  currently holds minted JWTs (see §4), valid ~4h from 08:39 UTC
- `.gitignore` — ignore `frontend/e2e/.p9-tokens.json`
- `docs/audit/p9-section.md` — this file
- `docs/audit/p9-results.json` — 0 bytes: the spec's `afterAll` write
  fails with EPERM under the window; a completed run after recovery
  will populate it (242 entries)
- `docs/audit/screenshots/` — pending (BLOCKED)

Temporary, NOT committed (delete after the audit):
`frontend/vite.config.p9.mjs` (still needed by the running dev server —
delete only after the rerun), `/tmp/p9-*.log`, `/tmp/p9-*.mjs`,
`/tmp/p9-min.mjs`, `/tmp/playwright-transform-cache-0/de/de3574aacb_3df48c0_responsivespec.js`
(cache entry — regenerable; keep until the rerun completes).

## What remains UNVERIFIED / unfixed

All items below are BLOCKED on the Chromium SIGTRAP (§5), not on the
app. The test infrastructure is ready: the transform cache is
populated, minted tokens are in place (until ~09:29 UTC file trust;
JWTs valid to ~12:39 UTC), and both servers are running. Rerun once
the environment recovers (verify first with
`chrome --headless --dump-dom about:blank` — it must print HTML,
not exit silently):

```sh
cd ~/workspace/farmmarket/audit-p9/frontend
# NO TMPDIR override (see §3); servers already on 8014 + 5114
P9_BASE_URL=http://127.0.0.1:5114 node node_modules/@playwright/test/cli.js test -c playwright.config.p9.ts -g "Weather — layout"   # bug 5, 6 tests
P9_BASE_URL=http://127.0.0.1:5114 node node_modules/@playwright/test/cli.js test -c playwright.config.p9.ts -g "viewport 430px"    # 37 tests
P9_BASE_URL=http://127.0.0.1:5114 node node_modules/@playwright/test/cli.js test -c playwright.config.p9.ts -g "viewport 768px"    # 37 tests
P9_BASE_URL=http://127.0.0.1:5114 node node_modules/@playwright/test/cli.js test -c playwright.config.p9.ts -g "viewport 1024px"   # 37 tests
P9_BASE_URL=http://127.0.0.1:5114 node node_modules/@playwright/test/cli.js test -c playwright.config.p9.ts -g "viewport 1440px"  # 37 tests
P9_BASE_URL=http://127.0.0.1:5114 node node_modules/@playwright/test/cli.js test -c playwright.config.p9.ts -g "interactions"      # 18 tests
P9_BASE_URL=http://127.0.0.1:5114 node node_modules/@playwright/test/cli.js test -c playwright.config.p9.ts -g "screenshots"      # 12 shots
# or the whole suite at once (~20 min; run detached or accept the exec cap):
P9_BASE_URL=http://127.0.0.1:5114 node node_modules/@playwright/test/cli.js test -c playwright.config.p9.ts
```

- Weather fix (bug 5) at all viewports — needs one green run of
  `Weather — layout`.
- Full matrix at 768 / 1024 / 1440 and 430 beyond Farms.
- All 18 interaction tests (dead-button checks).
- 12 screenshots (total must stay < 5 MB — check with
  `du -sb docs/audit/screenshots/` before committing).
- If the rerun happens after ~09:29 UTC and login still 500s,
  re-mint tokens first (ids farmer=1, buyer=2, transporter=11,
  admin=12; secret `p9-audit-secret-do-not-use-in-production`):
  `~/workspace/farmmarket/.venv/bin/python -c "from jose import jwt; ..."` —
  see §4; then update `savedAt` in `e2e/.p9-tokens.json`.
  If the window has cleared, login works and `beforeAll` re-logins
  normally (no minting needed).
- Vitest baseline (52 tests) was NOT rerun: `vitest run` fails at
  startup with the same EPERM (vite config load writes a temp file).
  BLOCKED (environment). The P9 changes are CSS-only + one
  `aria-label` using an existing i18n key; no logic touched.
- `git commit` of the above files (BLOCKED by EPERM; coordinator to
  handle centrally). Uncommitted: the 6 source fixes, the spec,
  the config, `.gitignore`, `p9-section.md`.

## Doc suggestions (for other phases — not edited per constraints)

- `TEST_REPORT.md`: add the P9 matrix + the five responsive bugs.
- `LIMITATIONS.md`: note the Weather rain-chance column is hidden below
  420px viewports by design.
