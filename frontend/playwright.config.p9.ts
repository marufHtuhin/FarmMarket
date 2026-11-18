import { defineConfig } from "@playwright/test";

/**
 * Phase 9 (responsive UI audit) config.
 *
 * Runs ONLY frontend/e2e/responsive.spec.ts against an already-running
 * backend on port 8014 (the audit worktree's port — never 8000, which other
 * audit agents use). Start the server first, e.g.:
 *
 *   cd backend
 *   DATABASE_URL=sqlite:////tmp/p9-e2e.db SECRET_KEY=... python seed_demo.py
 *   DATABASE_URL=sqlite:////tmp/p9-e2e.db SECRET_KEY=... python -m uvicorn \
 *     app.main:app --host 127.0.0.1 --port 8014
 *
 * (frontend/dist must be built first: `npm run build` in frontend/.)
 * Override the base URL with P9_BASE_URL.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "responsive.spec.ts",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.P9_BASE_URL || "http://127.0.0.1:8014",
    channel: "chromium",
    trace: "on-first-retry",
  },
});
