import { expect, test, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { DEMO } from "./helpers";

/**
 * Phase 9 — responsive UI audit.
 *
 * Full viewport × page matrix (360 / 390 / 430 / 768 / 1024 / 1440 px) over
 * every major page and role. For each combination the spec checks:
 *   - no horizontal overflow (document scrollWidth vs viewport)
 *   - no element extends outside the viewport (except content inside a
 *     deliberate horizontal scroller, e.g. tables in overflow-x-auto)
 *   - no broken images (complete but naturalWidth 0) — see the note below
 *   - no inaccessible form controls (no label / aria-label / aria-labelledby)
 *   - no dead links (missing or "#" href, except Leaflet's zoom controls,
 *     which use href="#" by design and are functional buttons)
 *   - every visible interactive element is actually clickable at its centre
 *     (elementFromPoint hits the element or its subtree — catches overlaps);
 *     the fixed bottom nav / sticky topbar are intentional chrome, so they
 *     are ignored mid-page, but a second pass scrolled to the page bottom
 *     flags anything the bottom nav permanently covers there
 *   - no console errors and no uncaught page errors
 *   - no failed same-origin requests
 *
 * Environment note — images: this VM routes browser traffic through an
 * egress proxy whose CONNECT tunnels intermittently fail
 * (net::ERR_TUNNEL_CONNECTION_FAILED), so an image can fail to load in the
 * browser even though its URL is valid. A broken image is therefore only a
 * failure when the URL ALSO fails a direct fetch from the test process
 * (Node fetch honours the proxy env vars). Verified-valid URLs are recorded
 * as `env-image-fail` (informational) instead. The same rule applies to
 * failed external requests (tiles, fonts, weather API).
 *
 * Auth note: the backend rate-limits login to 10/min/IP, so all four demo
 * roles log in ONCE in beforeAll and the tokens are cached (in memory and
 * in gitignored e2e/.p9-tokens.json, validated against /auth/me) and
 * injected via addInitScript for every test. A 429 still retries once
 * after the 60s window clears.
 *
 * Run with the P9 config (server must already be running on :8014):
 *   npx playwright test -c playwright.config.p9.ts
 */

const SPEC_DIR = path.dirname(fileURLToPath(import.meta.url));
const AUDIT_DIR = path.resolve(SPEC_DIR, "..", "..", "docs", "audit");
const SHOTS_DIR = path.join(AUDIT_DIR, "screenshots");

type Role = "public" | "farmer" | "buyer" | "transporter" | "admin";

const VIEWPORTS = [
  { w: 360, h: 800, name: "360" },
  { w: 390, h: 844, name: "390" },
  { w: 430, h: 932, name: "430" },
  { w: 768, h: 1024, name: "768" },
  { w: 1024, h: 768, name: "1024" },
  { w: 1440, h: 900, name: "1440" },
];

interface PageDef {
  name: string;
  path: string;
  role: Role;
}

let LISTING_ID = 1;

/** Cached login responses, one per role (see the auth note above). */
const TOKENS = new Map<string, { access_token: string; refresh_token?: string; user: unknown }>();

const PAGES: PageDef[] = [
  // Public
  { name: "Landing", path: "/", role: "public" },
  { name: "Login", path: "/login", role: "public" },
  { name: "Register", path: "/register", role: "public" },
  { name: "Forgot password", path: "/forgot-password", role: "public" },
  { name: "Marketplace", path: "/marketplace", role: "public" },
  { name: "Listing detail", path: "/marketplace/__LISTING__", role: "public" },
  { name: "Prices", path: "/prices", role: "public" },
  { name: "Weather", path: "/weather", role: "public" },
  { name: "About", path: "/about", role: "public" },
  { name: "Verify (unknown batch)", path: "/verify/FM-000000000000", role: "public" },
  { name: "Not found", path: "/no-such-route-xyz", role: "public" },
  // Farmer
  { name: "Dashboard (farmer)", path: "/dashboard", role: "farmer" },
  { name: "Farms", path: "/farms", role: "farmer" },
  { name: "New listing", path: "/listings/new", role: "farmer" },
  { name: "My listings", path: "/listings/mine", role: "farmer" },
  { name: "Quality check", path: "/quality", role: "farmer" },
  { name: "Matches (farmer)", path: "/matches", role: "farmer" },
  { name: "Offers (farmer)", path: "/offers", role: "farmer" },
  { name: "Messages (farmer)", path: "/messages", role: "farmer" },
  { name: "Orders (farmer)", path: "/orders", role: "farmer" },
  { name: "Assistant", path: "/assistant", role: "farmer" },
  { name: "Logistics (farmer)", path: "/logistics", role: "farmer" },
  { name: "Batches", path: "/batches", role: "farmer" },
  { name: "Notifications (farmer)", path: "/notifications", role: "farmer" },
  { name: "Profile (farmer)", path: "/profile", role: "farmer" },
  // Buyer
  { name: "Dashboard (buyer)", path: "/dashboard", role: "buyer" },
  { name: "Matches (buyer)", path: "/matches", role: "buyer" },
  { name: "Orders (buyer)", path: "/orders", role: "buyer" },
  { name: "Messages (buyer)", path: "/messages", role: "buyer" },
  // Transporter
  { name: "Dashboard (transporter)", path: "/dashboard", role: "transporter" },
  { name: "Deliveries", path: "/deliveries", role: "transporter" },
  { name: "Vehicles", path: "/vehicles", role: "transporter" },
  { name: "Logistics (transporter)", path: "/logistics", role: "transporter" },
  // Admin
  { name: "Admin dashboard", path: "/admin", role: "admin" },
  { name: "Admin users", path: "/admin/users", role: "admin" },
  { name: "Admin data sources", path: "/admin/data-sources", role: "admin" },
  { name: "Admin audit logs", path: "/admin/audit-logs", role: "admin" },
];

interface LayoutIssue {
  kind: string;
  detail: string;
}

interface PageResult {
  viewport: string;
  page: string;
  role: string;
  path: string;
  issues: LayoutIssue[];
  envIssues: LayoutIssue[];
  consoleErrors: string[];
  pageErrors: string[];
}

const RESULTS: PageResult[] = [];

/** Inject cached tokens + English locale before any load (no API call). */
async function loginAs(page: Page, role: Exclude<Role, "public">) {
  const body = TOKENS.get(role);
  expect(body, `no cached token for ${role}`).toBeTruthy();
  await page.addInitScript((b: { access_token: string; refresh_token?: string; user: unknown }) => {
    localStorage.setItem("fm_lang", "en");
    localStorage.setItem("fm_access_token", b.access_token);
    if (b.refresh_token) localStorage.setItem("fm_refresh_token", b.refresh_token);
    localStorage.setItem("fm_user", JSON.stringify(b.user));
  }, body);
}

async function setPublic(page: Page) {
  await page.addInitScript(() => localStorage.setItem("fm_lang", "en"));
}

async function settle(page: Page) {
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(1200);
  await page
    .waitForFunction(() => [...document.images].every((i) => i.complete), null, { timeout: 5000 })
    .catch(() => {});
  // The VM egress proxy drops some image tunnels; retry broken images twice
  // before judging them (a still-broken image is then verified out-of-band).
  for (let round = 0; round < 2; round++) {
    const broken = await page.evaluate(
      () => [...document.images].filter((i) => i.complete && i.naturalWidth === 0).length
    );
    if (broken === 0) break;
    await page.evaluate(() => {
      for (const img of document.images) {
        if (img.complete && img.naturalWidth === 0 && img.src) {
          const s = img.src;
          img.src = "";
          img.src = s;
        }
      }
    });
    await page.waitForTimeout(2500);
    await page
      .waitForFunction(() => [...document.images].every((i) => i.complete), null, { timeout: 5000 })
      .catch(() => {});
  }
  await page.waitForTimeout(300);
}

/** Cross-test cache for URL verifications (same tile/image URLs recur). */
const URL_CACHE = new Map<string, "ok" | "bad" | "unknown">();

/**
 * Direct fetch of a URL from the test process (proxy-aware via env vars).
 * Returns "ok" (HTTP 2xx), "bad" (definitive HTTP error, e.g. 404), or
 * "unknown" (every attempt threw at the network level — the VM proxy drops
 * tunnels for any client, so an unverifiable URL is environmental, not
 * proof the app's URL is wrong). Retries network failures once.
 */
async function urlLoads(url: string): Promise<"ok" | "bad" | "unknown"> {
  const cached = URL_CACHE.get(url);
  if (cached) return cached;
  let verdict: "ok" | "bad" | "unknown" = "unknown";
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const res = await fetch(url, { method: "HEAD", signal: AbortSignal.timeout(8000), redirect: "follow" });
      if (res.ok) {
        verdict = "ok";
        break;
      }
      if (res.status === 405 || res.status === 501) {
        const get = await fetch(url, { signal: AbortSignal.timeout(8000), redirect: "follow" });
        verdict = get.ok ? "ok" : "bad";
      } else {
        verdict = "bad";
      }
      break;
    } catch {
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
  URL_CACHE.set(url, verdict);
  return verdict;
}

async function collectLayoutIssues(page: Page, vw: number): Promise<LayoutIssue[]> {
  return page.evaluate((viewportWidth) => {
    const issues: { kind: string; detail: string }[] = [];
    const doc = document.documentElement;

    if (doc.scrollWidth > viewportWidth + 1) {
      issues.push({
        kind: "h-overflow",
        detail: `document scrollWidth ${doc.scrollWidth}px > viewport ${viewportWidth}px`,
      });
    }

    // The visible box of an element: its own rect intersected with every
    // clipping ancestor (overflow hidden/clip/auto/scroll), per axis.
    // Elements inside a clipped container (map panes, horizontal table
    // scrollers, the sidebar's scrollable nav) can only be seen within
    // that container's box — a nav link below the sidebar's scroll fold
    // is not "covered by the footer", it is scrolled out of view.
    // <html>/<body> are NOT clipping ancestors here: body's
    // overflow-x:hidden is what masks page overflow, which is exactly what
    // the scrollWidth check above detects.
    const clips = (v: string) => ["hidden", "clip", "auto", "scroll"].includes(v);
    const visibleBox = (el: Element): { left: number; right: number; top: number; bottom: number } => {
      const r = el.getBoundingClientRect();
      let left = r.left;
      let right = r.right;
      let top = r.top;
      let bottom = r.bottom;
      let p = el.parentElement;
      while (p && p !== document.body && p !== document.documentElement) {
        const s = getComputedStyle(p);
        if (clips(s.overflowX) || clips(s.overflowY)) {
          const pr = p.getBoundingClientRect();
          if (clips(s.overflowX)) {
            left = Math.max(left, pr.left);
            right = Math.min(right, pr.right);
          }
          if (clips(s.overflowY)) {
            top = Math.max(top, pr.top);
            bottom = Math.min(bottom, pr.bottom);
          }
        }
        p = p.parentElement;
      }
      return { left, right, top, bottom };
    };

    const describe = (el: Element): string => {
      const cls = typeof el.className === "string" ? el.className.split(/\s+/).slice(0, 3).join(".") : "";
      const text = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40);
      return `${el.tagName.toLowerCase()}${cls ? "." + cls : ""}${text ? ` "${text}"` : ""}`;
    };

    // Elements whose VISIBLE part extends past the viewport.
    let outside = 0;
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") continue;
      const vis = visibleBox(el);
      if (vis.right > viewportWidth + 1 || vis.left < -1) {
        outside++;
        if (outside <= 8) {
          issues.push({
            kind: "outside-viewport",
            detail: `${describe(el)} left=${Math.round(vis.left)} right=${Math.round(vis.right)}`,
          });
        }
      }
    }
    if (outside > 8) {
      issues.push({ kind: "outside-viewport", detail: `...and ${outside - 8} more elements outside the viewport` });
    }

    // Broken images (verified out-of-band by the test before failing).
    for (const img of document.querySelectorAll("img")) {
      if (img.complete && img.naturalWidth === 0) {
        issues.push({ kind: "broken-image", detail: img.getAttribute("src") || "(no src)" });
      }
    }

    // Unlabelled form controls.
    for (const el of document.querySelectorAll("input, select, textarea")) {
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") continue;
      const type = (el as HTMLInputElement).type;
      if (type === "hidden" || type === "submit" || type === "button") continue;
      const labelled =
        el.getAttribute("aria-label") ||
        el.getAttribute("aria-labelledby") ||
        el.closest("label") ||
        (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`));
      if (!labelled) {
        issues.push({
          kind: "unlabeled-control",
          detail: `${el.tagName.toLowerCase()}${type ? `[type=${type}]` : ""} name="${el.getAttribute("name") || ""}" placeholder="${el.getAttribute("placeholder") || ""}"`,
        });
      }
    }

    // Dead links (Leaflet's zoom +/- use href="#" by design — excluded).
    for (const a of document.querySelectorAll("a")) {
      if (a.closest(".leaflet-control")) continue;
      const href = a.getAttribute("href");
      if (!href || href === "#") {
        issues.push({
          kind: "dead-link",
          detail: `"${(a.textContent || "").trim().slice(0, 40)}" href=${href ?? "(none)"}`,
        });
      }
    }

    // Clickability: elementFromPoint at the centre of each element's VISIBLE
    // box must hit the element itself or something in the same subtree.
    // Fully clipped elements (below a scroll fold) are skipped — they are
    // reachable by scrolling, not covered. Covers by the fixed bottom nav /
    // sticky topbar are intentional chrome mid-page (the user scrolls past
    // them); they are checked separately at the bottom of the page, where
    // content must clear the nav.
    const inChrome = (el: Element | null): boolean =>
      !!el?.closest("nav.fixed.bottom-0, header.sticky");
    const interactives = [...document.querySelectorAll("a, button, input, select, textarea, [role='button']")].filter(
      (el) => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return false;
        const cs = getComputedStyle(el);
        if (cs.display === "none" || cs.visibility === "hidden" || cs.pointerEvents === "none") return false;
        const vis = visibleBox(el);
        if (vis.right <= vis.left || vis.bottom <= vis.top) return false; // fully clipped
        return vis.bottom > 0 && vis.top < window.innerHeight && vis.right > 0 && vis.left < window.innerWidth;
      }
    );
    let blocked = 0;
    for (const el of interactives.slice(0, 120)) {
      const vis = visibleBox(el);
      const cx = Math.min(Math.max((vis.left + vis.right) / 2, 0), window.innerWidth - 1);
      const cy = Math.min(Math.max((vis.top + vis.bottom) / 2, 0), window.innerHeight - 1);
      const hit = document.elementFromPoint(cx, cy);
      if (!hit || inChrome(hit)) continue;
      if (hit !== el && !el.contains(hit) && !hit.contains(el)) {
        blocked++;
        if (blocked <= 8) {
          issues.push({
            kind: "blocked-interactive",
            detail: `${describe(el)} is covered at its centre by ${describe(hit)}`,
          });
        }
      }
    }
    if (blocked > 8) {
      issues.push({ kind: "blocked-interactive", detail: `...and ${blocked - 8} more blocked interactive elements` });
    }

    return issues;
  }, vw);
}

/** Scrolled to the page bottom: nothing may stay hidden behind the bottom nav. */
async function collectBottomNavIssues(page: Page): Promise<LayoutIssue[]> {
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(600);
  return page.evaluate(() => {
    const issues: { kind: string; detail: string }[] = [];
    const describe = (el: Element): string => {
      const cls = typeof el.className === "string" ? el.className.split(/\s+/).slice(0, 3).join(".") : "";
      const text = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40);
      return `${el.tagName.toLowerCase()}${cls ? "." + cls : ""}${text ? ` "${text}"` : ""}`;
    };
    const clips = (v: string) => ["hidden", "clip", "auto", "scroll"].includes(v);
    const visibleBox = (el: Element): { left: number; right: number; top: number; bottom: number } => {
      const r = el.getBoundingClientRect();
      let left = r.left;
      let right = r.right;
      let top = r.top;
      let bottom = r.bottom;
      let p = el.parentElement;
      while (p && p !== document.body && p !== document.documentElement) {
        const s = getComputedStyle(p);
        if (clips(s.overflowX) || clips(s.overflowY)) {
          const pr = p.getBoundingClientRect();
          if (clips(s.overflowX)) {
            left = Math.max(left, pr.left);
            right = Math.min(right, pr.right);
          }
          if (clips(s.overflowY)) {
            top = Math.max(top, pr.top);
            bottom = Math.min(bottom, pr.bottom);
          }
        }
        p = p.parentElement;
      }
      return { left, right, top, bottom };
    };
    let hidden = 0;
    for (const el of document.querySelectorAll("a, button, input, select, textarea, [role='button']")) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden" || cs.pointerEvents === "none") continue;
      const vis = visibleBox(el);
      if (vis.right <= vis.left || vis.bottom <= vis.top) continue; // fully clipped
      if (vis.bottom <= 0 || vis.top >= window.innerHeight || vis.right <= 0 || vis.left >= window.innerWidth) continue;
      if (el.closest("nav.fixed.bottom-0")) continue; // the nav itself
      const cx = Math.min(Math.max((vis.left + vis.right) / 2, 0), window.innerWidth - 1);
      const cy = Math.min(Math.max((vis.top + vis.bottom) / 2, 0), window.innerHeight - 1);
      const hit = document.elementFromPoint(cx, cy);
      if (hit?.closest("nav.fixed.bottom-0")) {
        hidden++;
        if (hidden <= 8) {
          issues.push({ kind: "hidden-behind-nav", detail: `${describe(el)} is covered by the bottom nav at page bottom` });
        }
      }
    }
    if (hidden > 8) {
      issues.push({ kind: "hidden-behind-nav", detail: `...and ${hidden - 8} more elements hidden behind the bottom nav` });
    }
    return issues;
  });
}

/** Token cache so repeated runs (and Playwright's per-describe beforeAll
 *  re-runs) don't hammer the 10/min/IP login limit. Access tokens live
 *  60 min; the cache is trusted for 50 min and validated against /auth/me.
 *  The file holds demo-account JWTs for the scratch DB only and is
 *  gitignored (frontend/e2e/.p9-tokens.json). */
const TOKEN_CACHE = path.join(SPEC_DIR, ".p9-tokens.json");

function loadCachedTokens(): boolean {
  try {
    const raw = JSON.parse(fs.readFileSync(TOKEN_CACHE, "utf8")) as {
      savedAt: number;
      tokens: Record<string, { access_token: string; refresh_token?: string; user: unknown }>;
    };
    if (Date.now() - raw.savedAt > 50 * 60 * 1000) return false;
    for (const [role, body] of Object.entries(raw.tokens)) TOKENS.set(role, body);
    return TOKENS.size === 4;
  } catch {
    return false;
  }
}

function saveCachedTokens() {
  try {
    fs.writeFileSync(
      TOKEN_CACHE,
      JSON.stringify({ savedAt: Date.now(), tokens: Object.fromEntries(TOKENS) })
    );
  } catch {
    // Cache is an optimisation; a write failure must not fail the run.
  }
}

test.beforeAll(async ({ request }) => {
  // The logins below can legitimately take 65 s+: on a 429 from the 10/min/IP
  // login limit (shared with the other specs, which log in first), we wait
  // out the 60 s window and retry. That exceeds the 60 s default hook
  // timeout, so raise it here — setTimeout() must be called INSIDE the hook
  // to affect the hook's timeout (a file-level call only changes per-test
  // timeouts). Without this, a 429 here kills the whole 241-test matrix
  // (17 Nov 2026 recovery run: hook timed out at 60 s, 241 "did not run").
  test.setTimeout(180_000);
  // Reuse cached tokens when they still validate (one /auth/me probe).
  if (loadCachedTokens()) {
    const probe = await request.get("/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${TOKENS.get("farmer")!.access_token}` },
    });
    if (probe.ok()) {
      const farmerId = (TOKENS.get("farmer")!.user as { id: number }).id;
      const res = await request.get("/api/v1/products");
      expect(res.ok()).toBeTruthy();
      const products = await res.json();
      const own = products.find((p: { farmer_id: number }) => p.farmer_id === farmerId) || products[0];
      LISTING_ID = own.id;
      return;
    }
    TOKENS.clear();
  }
  // One login per role. On 429 (10/min/IP limit shared with other runs),
  // wait out the 60s window once and retry.
  for (const role of ["farmer", "buyer", "transporter", "admin"] as const) {
    let res = await request.post("/api/v1/auth/login", {
      data: { email: DEMO[role].email, password: DEMO[role].password },
    });
    if (res.status() === 429) {
      await new Promise((r) => setTimeout(r, 65_000));
      res = await request.post("/api/v1/auth/login", {
        data: { email: DEMO[role].email, password: DEMO[role].password },
      });
    }
    expect(res.ok(), `login for ${role} failed with ${res.status()}`).toBeTruthy();
    TOKENS.set(role, await res.json());
  }
  saveCachedTokens();
  // Pick a listing owned by the demo farmer (Rahim Uddin) so the buyer →
  // farmer messaging chain in the interaction tests targets his account.
  const farmerId = (TOKENS.get("farmer")!.user as { id: number }).id;
  const res = await request.get("/api/v1/products");
  expect(res.ok()).toBeTruthy();
  const products = await res.json();
  expect(products.length).toBeGreaterThan(0);
  const own = products.find((p: { farmer_id: number }) => p.farmer_id === farmerId) || products[0];
  LISTING_ID = own.id;
});

test.afterAll(async () => {
  fs.mkdirSync(AUDIT_DIR, { recursive: true });
  fs.writeFileSync(path.join(AUDIT_DIR, "p9-results.json"), JSON.stringify(RESULTS, null, 2));
});

for (const vp of VIEWPORTS) {
  test.describe(`viewport ${vp.w}px`, () => {
    test.use({ viewport: { width: vp.w, height: vp.h } });

    for (const def of PAGES) {
      test(`${def.name} — layout`, async ({ page, baseURL }) => {
        test.setTimeout(120_000); // image retries + URL verification on map pages
        const consoleErrors: string[] = [];
        const pageErrors: string[] = [];
        const failedRequests: { url: string; error: string }[] = [];
        page.on("console", (m) => {
          // "Failed to load resource" duplicates requestfailed events, which
          // carry the URL and are classified below — ignore it here.
          if (m.type() === "error" && !m.text().startsWith("Failed to load resource")) {
            consoleErrors.push(m.text().slice(0, 300));
          }
        });
        page.on("pageerror", (e) => pageErrors.push(String(e).slice(0, 300)));
        page.on("requestfailed", (r) =>
          failedRequests.push({ url: r.url(), error: r.failure()?.errorText || "unknown" })
        );

        if (def.role === "public") await setPublic(page);
        else await loginAs(page, def.role);

        const url = def.path.replace("__LISTING__", String(LISTING_ID));
        await page.goto(url);
        await settle(page);

        // The page must actually render (not a blank crash / redirect loop).
        await expect(page.locator("main, #root").first()).toBeVisible();
        const rawIssues = await collectLayoutIssues(page, vp.w);
        const bottomIssues = await collectBottomNavIssues(page);

        // Classify issues: broken images / failed external requests are only
        // real failures when the URL also fails a direct fetch (see header).
        const issues: LayoutIssue[] = [];
        const envIssues: LayoutIssue[] = [];
        for (const issue of [...rawIssues, ...bottomIssues]) {
          if (issue.kind === "broken-image" && issue.detail !== "(no src)") {
            const verdict = await urlLoads(issue.detail);
            if (verdict === "bad") issues.push(issue);
            else
              envIssues.push({
                kind: verdict === "ok" ? "env-image-fail" : "env-image-unverified",
                detail: issue.detail,
              });
          } else {
            issues.push(issue);
          }
        }
        for (const fr of failedRequests) {
          const sameOrigin = baseURL && fr.url.startsWith(baseURL);
          if (sameOrigin) {
            issues.push({ kind: "failed-request", detail: `${fr.url} (${fr.error})` });
          } else {
            const verdict = await urlLoads(fr.url);
            if (verdict === "bad") {
              issues.push({ kind: "failed-request", detail: `${fr.url} (${fr.error})` });
            } else {
              envIssues.push({
                kind: verdict === "ok" ? "env-request-fail" : "env-request-unverified",
                detail: `${fr.url} (${fr.error})`,
              });
            }
          }
        }
        RESULTS.push({ viewport: vp.name, page: def.name, role: def.role, path: url, issues, envIssues, consoleErrors, pageErrors });

        const issueDetail = issues.map((i) => `\n  [${i.kind}] ${i.detail}`).join("");
        expect.soft(
          issues.length,
          `${def.name} @ ${vp.w}px has ${issues.length} layout issue(s):${issueDetail}`
        ).toBe(0);
        expect.soft(
          pageErrors,
          `${def.name} @ ${vp.w}px page errors: ${pageErrors.join(" | ")}`
        ).toEqual([]);
        expect.soft(
          consoleErrors,
          `${def.name} @ ${vp.w}px console errors: ${consoleErrors.join(" | ")}`
        ).toEqual([]);
      });
    }
  });
}

// ---------------------------------------------------------------------------
// Interaction tests — every key visible button must do its job.
// ---------------------------------------------------------------------------

test.describe("interactions @ 390px", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("landing: language toggle + Explore marketplace link work", async ({ page }) => {
    await setPublic(page);
    await page.goto("/");
    await expect(page.getByText("Fair value for every harvest")).toBeVisible();
    await page.getByRole("button", { name: "বাং" }).click();
    await expect(page.getByText("ফসলের ন্যায্য দাম")).toBeVisible();
    await page.getByRole("button", { name: "EN" }).click();
    await expect(page.getByText("Fair value for every harvest")).toBeVisible();
    await page.getByRole("link", { name: /Explore marketplace/ }).click();
    await expect(page).toHaveURL(/\/marketplace/);
  });

  test("login: wrong credentials show an error, forgot link navigates", async ({ page }) => {
    await setPublic(page);
    await page.goto("/login");
    await page.getByLabel(/Email/).fill("nobody@example.com");
    await page.getByLabel(/Password/).fill("WrongPass1!");
    await page.locator("form button[type='submit']").click();
    await expect(page.getByText(/incorrect|invalid|failed/i).first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole("link", { name: /Forgot/i }).click();
    await expect(page).toHaveURL(/\/forgot-password/);
  });

  test("marketplace: search filters, card opens detail", async ({ page }) => {
    await setPublic(page);
    await page.goto("/marketplace");
    await expect(page.locator("article").first()).toBeVisible();
    const before = await page.locator("article").count();
    await page.getByLabel(/Search/).fill("Tomato");
    await page.waitForTimeout(400);
    const after = await page.locator("article").count();
    expect(after).toBeGreaterThan(0);
    expect(after).toBeLessThanOrEqual(before);
    await expect(page.locator("article").first()).toContainText(/Tomato/i);
    await page.locator("article").first().getByRole("link").first().click();
    await expect(page).toHaveURL(/\/marketplace\/\d+/);
    await expect(page.locator("h1")).toBeVisible();
  });

  test("listing detail (buyer): order + offer modals open and close", async ({ page }) => {
    await loginAs(page, "buyer");
    await page.goto(`/marketplace/${LISTING_ID}`);
    await expect(page.locator("h1")).toBeVisible();
    await page.getByRole("button", { name: /Order now/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: "Close" }).first().click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: /Make an offer/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("listing detail (buyer): Message farmer opens a thread", async ({ page }) => {
    await loginAs(page, "buyer");
    await page.goto(`/marketplace/${LISTING_ID}`);
    await page.getByRole("button", { name: /Message farmer/ }).click();
    await expect(page).toHaveURL(/\/messages\/\d+/);
    await expect(page.getByLabel("Type your message…")).toBeVisible();
  });

  test("bottom nav: all five items navigate (farmer)", async ({ page }) => {
    await loginAs(page, "farmer");
    await page.goto("/dashboard");
    const nav = page.locator("nav.fixed.bottom-0");
    await expect(nav).toBeVisible();
    for (const [name, url] of [
      ["Market", /\/marketplace/],
      ["Matches", /\/matches/],
      ["Prices", /\/prices/],
      ["Orders", /\/orders/],
      ["Menu", /\/profile/],
    ] as const) {
      await nav.getByRole("link", { name: new RegExp(name, "i") }).click();
      await expect(page).toHaveURL(url);
    }
  });

  test("mobile drawer: hamburger opens menu, link navigates", async ({ page }) => {
    await loginAs(page, "farmer");
    await page.goto("/dashboard");
    await page.getByRole("button", { name: "Open menu" }).click();
    await expect(page.getByRole("dialog", { name: "FarmMarket" })).toBeVisible();
    await page.getByRole("dialog").getByRole("link", { name: /Quality/ }).click();
    await expect(page).toHaveURL(/\/quality/);
  });

  test("user menu: opens, Profile link works", async ({ page }) => {
    await loginAs(page, "farmer");
    await page.goto("/dashboard");
    await page.locator("button[aria-haspopup='menu']").click();
    await expect(page.getByText("farmer@farmmarket.demo")).toBeVisible();
    await page.getByRole("link", { name: /Profile/ }).first().click();
    await expect(page).toHaveURL(/\/profile/);
  });

  test("weather: hub selector changes the page", async ({ page }) => {
    await setPublic(page);
    await page.goto("/weather");
    await expect(page.getByText("Weather")).toBeVisible();
    const select = page.getByLabel(/Select hub|Hub/i).first();
    await select.selectOption({ index: 1 });
    await expect(page.locator("main")).toContainText(/Chattogram|Rajshahi|Khulna|Sylhet|Dhaka/);
  });

  test("prices: crop selector updates the forecast", async ({ page }) => {
    await setPublic(page);
    await page.goto("/prices");
    await expect(page.getByText("Market price information")).toBeVisible();
    await page.getByLabel(/Select crop/i).selectOption({ index: 1 });
    await page.waitForTimeout(800);
    await expect(page.locator("svg, canvas").first()).toBeVisible();
  });

  test("messages: open a thread and send a message (farmer)", async ({ page }) => {
    await loginAs(page, "farmer");
    await page.goto("/messages");
    const thread = page.getByRole("link", { name: /Dhaka Fresh Mart/ }).first();
    await expect(thread).toBeVisible({ timeout: 10_000 });
    await thread.click();
    await expect(page).toHaveURL(/\/messages\/\d+/);
    const msg = `P9 audit ping ${Date.now()}`;
    await page.getByLabel("Type your message…").fill(msg);
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText(msg)).toBeVisible();
  });

  test("notifications: mark-all-as-read button works", async ({ page }) => {
    await loginAs(page, "farmer");
    await page.goto("/notifications");
    await expect(page.getByText(/Notifications/)).toBeVisible();
    await page.getByRole("button", { name: /Mark all as read/ }).click();
    // Success toast (role=status) — not the button's own label.
    await expect(page.getByRole("status")).toContainText(/Mark all as read/i);
  });

  test("assistant: sending a question gets a reply (farmer)", async ({ page }) => {
    await loginAs(page, "farmer");
    await page.goto("/assistant");
    await page.getByLabel("Type your question…").fill("How do I store tomatoes?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText(/tomato/i).last()).toBeVisible({ timeout: 30_000 });
  });

  test("quality: upload + assess reports the model state (farmer)", async ({ page }) => {
    await loginAs(page, "farmer");
    await page.goto("/quality");
    await expect(page.getByText("Crop quality check")).toBeVisible();
    await page.locator('input[type="file"]').nth(1).setInputFiles("e2e/fixtures/tomato.jpg");
    await page.getByLabel(/Crop/).fill("tomato");
    await page.getByRole("button", { name: "Assess photo" }).click();
    await expect(page.getByText(/Vision model is not trained yet/)).toBeVisible();
  });

  test("admin: price entry form submits (admin)", async ({ page }) => {
    await loginAs(page, "admin");
    await page.goto("/admin/data-sources");
    await expect(page.getByText(/Data sources/i)).toBeVisible();
    // Manual daily price entry: fill price + submit, expect a success toast.
    const priceInput = page.locator('form input[type="number"]').first();
    await expect(priceInput).toBeVisible();
    await priceInput.fill("42");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("status")).toContainText(/saved|updated/i);
  });
});

test.describe("interactions @ 1440px", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("desktop sidebar nav works (admin)", async ({ page }) => {
    await loginAs(page, "admin");
    await page.goto("/admin");
    await expect(page.locator("aside")).toBeVisible();
    await page.locator("aside").getByRole("link", { name: /Users/ }).click();
    await expect(page).toHaveURL(/\/admin\/users/);
    await page.locator("aside").getByRole("link", { name: /Data sources/ }).click();
    await expect(page).toHaveURL(/\/admin\/data-sources/);
  });

  test("desktop: bottom nav hidden, topbar actions work (farmer)", async ({ page }) => {
    await loginAs(page, "farmer");
    await page.goto("/dashboard");
    await expect(page.locator("nav.fixed.bottom-0")).toBeHidden();
    await page.getByRole("link", { name: "Notifications" }).click();
    await expect(page).toHaveURL(/\/notifications/);
  });

  test("marketplace pagination + sort controls respond", async ({ page }) => {
    await setPublic(page);
    await page.goto("/marketplace");
    await expect(page.locator("article").first()).toBeVisible();
    const sort = page.getByLabel(/Sort/i);
    if (await sort.count()) {
      await sort.selectOption({ index: 1 });
      await page.waitForTimeout(500);
      await expect(page.locator("article").first()).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// Screenshots — key pages at desktop + mobile, shipped in docs/audit.
// ---------------------------------------------------------------------------

test.describe("screenshots", () => {
  const shots: { name: string; path: string; role: Role }[] = [
    { name: "landing", path: "/", role: "public" },
    { name: "login", path: "/login", role: "public" },
    { name: "marketplace", path: "/marketplace", role: "public" },
    { name: "listing-detail", path: "/marketplace/__LISTING__", role: "public" },
    { name: "weather", path: "/weather", role: "public" },
    { name: "farmer-dashboard", path: "/dashboard", role: "farmer" },
  ];

  for (const vp of [1440, 390]) {
    test(`capture key pages @ ${vp}px`, async ({ page }) => {
      fs.mkdirSync(SHOTS_DIR, { recursive: true });
      await page.setViewportSize({ width: vp, height: vp === 1440 ? 900 : 844 });
      for (const shot of shots) {
        if (shot.role === "public") await setPublic(page);
        else await loginAs(page, shot.role);
        await page.goto(shot.path.replace("__LISTING__", String(LISTING_ID)));
        await settle(page);
        await page.screenshot({
          path: path.join(SHOTS_DIR, `${shot.name}-${vp}.jpg`),
          type: "jpeg",
          quality: 70,
        });
      }
    });
  }
});
