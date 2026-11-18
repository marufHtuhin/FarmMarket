import { expect, test } from "@playwright/test";
import { clearSession, DEMO, login, setEnglish, stamp } from "./helpers";

/** Farmer-buyer messaging: two demo users exchange messages through the UI.
 *  The seeded Tomato listing belongs to the demo farmer (Rahim Uddin), so
 *  the buyer messages him and he replies as the demo farmer account. */
test("buyer and farmer exchange messages about a listing", async ({ page }) => {
  await setEnglish(page);
  const buyerMsg = `Is the tomato still available? [${stamp()}]`;
  const farmerReply = `Yes, still available — fresh harvest. [${stamp()}]`;

  // Buyer opens the Tomato listing and messages its farmer.
  // NOTE: core-flow.spec.ts runs before this file and creates its own
  // Tomato listing for an "E2E Farmer", so scope to the card belonging to
  // the demo farmer (Rahim Uddin) — the first Tomato link is not his when
  // the full suite runs.
  await login(page, DEMO.buyer.email, DEMO.buyer.password);
  await page.goto("/marketplace");
  const card = page
    .locator("article")
    .filter({ hasText: "Rahim Uddin" })
    .filter({ hasText: "Tomato" })
    .first();
  await card.getByRole("link", { name: "Tomato" }).first().click();
  await expect(page.getByRole("button", { name: "Message farmer" })).toBeVisible();
  await page.getByRole("button", { name: "Message farmer" }).click();
  await expect(page).toHaveURL(/\/messages\/\d+/);
  await expect(page.getByText("Rahim Uddin")).toBeVisible();
  // Privacy: the farmer's demo phone number must never appear in the chat.
  await expect(page.locator("body")).not.toContainText("01710000001");

  await page.getByLabel("Type your message…").fill(buyerMsg);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(buyerMsg)).toBeVisible();

  // Farmer sees the conversation with an unread badge, opens it, replies.
  await clearSession(page);
  await login(page, DEMO.farmer.email, DEMO.farmer.password);
  await page.goto("/messages");
  await expect(page.getByRole("link", { name: /Dhaka Fresh Mart/ })).toBeVisible();
  await expect(page.getByText(buyerMsg)).toBeVisible();
  // Unread badge on the sidebar Messages nav entry.
  await expect(page.locator("aside a[href='/messages']")).toContainText("1");
  await page.getByRole("link", { name: /Dhaka Fresh Mart/ }).click();
  await expect(page).toHaveURL(/\/messages\/\d+/);
  await expect(page.getByText(buyerMsg)).toBeVisible();
  await expect(page.locator("body")).not.toContainText("01710000002");
  await page.getByLabel("Type your message…").fill(farmerReply);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(farmerReply)).toBeVisible();

  // Buyer comes back and sees the farmer's reply in the same thread.
  await clearSession(page);
  await login(page, DEMO.buyer.email, DEMO.buyer.password);
  await page.goto("/messages");
  await page.getByRole("link", { name: /Rahim Uddin/ }).click();
  await expect(page.getByText(buyerMsg)).toBeVisible();
  await expect(page.getByText(farmerReply)).toBeVisible();
});

test("messages page requires login and blocks other roles", async ({ page }) => {
  await setEnglish(page);
  await page.goto("/messages");
  await expect(page).toHaveURL(/\/login/);
  // Transporters cannot use farmer-buyer chat.
  await login(page, DEMO.transporter.email, DEMO.transporter.password);
  await page.goto("/messages");
  await expect(page.getByText("Access denied")).toBeVisible();
});
