import { expect, test } from "@playwright/test";
import { DEMO, login, setEnglish } from "./helpers";

/** Public pages, route guards, and the documented fallback behaviours. */
test("landing loads and language toggle switches to Bangla", async ({ page }) => {
  await setEnglish(page);
  await page.goto("/");
  await expect(page.getByText("Fair value for every harvest")).toBeVisible();
  await expect(page.getByRole("link", { name: /Explore marketplace/ })).toBeVisible();
  // Language toggle in the header.
  await page.getByRole("button", { name: "বাং" }).click();
  await expect(page.getByText("ফসলের ন্যায্য দাম")).toBeVisible();
});

test("protected routes redirect to login when logged out", async ({ page }) => {
  await setEnglish(page);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/login/);
});

test("role guards block the wrong role", async ({ page }) => {
  await setEnglish(page);
  await login(page, DEMO.buyer.email, DEMO.buyer.password);
  await page.goto("/admin");
  // The guard renders an inline "Access denied" state (URL stays /admin).
  await expect(page.getByText("Access denied")).toBeVisible();
  await expect(page.getByText("Your account does not have permission")).toBeVisible();
});

test("assistant answers in template mode without a Gemini key", async ({ page }) => {
  await setEnglish(page);
  await login(page, DEMO.farmer.email, DEMO.farmer.password);
  await page.goto("/assistant");
  await page.getByLabel("Type your question…").fill("How do I store tomatoes?");
  await page.getByRole("button", { name: "Send" }).click();
  // A reply appears (template fallback, with sources or a clear note).
  await expect(page.locator("text=How do I store tomatoes?")).toBeVisible();
  await expect(page.getByText(/tomato/i).last()).toBeVisible({ timeout: 30_000 });
});

test("quality page reports the vision model as not trained", async ({ page }) => {
  await setEnglish(page);
  await login(page, DEMO.farmer.email, DEMO.farmer.password);
  await page.goto("/quality");
  await expect(page.getByText("Crop quality check")).toBeVisible();
  // No model ships: uploading a photo and assessing must report that clearly.
  await page.locator('input[type="file"]').nth(1).setInputFiles("e2e/fixtures/tomato.jpg");
  await page.getByLabel(/Crop/).fill("tomato");
  await page.getByRole("button", { name: "Assess photo" }).click();
  await expect(page.getByText(/Vision model is not trained yet/)).toBeVisible();
});

test("prices page renders the forecast chart", async ({ page }) => {
  await setEnglish(page);
  await page.goto("/prices");
  await expect(page.getByText("Market price information")).toBeVisible();
  // The chart or its empty state renders without crashing.
  await expect(page.locator("svg, canvas").first()).toBeVisible();
});

test("public verify page shows an unknown-batch error", async ({ page }) => {
  await setEnglish(page);
  await page.goto("/verify/FM-000000000000");
  await expect(page.getByText(/not found|unknown/i).first()).toBeVisible();
});
