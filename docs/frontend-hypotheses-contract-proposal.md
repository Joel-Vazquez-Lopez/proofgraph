# Minimal investigation-explanations API contract proposal

**Status: Proposed only — not supported or rendered by the current frontend.**
Frontend implementation is blocked on Agent 1 agreeing and implementing the contract. This note does not assert existing fields or model capabilities.

## Why

The merchant needs an intelligible answer to *what explanations are still plausible?* and *what evidence would distinguish them?* The interface must not fabricate hypothesis scores, evidence, or recommendations. Current API returns `readiness`, `current_policy_decision`, `evidence_graph`, and `timeline`. It has no typed, evidence-linked collection of competing explanations.

## Suggested additive contract

Prefer a **versioned optional payload**, ideally included in `GET /api/v1/disputes/{id}` once ready, or exposed at a separate `GET /api/v1/disputes/{id}/explanations` endpoint. Agent 1 owns the decision; the frontend does not assume the endpoint exists.

```ts
// PROPOSAL, NOT AN IMPLEMENTED BACKEND API
interface InvestigationExplanationsV1 {
  version: 1;
  hypotheses: Array<{
    hypothesis_id: string;
    title: string;                     // Plain English; no inferred facts
    explanation: string;               // Concise rationale
    assessment: "SUPPORTED" | "CONTRADICTED" | "UNRESOLVED";
    supporting_node_ids: string[];     // Must exist in evidence_graph.nodes
    contradicting_node_ids: string[];  // Must exist in evidence_graph.nodes
    unresolved_questions: string[];    // Observable gaps, not invented facts
  }>;
  next_step?: {
    action_id: string;                 // Align with current_policy_decision, if available
    title: string;
    rationale: string;
    execution_mode: "IN_APP" | "MANUAL";
    required_inputs: string[];
  };
}
```

No numeric confidence or probabilities unless Agent 1 documents calibration, semantics and tests. Hypothesis *assessment* is qualitative and should not imply certainty. A hypothesis can be unsupported, contradictory, or unknown; those are not interchangeable.

## Required invariants

1. Evidence links reference real node IDs from the same case; no fabricated citations.
2. Provenance is read from each referenced node's `origin` **and** `verification_status` field. `SYNTHETIC_FIXTURE` remains simulated even when status is `VERIFIED`.
3. `hypotheses: []` means **no hypotheses supplied**, not “the engine ruled out all alternatives.” Missing payload means capability unavailable.
4. Recommendations match real actions. `IN_APP` must identify an implemented frontend/API flow; otherwise use `MANUAL`.
5. Hypotheses do not assign blame, decide outcomes, or move funds.
6. Existing clients should continue working if this optional payload is absent.

## Proposed frontend UX once accepted

Render a collapsed **“Possible explanations”** panel below the merchant's concise evidence summary. Each explanation has plain-English status, supporting and conflicting evidence record references, unresolved questions, and no made-up confidence bars. The current recommended step remains prominent, with the execution mode shown. The graph, raw sources, policy scores and audit trail remain in Advanced.

## Coordination request for Agent 1

Please reply with: (a) chosen endpoint/payload, (b) guarantee that node refs resolve, (c) allowed assessment values, (d) when a recommendation is executable versus manual, and (e) fixture cases/test coverage. Agent 3 will add the UI and tests only after the contract exists.
