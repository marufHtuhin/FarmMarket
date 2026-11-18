import { defineConfig } from "@playwright/test";

/**
 * FarmMarket E2E tests. The backend (uvicorn) serves the built React SPA from
 * frontend/dist on the same origin, so the whole stack is exercised through
 * http://127.0.0.1:8000.
 *
 * Prerequisites:
 *   1. npm run build          (builds frontend/dist for uvicorn to serve)
 *   2. npx playwright install chromium   (one-time browser download)
 * Then:  npx playwright test
 *
 * The webServer below starts the backend on a scratch SQLite DB seeded with
 * the demo users (farmer/buyer/transporter/admin @farmmarket.demo, Demo123!).
 * To run against a manually started server instead, start it yourself and
 * export PLAYWRIGHT_REUSE_SERVER=1 — the existing server on :8000 is reused.
 *
 * Port: override with E2E_PORT (e.g. E2E_PORT=8012) when :8000 is taken —
 * the webServer and baseURL follow it. Default is 8000.
 */
const E2E_PORT = process.env.E2E_PORT || "8000";
const BASE_URL = `http://127.0.0.1:${E2E_PORT}`;
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1, // tests share one scratch database — run sequentially
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    // Use the full Chromium build, not the headless shell: the shell download
    // fails in this VM's sandboxed network while the full build installs fine.
    // On a machine where the shell is installed, remove this line.
    channel: "chromium",
    trace: "on-first-retry",
  },
  webServer: {
    command: "bash e2e/serve.sh",
    url: `${BASE_URL}/api/health`,
    reuseExistingServer: true,
    timeout: 120_000,
    env: { E2E_PORT },
  },
});
