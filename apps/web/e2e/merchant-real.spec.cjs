const { test, expect } = require("@playwright/test");
const fs = require("node:fs/promises");

// IMPORTANT: no page.route(), route.fulfill(), route.abort(), or mocked dispute API.
// Next.js /api/v1 rewrites point to the actual FastAPI instance started by
// playwright.config.cjs. Each assertion below is grounded in persisted API state.

const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jrKkAAAAASUVORK5CYII=",
  "base64"
);

async function getCase(page, id) {
  const response = await page.request.get(`/api/v1/disputes/${id}`);
  expect(response.ok(), `FastAPI GET dispute ${id}`).toBeTruthy();
  return response.json();
}

async function openCase(page, itemName) {
  await page.getByRole("button", { name: new RegExp(itemName, "i") }).click();
  await expect(page.getByText("Customer says", { exact: true })).toBeVisible();
}

async function openReview(page) {
  const openButton = page.getByRole("button", {
    name: /See case summary|Review updated case summary|Review this issue/,
  }).first();
  await expect(openButton).toBeVisible();
  await openButton.click();
  const dialog = page.getByRole("dialog", { name: "Case review package" });
  await expect(dialog).toBeVisible();
  return dialog;
}

test("real backend: merchant investigates, saves tracking, checks carrier, reviews contradiction, and uploads condition evidence", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "My Cases" })).toBeVisible();

  // 1. Select a real seeded item-not-received dispute and understand the claim.
  await openCase(page, "Keychron Q1 Pro");
  await expect(page.getByText(/I ordered a mechanical keychron keyboard/)).toBeVisible();
  await expect(page.getByText("No tracking information yet")).toBeVisible();
  await expect(page.getByText("Add tracking information")).toBeVisible();
  const before = await getCase(page, "PP-D-INR-8841");
  expect(before.evidence_graph.nodes.some((n) => n.type === "SHIPMENT")).toBe(false);

  // 2. POST tracking to FastAPI without implicitly running a carrier lookup.
  await page.getByRole("textbox", { name: "Tracking number" }).fill("940010009999");
  const trackingResponse = page.waitForResponse((r) =>
    r.request().method() === "POST" && r.url().endsWith("/PP-D-INR-8841/evidence")
  );
  await page.getByRole("button", { name: "Save tracking information" }).click();
  expect((await trackingResponse).ok()).toBeTruthy();
  await expect(page.getByRole("status")).toContainText("Tracking details submitted");
  const afterTracking = await getCase(page, "PP-D-INR-8841");
  const shipment = afterTracking.evidence_graph.nodes.find((n) => n.type === "SHIPMENT");
  expect(shipment?.content.tracking_number).toBe("940010009999");
  expect(shipment?.origin).toBe("USER_SUBMITTED");
  expect(shipment?.verification_status).toBe("UNVERIFIED");
  expect(afterTracking.evidence_graph.nodes.filter((n) => n.type === "OBSERVATION")).toHaveLength(0);

  // The recommended next step actually changes, while success feedback persists.
  await expect(page.getByText("Check delivery with the carrier")).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Tracking details submitted");
  await expect(page.getByText(/This is a simulation using fixture data/)).toBeVisible();

  // 3. The merchant explicitly consents to a SIMULATED carrier check.
  await page.getByRole("checkbox", { name: /lookup may use demonstration data/ }).check();
  const carrierResponse = page.waitForResponse((r) =>
    r.request().method() === "POST" && r.url().endsWith("/PP-D-INR-8841/verify-carrier")
  );
  await page.getByRole("button", { name: "Look up delivery record" }).click();
  expect((await carrierResponse).ok()).toBeTruthy();
  await expect(page.getByRole("status")).toContainText(/simulated demonstration data/);
  const afterLookup = await getCase(page, "PP-D-INR-8841");
  const lookup = afterLookup.evidence_graph.nodes.filter((n) => n.type === "OBSERVATION").at(-1);
  expect(lookup?.origin).toBe("SYNTHETIC_FIXTURE");
  expect(lookup?.content.verification_outcome).toBe("SIMULATED");
  expect(lookup?.metadata?.independently_verified).toBe(false);
  expect(lookup?.content.status).toBe("DELIVERED");
  await expect(page.getByText("Delivery record on file")).toBeVisible();
  await expect(page.getByText(/This is synthetic demonstration data, not a live carrier check/)).toBeVisible();

  // 4. Review the REAL record and its honest provenance; download the summary.
  const report = await openReview(page);
  await expect(report.getByText("Simulated record").first()).toBeVisible();
  await expect(report.getByText("User submitted").first()).toBeVisible();
  await expect(report.getByText(/not independently verified/).first()).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    report.getByRole("button", { name: "Download case summary" }).click(),
  ]);
  const markdown = await fs.readFile(await download.path(), "utf8");
  expect(markdown).toContain("Simulated record");
  expect(markdown).toContain("User submitted");
  expect(markdown).toContain("Requirements met (evaluator assessment, not proof of independent verification)");
  expect(markdown).not.toContain("Established & Verified Facts");
  expect(markdown).not.toMatch(/submitted (?:to|through) PayPal/i);
  await page.keyboard.press("Escape");
  await expect(report).toHaveCount(0);

  // 5. A separate real dispute contradicts the merchant's delivery address.
  await openCase(page, "Sony WH-1000XM5");
  const mismatched = await getCase(page, "PP-D-INR-9923");
  expect(mismatched.readiness.active_contradictions.length).toBeGreaterThan(0);
  await expect(page.getByText("Conflicting evidence").first()).toBeVisible();
  await expect(page.getByText(/Portland, OR, 97201/).first()).toBeVisible();
  await expect(page.getByText(/Seattle, WA, 98101/).first()).toBeVisible();
  const conflictReport = await openReview(page);
  await expect(conflictReport.getByText("What remains unresolved")).toBeVisible();
  await expect(conflictReport.getByText(/Conflicting evidence:/).first()).toBeVisible();
  await expect(conflictReport.getByText("Simulated record").first()).toBeVisible();
  await page.keyboard.press("Escape");

  // 6. Different dispute category: condition-document submission and evaluation.
  await openCase(page, "Leica Summicron");
  await expect(page.getByText(/deep diagonal scratch across the front element/)).toBeVisible();
  await expect(page.getByText("Add a photo or document")).toBeVisible();
  const file = page.getByRole("button", { name: "Choose supporting condition document" })
    .or(page.getByLabel("Choose supporting condition document"));
  // Malformed image is rejected by the REAL backend signature validator.
  await file.setInputFiles({
    name: "bad-image.png", mimeType: "image/png", buffer: Buffer.from("not-a-png"),
  });
  const rejectedUpload = page.waitForResponse((r) =>
    r.request().method() === "POST" && r.url().endsWith("/PP-D-SNAD-3012/upload-evidence")
  );
  await page.getByRole("button", { name: "Save document" }).click();
  expect((await rejectedUpload).status()).toBe(400);
  await expect(page.getByRole("alert").filter({ hasText: /Invalid file format: content signature/ })).toBeVisible();
  // Correct the selection and retry without refreshing or losing the case.
  await file.setInputFiles({ name: "lens-condition.png", mimeType: "image/png", buffer: png });
  const uploadResponse = page.waitForResponse((r) =>
    r.request().method() === "POST" && r.url().endsWith("/PP-D-SNAD-3012/upload-evidence")
  );
  await page.getByRole("button", { name: "Save document" }).click();
  expect((await uploadResponse).ok()).toBeTruthy();
  await expect(page.getByRole("status")).toContainText(/Document received and added/);
  const afterUpload = await getCase(page, "PP-D-SNAD-3012");
  const uploaded = afterUpload.evidence_graph.nodes.find((n) =>
    n.type === "EVIDENCE_ITEM" && n.content?.file_name?.includes("lens-condition")
  );
  expect(uploaded, "Evidence file persisted in the real FastAPI graph").toBeTruthy();
  expect(uploaded.origin).toBe("USER_SUBMITTED");
  expect(uploaded.verification_status).toBe("UNVERIFIED");
  await expect(page.getByText("Merchant document received")).toBeVisible();
  await expect(page.getByText(/not independently authenticated/)).toBeVisible();
  // The next action is review, not an endless repeat-upload prompt.
  await expect(page.getByRole("button", { name: "Save document" })).toHaveCount(0);
  const conditionReport = await openReview(page);
  await expect(conditionReport.getByText("User submitted").first()).toBeVisible();
  await expect(conditionReport.getByText(/readiness checks, not independently verified facts/)).toBeVisible();
  await page.keyboard.press("Escape");
});

test("real backend: small-screen navigation, focus and keyboard access", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "My Cases" })).toBeVisible();
  const cameraCase = page.getByRole("button", { name: /Leica Summicron/ });
  await cameraCase.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Customer says", { exact: true })).toBeVisible();
  await expect(page.getByText(/deep diagonal scratch/).first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  expect(overflow, "No horizontal page overflow at 375px").toBeLessThanOrEqual(2);
  const trigger = page.getByRole("button", { name: /See case summary|Review updated case summary|Review this issue/ }).first();
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Case review package" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Close review package" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("real backend: visible loading and recoverable network failure without API stubs", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "My Cases" })).toBeVisible();
  await expect(page.getByText("Customer says", { exact: true })).toBeVisible();
  // Browser goes offline: real fetches fail naturally, without request interception.
  await page.context().setOffline(true);
  await page.getByRole("button", { name: "Refresh investigation state" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /Could not load cases/ })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: /Could not load case details/ })).toBeVisible();
  await page.context().setOffline(false);
  await page.getByRole("button", { name: "Retry loading cases" }).click();
  await page.getByRole("button", { name: "Retry case details" }).click();
  await expect(page.getByText("Customer says", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "My Cases" })).toBeVisible();
});
