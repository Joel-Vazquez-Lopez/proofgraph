const { test, expect } = require("@playwright/test");

const cases = [
  { dispute_id: "DEMO-INR", category: "ITEM_NOT_RECEIVED", state: "AWAITING_EVIDENCE", data_source: "SYNTHETIC_FIXTURE", item_name: "Mechanical keyboard", buyer_name: "Alex", amount: 189.99, currency: "USD" },
  { dispute_id: "DEMO-MISMATCH", category: "ITEM_NOT_RECEIVED", state: "REVIEW_REQUIRED", data_source: "SYNTHETIC_FIXTURE", item_name: "Headphones", buyer_name: "Sam", amount: 349, currency: "USD" },
  { dispute_id: "DEMO-SNAD", category: "SIGNIFICANTLY_NOT_AS_DESCRIBED", state: "AWAITING_EVIDENCE", data_source: "SYNTHETIC_FIXTURE", item_name: "Camera lens", buyer_name: "Dana", amount: 420, currency: "USD" },
  { dispute_id: "DEMO-DUP", category: "DUPLICATE_TRANSACTION", state: "INVESTIGATING", data_source: "SYNTHETIC_FIXTURE", item_name: "Coffee beans", buyer_name: "Robin", amount: 49, currency: "USD" },
].map((d) => ({ ...d, buyer_id: "buyer_1", seller_id: "seller_1", created_at: "2026-10-24T10:00:00Z", updated_at: "2026-10-24T10:00:00Z", open_questions_count: 1, is_decision_ready: false }));

const node = (id, type, content, origin = "SYNTHETIC_FIXTURE", status = "VERIFIED") => ({
  id, type, content, label: id, source: origin, origin, verification_status: status, created_at: "2026-10-24T10:00:00Z",
});

function detail(summary, hasTracking) {
  const mismatch = summary.dispute_id === "DEMO-MISMATCH";
  const inad = summary.category === "ITEM_NOT_RECEIVED";
  const snd = summary.category === "SIGNIFICANTLY_NOT_AS_DESCRIBED";
  const nodes = [
    node("payment record", "TRANSACTION", { amount: summary.amount }),
    node("order record", "ORDER", { item_name: summary.item_name, destination_address: { city: "Portland", state: "OR", postal_code: "97201" } }),
  ];
  if (mismatch || hasTracking && summary.dispute_id === "DEMO-INR") {
    nodes.push(node("tracking record", "SHIPMENT", { carrier_name: "USPS", tracking_number: "TRACK-42" }, "USER_SUBMITTED", "UNVERIFIED"));
  }
  if (mismatch) {
    nodes.push(node("delivery observation", "OBSERVATION", { tracking_number: "TRACK-42", status: "DELIVERED", delivered_to_address: { city: "Seattle", state: "WA", postal_code: "98101" } }));
  }
  const missing = mismatch ? ["CARRIER_ADDRESS_CONFIRMATION"] : (snd ? ["CONDITION_DOCUMENT"] : inad ? [hasTracking ? "DELIVERY_EVIDENCE" : "TRACKING_NUMBER"] : ["TRANSACTION_LEDGER_CHECK"]);
  return {
    ...summary, transaction_id: "TX-123",
    buyer_claim: snd ? "Condition does not match the listing." : inad ? "I did not receive the item." : "I may have paid twice.",
    seller_response: "We are reviewing the transaction.",
    evidence_graph: { nodes, edges: [] },
    current_policy_decision: { chosen_action: { action_id: "act_merchant_tracking", action_type: "REQUEST_MERCHANT_FULFILLMENT", title: "Request supporting evidence", description: "Ask the merchant to provide the relevant record.", target_party: "MERCHANT", expected_information_gain: 0.5, acquisition_friction: 0.2, utility_score: 0.3, rationale: "Open evidence gap" }, selection_rationale: "Open evidence gap" },
    readiness: { is_decision_ready: false, requires_escalation: mismatch, satisfied_requirements: ["PAYMENT_ON_FILE"], missing_requirements: missing, active_contradictions: mismatch ? ["Delivery postal code does not match the order"] : [], recommended_state: summary.state, rationale: mismatch ? "Destination mismatch" : "More evidence is needed." },
    timeline: [], integrity_findings: [],
  };
}

async function mockApi(page, { failFirstDetail = false, delayFirstDetail = false, failFirstList = false, emptyList = false } = {}) {
  let savedTracking = false;
  let failed = false;
  let failedList = false;
  let delayed = false;
  await page.route("**/api/v1/disputes**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/\/$/, "");
    const segments = path.split("/");
    const id = segments[4];
    if (request.method() === "GET" && path === "/api/v1/disputes") {
      if (failFirstList && !failedList) {
        failedList = true;
        return route.fulfill({ status: 503, json: { detail: "Cases are temporarily unavailable" } });
      }
      return route.fulfill({ json: emptyList ? [] : cases });
    }
    if (request.method() === "POST" && path.endsWith("/ai/extract")) {
      return route.fulfill({ json: {
        status: "FALLBACK_NOT_CONFIGURED", provider: "gemini", model: "gemini-3.5-flash-lite",
        model_called: false, claims: [], rejected_items: 0,
        message: "No real API key configured; no model was called.",
        provenance: "NO_MODEL_OUTPUT — deterministic policy fallback only",
        fallback_action_id: "act_merchant_tracking",
      } });
    }
    if (request.method() === "POST" && path.endsWith("/evidence")) {
      savedTracking = true;
      return route.fulfill({ json: { success: true, new_state: "INVESTIGATING", message: "Recorded" } });
    }
    if (request.method() === "POST") {
      return route.fulfill({ json: { success: true, new_state: "INVESTIGATING" } });
    }
    if (request.method() === "GET" && id) {
      if (failFirstDetail && !failed) {
        failed = true;
        return route.fulfill({ status: 503, json: { detail: "Temporary case service outage" } });
      }
      if (delayFirstDetail && id === "DEMO-INR" && !delayed) {
        delayed = true;
        await new Promise((resolve) => setTimeout(resolve, 900));
      }
      const found = cases.find((item) => item.dispute_id === id);
      return found ? route.fulfill({ json: detail(found, savedTracking) }) : route.fulfill({ status: 404, json: { detail: "No case" } });
    }
    return route.continue();
  });
}

test("merchant submits tracking and sees the changed investigation and persistent feedback", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByText("Add tracking information")).toBeVisible();
  await page.getByPlaceholder("e.g. 940010009999").fill("TRACK-42");
  await page.getByRole("button", { name: "Save tracking information" }).click();
  await expect(page.getByText(/Tracking details submitted/)).toBeVisible();
  await expect(page.getByText("Check delivery with the carrier")).toBeVisible();
  await expect(page.getByText(/Delivery is not confirmed/).first()).toBeVisible();
  await page.getByRole("button", { name: /Headphones/ }).click();
  await expect(page.getByText("Conflicting evidence — human review needed.")).toBeVisible();
  await expect(page.getByText("Also still needed")).toBeVisible();
  await expect(page.getByText("CARRIER ADDRESS CONFIRMATION")).toBeVisible();
  await expect(page.getByText("Portland, OR, 97201").first()).toBeVisible();
  await expect(page.getByText("Seattle, WA, 98101").first()).toBeVisible();
  await page.getByRole("button", { name: "Review this issue" }).click();
  await expect(page.getByRole("dialog", { name: "Case review package" })).toBeVisible();
  await expect(page.getByText("Simulated record").first()).toBeVisible();
  await expect(page.getByText("These are readiness checks, not independently verified facts.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Review this issue" })).toBeFocused();
});

test("non-shipping disputes show an executable upload or clearly manual next step", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: /Camera lens/ }).click();
  await expect(page.getByText("Add a photo or document")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save document" })).toBeDisabled();
  await page.getByRole("button", { name: /Coffee beans/ }).click();
  await expect(page.getByText(/Manual follow-up required/)).toBeVisible();
  await expect(page.getByRole("button", { name: "See case summary" })).toBeVisible();
});

test("API error produces an actionable retry", async ({ page }) => {
  await mockApi(page, { failFirstDetail: true });
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "Temporary case service outage" })).toBeVisible();
  await page.getByRole("button", { name: "Retry case details" }).click();
  await expect(page.getByText("Add tracking information")).toBeVisible();
});

test("switching cases cannot reveal an older delayed detail response", async ({ page }) => {
  await mockApi(page, { delayFirstDetail: true });
  await page.goto("/");
  await page.getByRole("button", { name: /Coffee beans/ }).click();
  await expect(page.getByText(/Manual follow-up required/)).toBeVisible();
  await page.waitForTimeout(1100);
  await expect(page.getByText(/Manual follow-up required/)).toBeVisible();
  await expect(page.getByText("Add tracking information")).toHaveCount(0);
});

test("mobile viewport fits without horizontal overflow and case cards are keyboard-operable", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockApi(page);
  await page.goto("/");
  const caseButton = page.getByRole("button", { name: /Camera lens/ });
  await caseButton.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Add a photo or document")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(2);
});

test("empty account shows a helpful empty state without fabricating cases", async ({ page }) => {
  await mockApi(page, { emptyList: true });
  await page.goto("/");
  await expect(page.getByText("No cases are available for this account.")).toBeVisible();
  await expect(page.getByText("Select a case to begin investigation.")).toBeVisible();
  // Next.js may expose its own inert route-announcer alert; only check app errors.
  await expect(page.getByRole("alert").filter({ hasText: /Could not load cases|Cases are temporarily unavailable/ })).toHaveCount(0);
});

test("failed initial case-list load offers retry instead of incorrectly claiming no cases", async ({ page }) => {
  await mockApi(page, { failFirstList: true });
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "Cases are temporarily unavailable" })).toBeVisible();
  await expect(page.getByText("No cases are available for this account.")).toHaveCount(0);
  await page.getByRole("button", { name: "Retry loading cases" }).click();
  await expect(page.getByRole("button", { name: /Mechanical keyboard/ })).toBeVisible();
});

test("AI assistance shows explicit non-AI fallback instead of pretending a model ran", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Analyze dispute text with AI" })).toBeVisible();
  await page.getByRole("button", { name: "Analyze dispute text with AI" }).click();
  await expect(page.getByText(/No model call.*FALLBACK_NOT_CONFIGURED/)).toBeVisible();
  await expect(page.getByText(/NO_MODEL_OUTPUT/)).toBeVisible();
  await expect(page.getByText(/Separate deterministic investigation action/)).toBeVisible();
});

test("AI assistant UI labels exact source quote, named model and unverified provenance", async ({ page }) => {
  await mockApi(page);
  // Intercept ONLY the presentation test: this is NOT a live model.
  await page.route("**/ai/extract", (route) => route.fulfill({ json: {
    status: "MODEL_SUCCESS", provider: "openai", model: "gpt-4o-mini",
    model_called: true, rejected_items: 0,
    message: "Mocked provider response for UI-only test",
    provenance: "MODEL_INFERENCE / UNVERIFIED — textual analysis, not evidence verification",
    fallback_action_id: "act_merchant_tracking",
    claims: [{
      source_id: "case:buyer_claim", quote: "I did not receive the item.",
      claim_type: "NON_RECEIPT", evidence_need: "HANDOFF_PROOF",
      evidence_question: "Can delivery handoff or recipient acknowledgement be corroborated?",
      inference_node_id: "ai_claim_test_only",
    }],
  }}));
  await page.goto("/");
  await page.getByRole("button", { name: "Analyze dispute text with AI" }).click();
  await expect(page.getByText(/Provider: openai.*gpt-4o-mini.*MODEL_SUCCESS/)).toBeVisible();
  await expect(page.getByRole("region", { name: "AI claim extraction" }).getByText("I did not receive the item.")).toBeVisible();
  await expect(page.getByText(/MODEL_INFERENCE \/ UNVERIFIED/)).toBeVisible();
  await expect(page.getByText(/case:buyer_claim/)).toBeVisible();
});

test("Gemini success explicitly names free-tier model and quote provenance (mocked UI only)", async ({ page }) => {
  await mockApi(page);
  // This is a presentation stub; it is NOT evidence of a real Gemini request.
  await page.route("**/ai/extract", (route) => route.fulfill({ json: {
    status: "MODEL_SUCCESS", provider: "gemini", model: "gemini-3.5-flash-lite",
    model_called: true, rejected_items: 0,
    message: "Mocked Gemini reply for browser assertions only",
    provenance: "MODEL_INFERENCE / UNVERIFIED — textual analysis, not evidence verification",
    fallback_action_id: "act_merchant_tracking",
    claims: [{
      source_id: "case:buyer_claim", quote: "I did not receive the item.",
      claim_type: "NON_RECEIPT", evidence_need: "HANDOFF_PROOF",
      evidence_question: "Can delivery handoff or recipient acknowledgement be corroborated?",
      inference_node_id: "ai_claim_mock_gemini",
    }],
  }}));
  await page.goto("/");
  await page.getByRole("button", { name: "Analyze dispute text with AI" }).click();
  const panel = page.getByRole("region", { name: "AI claim extraction" });
  await expect(panel.getByText(/Provider: gemini.*gemini-3\.5-flash-lite.*MODEL_SUCCESS/)).toBeVisible();
  await expect(panel.getByText("I did not receive the item.")).toBeVisible();
  await expect(panel.getByText(/MODEL_INFERENCE \/ UNVERIFIED/)).toBeVisible();
  await expect(panel.getByText(/case:buyer_claim/)).toBeVisible();
});
