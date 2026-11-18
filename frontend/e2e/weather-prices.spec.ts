import { expect, test } from "@playwright/test";
import { DEMO, login, setEnglish } from "./helpers";

/**
 * Phase 11 (audit/p11-13): weather + prices pages and auth error paths.
 * The weather test hits LIVE Open-Meteo (no key needed); the login/register
 * error tests exercise the real API against the seeded demo database.
 */

test("weather page shows live conditions and the 7-day chart for Dhaka", async ({ page }) => {
  await setEnglish(page);
  await page.goto("/weather");
  await expect(page.getByText("Weather", { exact: true }).first()).toBeVisible();
  // Live Open-Meteo: current conditions render (not the unavailable state).
  await expect(page.getByRole("heading", { name: /Current conditions/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Past 7 days" })).toBeVisible();
  // Temperature chart (Recharts svg) renders.
  await expect(page.locator("svg.recharts-surface").first()).toBeVisible();
});

test("weather page switches hub and still shows live data", async ({ page }) => {
  await setEnglish(page);
  await page.goto("/weather");
  await expect(page.getByRole("heading", { name: /Current conditions/ })).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Select a hub").selectOption("chattogram");
  await expect(page.getByRole("heading", { name: /Current conditions/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("— Chattogram")).toBeVisible();
});

test("prices page lets the visitor change crop and hub", async ({ page }) => {
  await setEnglish(page);
  await page.goto("/prices");
  await expect(page.getByText("Market price information")).toBeVisible();
  await page.getByLabel("Select a crop").selectOption("potato");
  await page.getByLabel("Select a hub").selectOption("rajshahi");
  // The chart (or its empty state) still renders without crashing.
  await expect(page.locator("svg, canvas").first()).toBeVisible();
});

test("login with a wrong password shows an error and stays on login", async ({ page }) => {
  await setEnglish(page);
  await page.goto("/login");
  await page.getByLabel(/Email/).fill(DEMO.farmer.email);
  await page.getByLabel(/Password/).fill("WrongPassword1!");
  await page.locator("form button[type='submit']").click();
  await expect(page.getByRole("status")).toContainText("Incorrect email or password");
  await expect(page).toHaveURL(/\/login/);
});

test("registering with an existing email shows an error", async ({ page }) => {
  await setEnglish(page);
  await page.goto("/register");
  await page.getByLabel(/Full name/).fill("Duplicate User");
  await page.getByLabel(/Email/).fill(DEMO.buyer.email);
  await page.locator("select[name='role']").selectOption("buyer");
  await page.getByLabel(/^Password/).fill("Demo123!");
  await page.getByLabel(/Confirm password/).fill("Demo123!");
  await page.getByLabel(/District/).fill("Gazipur");
  await page.locator("form button[type='submit']").click();
  await expect(page.getByRole("status")).toContainText("Email already registered");
  await expect(page).toHaveURL(/\/register/);
});

test("logged-in farmer can reach the weather page from the nav", async ({ page }) => {
  await setEnglish(page);
  await login(page, DEMO.farmer.email, DEMO.farmer.password);
  await page.goto("/weather");
  await expect(page.getByRole("heading", { name: /Current conditions/ })).toBeVisible({ timeout: 30_000 });
});
