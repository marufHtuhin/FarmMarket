import base from "./playwright.config";

/**
 * Phase 11 (audit/p11-13) E2E override: identical to playwright.config.ts
 * except the backend + SPA run on port 8016 (the standard config uses
 * 8000, which other audit agents use). Run with:
 *   npx playwright test --config playwright.p1113.config.ts e2e/weather-prices.spec.ts
 * The specs themselves only use baseURL, so they also run unchanged under
 * the standard config.
 */
export default {
  ...base,
  use: {
    ...base.use,
    baseURL: "http://127.0.0.1:8016",
  },
  webServer: {
    command: "bash e2e/serve-p1113.sh",
    url: "http://127.0.0.1:8016/api/health",
    reuseExistingServer: true,
    timeout: 120_000,
  },
};
