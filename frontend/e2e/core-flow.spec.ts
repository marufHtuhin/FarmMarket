import { expect, test } from "@playwright/test";
import { DEMO, clearSession, login, register, setEnglish, stamp } from "./helpers";

/**
 * Core marketplace flow, end to end through the real UI and API:
 * farmer registers -> farm -> listing -> buyer searches -> offer -> farmer
 * accepts -> order -> farmer assigns transporter -> transporter delivers ->
 * farmer creates a batch -> buyer verifies it on the public page.
 *
 * External services (Gemini, OpenWeather, OSRM) run in their documented
 * fallback modes here — no API keys are needed for this flow.
 */
test("core flow: register to delivery to batch verification", async ({ page }) => {
  test.setTimeout(180_000); // long multi-role flow
  await setEnglish(page);
  const s = stamp();
  const farmerEmail = `e2e-farmer-${s}@example.com`;
  const buyerEmail = `e2e-buyer-${s}@example.com`;
  const farmName = `E2E Farm ${s}`;

  // 1. Farmer registers and creates a farm.
  await register(page, "farmer", farmerEmail, "E2E Farmer");
  // P6 step: the new profile page shows the registered identity.
  await page.goto("/profile");
  await expect(page.getByText("E2E Farmer")).toBeVisible();
  await expect(page.getByText(farmerEmail)).toBeVisible();
  await page.goto("/farms");
  // The farms page has two "Add farm" buttons once the (empty) list loads:
  // the header action and the empty-state CTA, both opening the same form.
  // .first() pins the header button so the click is not a race against the
  // farms query resolving.
  await page.getByRole("button", { name: "Add farm" }).first().click();
  await page.getByLabel(/Farm name/).fill(farmName);
  await page.getByLabel(/District/).fill("Gazipur");
  await page.locator("form button[type='submit']").click();
  await expect(page.getByText(farmName)).toBeVisible();

  // 2. Farmer publishes a listing; capture the product id from the API response.
  // The crop select is a controlled (unregistered) select — find it by label.
  await page.goto("/listings/new");
  const cropSelect = page.getByLabel(/Select a crop/);
  const cropValue = await cropSelect.evaluate((sel: HTMLSelectElement) => {
    const opt = Array.from(sel.options).find((o) => o.value && o.value !== "__other");
    return opt?.value || "";
  });
  expect(cropValue).toBeTruthy();
  await cropSelect.selectOption(cropValue);
  await page.locator("input[name='quantity']").fill("250");
  await page.locator("input[name='price_per_unit']").fill("42.5");
  await page.locator("input[name='district']").fill("Gazipur");
  const [createResp] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/v1/products") && r.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Publish product" }).click(),
  ]);
  expect(createResp.status()).toBe(200);
  const productId = (await createResp.json()).id as number;
  await expect(page).toHaveURL(/\/listings\/mine/);
  await expect(page.locator(`a[href="/marketplace/${productId}"]`)).toBeVisible();

  // 3. Buyer registers, searches, and makes an offer.
  await clearSession(page);
  await register(page, "buyer", buyerEmail, "E2E Buyer");
  await page.goto("/marketplace");
  await page.getByLabel("Search by product name...").fill(cropValue);
  const card = page.locator(`a[href="/marketplace/${productId}"]`).first();
  await expect(card).toBeVisible();
  await card.click();
  await expect(page).toHaveURL(`/marketplace/${productId}`);
  // The detail page renders "Make an offer" twice (main action + sticky bar),
  // so disambiguate like the other action buttons in this spec.
  await page.getByRole("button", { name: "Make an offer" }).first().click();
  await page.getByLabel(/Order quantity/).fill("100");
  await page.getByLabel(/Your offered price/).fill("40");
  const [offerResp] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/v1/offers") && r.request().method() === "POST",
    ),
    page.locator("form button[type='submit']").click(),
  ]);
  expect(offerResp.status()).toBe(200);

  // 4. Farmer accepts the offer; an order is created.
  await clearSession(page);
  await login(page, farmerEmail, "Demo123!");
  await page.goto("/offers");
  await expect(page.getByRole("button", { name: "Accept" }).first()).toBeVisible();
  const [acceptResp] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/v1/offers/") && r.request().method() === "PATCH",
    ),
    page.getByRole("button", { name: "Accept" }).first().click(),
  ]);
  expect(acceptResp.status()).toBe(200);
  const accepted = await acceptResp.json();
  const orderId = accepted.order_id as number | undefined;

  // 5. Farmer opens the order and assigns the demo transporter.
  await page.goto("/orders");
  const orderLink = orderId
    ? page.locator(`a[href="/orders/${orderId}"]`).first()
    : page.locator('a[href^="/orders/"]').first();
  await expect(orderLink).toBeVisible();
  await orderLink.click();
  // Regression (audit): the detail page used to read flat buyer_name /
  // farmer_name fields the API never returns, so these tiles never
  // rendered. The API returns nested buyer/farmer objects.
  await expect(page.locator("dl dd", { hasText: "E2E Buyer" })).toBeVisible();
  await expect(page.locator("dl dd", { hasText: "E2E Farmer" })).toBeVisible();
  const assignSelect = page.getByLabel("Select a transporter");
  await expect(assignSelect).toBeVisible();
  const transporterValue = await assignSelect.evaluate((sel: HTMLSelectElement) => {
    const opt = Array.from(sel.options).find((o) => o.value);
    return opt?.value || "";
  });
  expect(transporterValue).toBeTruthy();
  await assignSelect.selectOption(transporterValue);
  // Same duplication guard as "Make an offer" above.
  await page.getByRole("button", { name: "Assign transporter" }).first().click();
  await expect(page.getByText("Transporter assigned")).toBeVisible();
  // The assigned transporter now renders as a tile (nested object, same fix).
  await expect(page.locator("dl dd", { hasText: "Transporter" })).toBeVisible();

  // 6. Transporter picks up, moves, and delivers.
  await clearSession(page);
  await login(page, DEMO.transporter.email, DEMO.transporter.password);
  await page.goto("/deliveries");
  await page.getByRole("button", { name: "Mark picked up" }).first().click();
  await expect(page.getByRole("button", { name: "Mark in transit" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Mark in transit" }).first().click();
  await expect(page.getByRole("button", { name: "Mark delivered" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Mark delivered" }).first().click();
  await page.getByLabel(/Proof note/).fill("Delivered to buyer, signed receipt.");
  await page.getByRole("button", { name: "Mark delivered" }).last().click();
  await expect(page.getByText(/delivered/i).first()).toBeVisible();

  // 6b. P6 final-state verification: via the API as the buyer, the order
  // must be completed, the delivery delivered with the proof note, and the
  // listing stock must be 250 - 100 = 150 (offer quantity reserved once).
  const loginResp = await page.request.post("/api/v1/auth/login", {
    data: { email: buyerEmail, password: "Demo123!" },
  });
  expect(loginResp.ok()).toBeTruthy();
  const buyerToken = (await loginResp.json()).access_token as string;
  const orderResp = await page.request.get(`/api/v1/orders/${orderId}`, {
    headers: { Authorization: `Bearer ${buyerToken}` },
  });
  expect(orderResp.ok()).toBeTruthy();
  const finalOrder = await orderResp.json();
  expect(finalOrder.status).toBe("completed");
  expect(finalOrder.delivery_status).toBe("delivered");
  expect(finalOrder.proof_note).toContain("Delivered to buyer");
  const productResp = await page.request.get(`/api/v1/products/${productId}`);
  expect((await productResp.json()).quantity).toBe(150);
  // The buyer sees the completed order in their own history.
  await clearSession(page);
  await login(page, buyerEmail, "Demo123!");
  await page.goto("/orders");
  // The orders page links each order twice (title link + "Order details →"),
  // so the href locator matches two elements — assert on the first.
  await expect(page.locator(`a[href="/orders/${orderId}"]`).first()).toBeVisible();
  await page.goto(`/orders/${orderId}`);
  await expect(page.getByText("completed", { exact: false }).first()).toBeVisible();

  // 7. Farmer creates a Digital Twin batch for the crop.
  await clearSession(page);
  await login(page, farmerEmail, "Demo123!");
  await page.goto("/batches");
  await page.getByRole("button", { name: "Create batch" }).first().click();
  await page.getByLabel(/Crop/).selectOption({ index: 1 });
  await page.getByLabel(/Origin district/).fill("Gazipur");
  await page.getByLabel(/Quantity \(kg\)/).fill("500");
  const [batchResp] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/v1/twin/batches") && r.request().method() === "POST",
    ),
    page.locator("form button[type='submit']").click(),
  ]);
  expect(batchResp.status()).toBe(200);
  const batchCode = (await batchResp.json()).batch_code as string;
  await expect(page).toHaveURL(`/batches/${batchCode}`);

  // 8. Anyone (no login) can verify the batch on the public page.
  await clearSession(page);
  await page.goto(`/verify/${batchCode}`);
  await expect(page.getByText("Chain intact")).toBeVisible();
  await expect(page.getByText(batchCode)).toBeVisible();
});
