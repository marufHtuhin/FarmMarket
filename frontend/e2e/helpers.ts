import { expect, type Page } from "@playwright/test";

/** Demo accounts seeded by e2e/serve.sh (seed_demo.py). */
export const DEMO = {
  farmer: { email: "farmer@farmmarket.demo", password: "Demo123!" },
  buyer: { email: "buyer@farmmarket.demo", password: "Demo123!" },
  transporter: { email: "transporter@farmmarket.demo", password: "Demo123!" },
  admin: { email: "admin@farmmarket.demo", password: "Demo123!" },
};

/** Force English UI before any page loads (default language is Bangla). */
export async function setEnglish(page: Page) {
  await page.addInitScript(() => localStorage.setItem("fm_lang", "en"));
}

/** Unique suffix so repeated runs never collide on e-mail addresses. */
export const stamp = () => Date.now().toString(36);

export async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel(/Email/).fill(email);
  await page.getByLabel(/Password/).fill(password);
  await page.locator("form button[type='submit']").click();
  await expect(page).not.toHaveURL(/\/login/);
  await page.waitForLoadState("networkidle");
}

export async function register(
  page: Page,
  role: "farmer" | "buyer" | "transporter",
  email: string,
  name: string,
) {
  await page.goto("/register");
  await page.getByLabel(/Full name/).fill(name);
  await page.getByLabel(/Email/).fill(email);
  await page.locator("select[name='role']").selectOption(role);
  await page.getByLabel(/^Password/).fill("Demo123!");
  await page.getByLabel(/Confirm password/).fill("Demo123!");
  await page.getByLabel(/District/).fill("Gazipur");
  await page.locator("form button[type='submit']").click();
  await expect(page).not.toHaveURL(/\/register/);
  await page.waitForLoadState("networkidle");
}

/** Client-side logout (clears stored tokens). The /auth/logout endpoint
 *  itself is covered by the backend pytest suite. */
export async function clearSession(page: Page) {
  await page.evaluate(() => localStorage.clear());
}
