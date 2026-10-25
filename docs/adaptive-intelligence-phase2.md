# Phase 2 — Adaptive Investigation Intelligence

**Review branch:** `agent/intelligence-phase2` (includes Phase 1 `agent/intelligence`).
**Status:** opt-in internal policy and HTTP vertical slice; do not merge until Backend and coordinator sign off.

## Run it

From repository root, with dependencies installed:

```bash
NBE_POLICY_TYPE=discriminative pytest -v
python benchmarks/evaluate_adaptive_nbe.py
python benchmarks/demo_intelligence.py
```

To exercise real FastAPI endpoints, start the usual API service with `NBE_POLICY_TYPE=discriminative` in its environment (the flag must be set **before** the process starts). The existing `GET /api/v1/disputes/{id}`, `POST /evidence`, and `POST /verify-carrier` work unchanged. `NBE_POLICY_TYPE=heuristic` remains the default. The policy is enabled only for INR; other categories delegate to the original heuristic.

### Executable graph example: full evidence-update loop

`python benchmarks/demo_intelligence.py` executes these **synthetic** graph updates, printing the decision and its rationale at every step:

| Step | Graph evidence state | Engine's next action | Why |
| --- | --- | --- | --- |
| 1 | Synthetic order and buyer nonreceipt claim; no tracking | `act_merchant_tracking` | Carrier/shipment identity missing |
| 2 | Merchant submits tracking identifier without independent verification | `act_carrier_lookup` | Missing eligible carrier observation |
| 3 | **Simulated** carrier observation reports delivery to ordered ZIP, without signature | `act_request_signature_or_proof` | Matching ZIP does not establish physical buyer receipt |
| 4 | Synthetic signed handoff artifact linked to shipment is added and explicitly tagged synthetic | no new action; existing readiness evaluator allows human handoff | Synthetic evidence provides *fixture-level* exercise of package completeness, not independent verification or adjudication |

All scenario observations and the simulated signature in this demo have `origin=SYNTHETIC_FIXTURE`. The `VERIFIED` status in a simulated fixture **must not be described as independent carrier verification**. The production readiness evaluator may still refer to such records as verified; that semantics issue is owned by Backend and must be reconciled before any live adjudication use.

### Real API example: tracking → carrier response → proof request

The new `apps/api/tests/test_adaptive_integration.py` uses FastAPI's real request handlers, DB, and the synthetic carrier adapter. It asserts:

1. `GET /api/v1/disputes/PP-D-INR-8841` returns `act_merchant_tracking`.
2. `POST /api/v1/disputes/PP-D-INR-8841/evidence` with `{"action_id":"act_merchant_tracking","submitter_role":"MERCHANT","carrier_name":"USPS","tracking_number":"940010009999","verify_carrier_now":false}` leaves the shipment `UNVERIFIED`, then recommends `act_carrier_lookup`.
3. `POST /api/v1/disputes/PP-D-INR-8841/verify-carrier` writes a **simulated** carrier observation and now recommends `act_request_signature_or_proof`, explicitly citing linked observation and buyer-claim IDs. Decision readiness remains false, with receipt unresolved.
4. A separate seeded wrong-address case `PP-D-INR-9923` correctly recommends `act_resolve_contradiction` and cites the conflicting synthetic scan ID.

No LLM is invoked. No refund, payment movement, or dispute winner is selected.

## Decision contract and scoring

`HypothesisDiscriminationPolicy.evaluate_candidates(category, graph, readiness)` returns the existing `PolicyDecision` / `CandidateAction` shapes. Internally:

1. `assess_inr_hypotheses(graph)` evaluates three **carrier-report** hypotheses, not who possessed or received the parcel. Only linked observations marked VERIFIED with either VERIFIED_EXTERNAL or SYNTHETIC_FIXTURE origin contribute, never submitted/unverified/model-only observations. Fixture observations are not blended with external reports.
2. `_derive_needs` constructs inspectable `InvestigationNeed` objects (question, hypothesis IDs, supporting evidence IDs, ordinal importance): tracking identity, carrier report, destination, competing reports, delivery discrepancy, updated transit, or physical handoff. **Physical receipt versus loss/theft/misdelivery remains open even with a matching postal-code scan**.
3. Only allowed, currently supported action IDs are considered: merchant tracking, carrier lookup, address clarification, merchant carrier records, and signature/photo request. The escalation action is returned when no useful acquisition remains. Carrier lookup uses the existing /verify-carrier endpoint; merchant/buyer submissions use /evidence. **Those routes can ingest replies but cannot by themselves verify their truth.** Carrier monitoring is not falsely advertised as an automatic background service.
4. Candidate ranking uses **ordinal ambiguity coverage / (1 + assigned friction)**, for example a priority-3 need addressed with friction 0.6 gives 1.875. Values are comparative rule scores only; not calibrated probabilities, entropy, or predicted reduction in uncertainty. The shared `expected_information_gain` field is set to **0.0 as unavailable**, not an assertion of zero potential information.
5. A QUESTION graph node with a matching action ID is considered an attempted/issued action. Generated proposals are persisted as QUESTION nodes in opt-in mode. A response updates the graph, readiness is recomputed by the old evaluator, then policy reevaluates and records the next recommendation. This *does not mean* the action successfully executed or that an answer was relevant.

Availability is injectable per action. In the existing DisputeService opt-in wiring, real PayPal cases have carrier lookup **disabled** because Backend has no working external carrier provider. Synthetic test cases have the simulated lookup available. A real availability contract for retries/timeouts is a Backend dependency, not an implied existing feature.

## Comparative evaluation

`benchmarks/evaluate_adaptive_nbe.py` defines a separate table of **16 synthetic challenge families**, each with four deterministically seeded postal-code/identifier perturbations (`seed=7331`). These are not the five legacy benchmark cases. Both policies receive identical graphs, buyer claims, report ordering, and action history; only the new policy can consume the injected explicit availability map, as the baseline has no such API.

Metrics collected:

- First useful action according to separately declared action acceptance sets.
- Unsupported verification assertions (a narrow textual proxy, **not** a comprehensive factual entailment check).
- Repeat of a previous action and recommendation of an explicitly unavailable action.
- Appropriate abstention/escalation based on declared missingness/exhaustion.
- Simulated steps until first **relevant UNVERIFIED artifact** is received, with failed/irrelevant actions returning none, capped at five. Cases correctly requiring escalation are excluded from the acquisition-step mean.

The synthetic oracle never fabricates externally verified observations. It can produce unverified artifacts for useful actions, but it does **not** simulate actual carrier truth, response rates, cost distributions, or case adjudication. Results are challenge-suite/fixture evidence, **not held-out generalization**. The benchmark includes a deliberate negative case in which a newer delivery scan is appended before an older transit scan: the new assessor fails to account for report chronology and treats an ordinary update as a conflict. The legacy heuristic can choose the better next action there. Preserve and report this negative result rather than special-case it without a principled temporal model.

## Current limitations and coordination requests

**Backend:**
- A normalized immutable observation envelope with authoritative source ID, `observed_at` and `received_at`, correction/supersession flags, shipment/recipient link, independent vs synthetic verification state and audit trail. Our assessor currently lacks timestamp/supersession logic and trusts upstream origin tags.
- Real action lifecycle: `RECOMMENDED`, `EXECUTED`, `RESPONDED`, `FAILED`, `EXHAUSTED`, plus provider availability and failure reason. The current QUESTION history over-approximates attempts.
- Targeted clarification and carrier-document intake need typed resolution/corroboration; current generic file acceptance cannot establish authentic delivery. Current `get_open_questions()` can mark a question answered by unrelated uploaded evidence; our status/relevance analysis does not trust that edge as proof.
- Current readiness evaluator and report generator may present synthetic VERIFIED reports as independently verified, and readiness may ignore inferred conflicting scans without an explicit CONTRADICTS edge. This change **does not** alter their rules because Backend and coordinator approval is required. A good recommended action does not override an unsafe terminal state.

**Coordinator/frontend:**
- Confirm the final semantics for `expected_information_gain=0.0` (unestimated, not zero) or approve a versioned optional `decision_score_kind` field.
- Decide whether to enable this policy by default after backend provenance and state gates have been reconciled.
- Optionally display unresolved hypothesis IDs and their evidence references by parsing existing policy rationales now; recommend a versioned typed response later. No frontend code was modified here.

**Research:**
- Add correct temporal/supersession reasoning, multiple-shipment order association, full address reconciliation, independent evidence authenticity and explicit actual receipt alternatives.
- Validate on independent held-out scenario families, blinded reviewer-defined useful actions, measured real acquisition outcomes, cost/latency and appropriate abstention. Keep fixed heuristic, null availability baseline, and strong rule baseline. Do not overclaim from synthetic acceptance labels.

## Definition of done for this PR

Executable graph/HTTP paths change recommendations after evidence submission; reasoning traces to evidence IDs and unresolved distinctions; unsupported/repeated actions are blocked where recognized; CI checks legacy tests, independent challenge, and full synthetic handoff demo. All outcomes remain subject to human adjudication.
