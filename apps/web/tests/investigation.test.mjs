import test from "node:test";
import assert from "node:assert/strict";
import {
  evidenceProvenance, investigationSummary, generateReviewMarkdown,
} from "../src/lib/investigation-report.mjs";
import {
  friendlyRequestError, getResponseError, isCurrentCase, submissionMessage,
} from "../src/lib/investigation-actions.mjs";
import { merchantNextStep, hasUsableDeliveryObservation, latestCarrierObservation } from "../src/lib/merchant-workflow.mjs";

const observation = (origin, verification_status = "VERIFIED") => ({
  id: `obs-${origin}`, type: "OBSERVATION", label: "Carrier delivery",
  source: origin === "SYNTHETIC_FIXTURE" ? "SyntheticAdapter" : "CarrierAPI",
  origin, verification_status,
  content: { tracking_number: "T123", status: "DELIVERED" },
});

function sampleDispute(nodes = []) {
  return {
    dispute_id: "TEST-INR-1", amount: 125, currency: "USD",
    buyer_claim: "Package not delivered", seller_response: null,
    evidence_graph: { nodes },
    readiness: {
      is_decision_ready: false,
      satisfied_requirements: ["PAYMENT_ON_FILE"],
      missing_requirements: ["PROOF_OF_DELIVERY"],
      active_contradictions: ["Order and delivery postal codes differ"],
      recommended_state: "REVIEW_REQUIRED",
      rationale: "Address mismatch",
    },
  };
}

test("synthetic VERIFIED node is only described as simulation in both views", () => {
  const caseData = sampleDispute([observation("SYNTHETIC_FIXTURE")]);
  const record = investigationSummary(caseData).evidence[0];
  assert.equal(record.label, "Simulated record");
  assert.equal(record.externallyVerified, false);
  const markdown = generateReviewMarkdown(caseData, "Keyboard", "Buyer", "2026-10-25");
  assert.match(markdown, /Simulated record/);
  assert.match(markdown, /Demonstration data; not independently verified/);
  assert.doesNotMatch(markdown, /Established & Verified Facts|PAYMENT_ON_FILE: Verified|Order placement and payment verified on ledger/);
  assert.match(markdown, /Requirements met.*not proof of independent verification/);
  assert.match(markdown, /Unresolved requirements/);
  assert.match(markdown, /Contradictions requiring review/);
});

test("user-submitted and inferred evidence cannot become independently verified", () => {
  assert.equal(evidenceProvenance(observation("USER_SUBMITTED", "VERIFIED")).externallyVerified, false);
  assert.equal(evidenceProvenance(observation("MODEL_INFERENCE", "VERIFIED")).externallyVerified, false);
  assert.equal(evidenceProvenance(observation("UNVERIFIED", "VERIFIED")).externallyVerified, false);
});

test("external origin alone is insufficient without verified status", () => {
  assert.equal(evidenceProvenance(observation("VERIFIED_EXTERNAL", "UNVERIFIED")).externallyVerified, false);
  assert.equal(evidenceProvenance(observation("VERIFIED_EXTERNAL", "VERIFIED")).externallyVerified, true);
});

test("empty and partially missing records do not manufacture facts", () => {
  const md = generateReviewMarkdown({ dispute_id: "EMPTY" }, "", "", "2026-10-25");
  assert.match(md, /No evidence items available/);
  assert.match(md, /No statement on record/);
  assert.match(md, /None listed by the evaluator/);
  assert.doesNotMatch(md, /Order placed and|verified on ledger/);
});

test("contradictions and missing requirements render independently", () => {
  const md = generateReviewMarkdown(sampleDispute(), "Keyboard", "Buyer", "2026-10-25");
  assert.match(md, /proof of delivery/);
  assert.match(md, /Order and delivery postal codes differ/);
});

test("category routing exposes supported actions and a manual fallback", () => {
  const base = { isReady: false, isReview: false, hasTracking: false, hasDeliveryRecord: false };
  assert.equal(merchantNextStep({ ...base, category: "ITEM_NOT_RECEIVED" }), "submit-tracking");
  assert.equal(merchantNextStep({ ...base, category: "ITEM_NOT_RECEIVED", hasTracking: true }), "carrier-lookup");
  assert.equal(merchantNextStep({ ...base, category: "ITEM_NOT_RECEIVED", hasTracking: true, hasDeliveryRecord: true }), "manual-follow-up");
  assert.equal(merchantNextStep({ ...base, category: "SIGNIFICANTLY_NOT_AS_DESCRIBED" }), "upload-condition");
  assert.equal(merchantNextStep({ ...base, category: "DUPLICATE_TRANSACTION" }), "manual-follow-up");
  assert.equal(merchantNextStep({ ...base, category: "UNAUTHORIZED_TRANSACTION" }), "manual-follow-up");
  assert.equal(merchantNextStep({ ...base, category: "ITEM_NOT_RECEIVED", isReview: true }), "human-review");
  assert.equal(merchantNextStep({ ...base, category: "ITEM_NOT_RECEIVED", isReady: true }), "review");
});

test("carrier observations must match tracking and verified delivered status", () => {
  const shipment = { content: { tracking_number: "T123" } };
  assert.equal(hasUsableDeliveryObservation(shipment, [observation("SYNTHETIC_FIXTURE")]), true);
  assert.equal(hasUsableDeliveryObservation(shipment, [{ ...observation("SYNTHETIC_FIXTURE"), content: { tracking_number: "other", status: "DELIVERED" } }]), false);
  assert.equal(hasUsableDeliveryObservation(shipment, [observation("VERIFIED_EXTERNAL", "UNVERIFIED")]), false);
  assert.equal(hasUsableDeliveryObservation(null, []), false);
});

test("old in-flight case responses cannot be committed to a new selection", () => {
  assert.equal(isCurrentCase("A", "B", 10, 10), false);
  assert.equal(isCurrentCase("A", "A", 9, 10), false);
  assert.equal(isCurrentCase("A", "A", 10, 10), true);
});

test("action successes make no unsupported verification claim", () => {
  const upload = submissionMessage("upload", { new_state: "AWAITING_EVIDENCE" });
  const tracking = submissionMessage("tracking", { new_state: "INVESTIGATING" });
  const simulated = submissionMessage("carrier", { new_state: "REVIEW_REQUIRED" }, true);
  assert.match(upload, /do not establish authenticity/);
  assert.match(tracking, /does not verify delivery/);
  assert.match(simulated, /simulated demonstration data/);
  assert.doesNotMatch(simulated, /independently verified delivery/);
});

test("API errors extract both text and validation-list details", async () => {
  assert.equal(await getResponseError({ status: 400, json: async () => ({ detail: "Invalid tracking" }) }, "Failed"), "Invalid tracking");
  assert.equal(await getResponseError({ status: 422, json: async () => ({ detail: [{ msg: "field required" }] }) }, "Failed"), "field required");
  assert.equal(await getResponseError({ status: 503, json: async () => { throw new Error("not JSON"); } }, "Service unavailable"), "Service unavailable (HTTP 503)");
});

test("append-only carrier history uses the latest event, not a historical delivery", () => {
  const shipment = { content: { tracking_number: "T123" } };
  const initial = observation("SYNTHETIC_FIXTURE");
  const corrected = { ...observation("SYNTHETIC_FIXTURE", "UNVERIFIED"), id: "later", content: { tracking_number: "T123", status: "NOT_FOUND" } };
  assert.equal(hasUsableDeliveryObservation(shipment, [initial, corrected]), false);
  assert.equal(latestCarrierObservation(shipment, [initial, corrected])?.id, "later");
  assert.equal(hasUsableDeliveryObservation(shipment, [corrected, initial]), true);
});

test("submitted condition evidence advances the merchant beyond the upload prompt", () => {
  const base = { isReady: false, isReview: false, category: "SIGNIFICANTLY_NOT_AS_DESCRIBED", hasTracking: true, hasDeliveryRecord: false };
  assert.equal(merchantNextStep(base), "upload-condition");
  assert.equal(merchantNextStep({ ...base, hasConditionEvidence: true }), "condition-submitted");
  assert.equal(merchantNextStep({ ...base, isReady: true, hasConditionEvidence: true }), "review");
});

test("offline network failures have a clear retry path while API details remain visible", () => {
  assert.match(friendlyRequestError(new TypeError("Failed to fetch"), "Could not load cases"), /Could not load cases.*Check your connection.*retry/);
  assert.equal(friendlyRequestError(new Error("Temporary service issue"), "Could not load cases"), "Temporary service issue");
});

test("simulated PayPal-looking records never appear as live verified sources in merchant review", () => {
  const syntheticPayment = {
    id: "tx-demo", type: "TRANSACTION", label: "Demo transaction",
    source: "PAYPAL_API", origin: "SYNTHETIC_FIXTURE",
    verification_status: "VERIFIED", content: { amount: 100 },
  };
  const view = investigationSummary(sampleDispute([syntheticPayment]));
  assert.equal(view.evidence[0].externallyVerified, false);
  assert.match(view.evidence[0].source, /Demonstration fixture/);
  assert.equal(view.evidence[0].verification, "Not independently verified");
  const markdown = generateReviewMarkdown(sampleDispute([syntheticPayment]), "Item", "Buyer", "2026-10-25");
  assert.match(markdown, /Demonstration fixture \(no live PayPal or carrier check\)/);
  assert.match(markdown, /verification: Not independently verified/);
  assert.doesNotMatch(markdown, /PAYPAL_API|API status: VERIFIED|independently verified per API provenance/i);
});
