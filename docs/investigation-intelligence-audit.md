# Investigation Intelligence — focused audit and staged research design

**Scope:** Investigation algorithms, hypothesis representations, and empirical evaluation.
**Base:** main, 2026-10-25. **Branch:** agent/intelligence.
**Status:** Initial non-breaking implementation; not a production adjudication system.

## 1. Actual current behavior (code audit)

- `evidence_graph.py` maintains typed graph nodes/edges with sources, provenance, and verification flags; it retrieves explicitly recorded contradictions. It does **not** infer contradictions from arbitrary fields, update beliefs, compare hypotheses, or establish independence of evidence.
- `get_unverified_claims()` treats *any* incoming `SUPPORTS` edge as enough to exclude a claim; it does not enforce provenance or verification status. `get_open_questions()` similarly treats *any* `ANSWERS` edge as closing a question. These are graph-structure queries, not proof standards.
- `nbe_policy.py` conditions decisions on category, presence of SHIPMENT, carrier-observation source/label substrings, `status`, signature flag, contradiction edges, and attempted QUESTION actions. Candidate `expected_information_gain` values (e.g. 0.95 and 0.98), friction, and utility are **manual constants**, not statistical expectations or calibrated probabilities. Candidate scoring is mainly preassigned: the algorithm does not calculate posterior uncertainty.
- `nbe_policy.py` used to insert an unconditional contradiction clarification before checking attempted actions, then insert another after checking history. This could defeat its own escalation logic. The small fix in this PR removes the initial duplicate block and explicitly calls the scores uncalibrated.
- `evaluator.py` checks category-based requirements, not which account of events is best supported. For INR it requires a VERIFIED transaction and DELIVERED observation but accepts ORDER and SHIPMENT presence as fulfillment criteria; it recognizes carrier observations by source/label strings. VERIFIED is not equivalent to VERIFIED_EXTERNAL. For SNAD, photo presence can suffice regardless of independent authenticity. Duplicate transaction checks two transaction nodes, not independently validated duplication of the same order. Generic category checks a transaction node. Do not call these production adjudication standards.
- `dispute_service.py` writes graph + readiness + policy as JSON and creates QUESTION nodes based on actions. Synthetic seed data explicitly uses SYNTHETIC_FIXTURE origin and sometimes VERIFIED status; carrier-check path writes DERIVED_FROM observation→shipment edges. The current API returns an existing PolicyDecision contract, so this PR avoids shared contract changes.
- `benchmarks/run_benchmark.py` evaluates five synthetic, hand-designed scenarios, and manually assigns relevant action IDs. Its fixed-checklist and random baselines are intentionally weak; its transitions/effects overlap with production rule branches. Published aggregate metrics are *in-benchmark results*, not independent generalization or real PayPal effectiveness. This suite should remain a regression/smoke benchmark, not serve as the main research claim.

### Current reasoning vs hard-coded decisions

| Conditional on evidence | Hard-coded implementation |
| --- | --- |
| Shipment absent / present; attempted action seen | Action IDs and candidate templates |
| Carrier observation status | Relevance, purported information gain, friction, utility |
| Explicit contradiction edge | Whether contradiction counts as critical (target type or provenance substrings) |
| Buyer claim and lack of signature | Single next step chosen for that category/status |
| Readiness missing requirement flags | Threshold of zero missing requirements and category-specific completion rules |

## 2. Concrete competing-hypothesis architecture

Begin with *carrier-report hypotheses*, not assertions of physical events or fraud:

- H1: carrier reports delivery to the order's postal code.
- H2: carrier reports delivery to a different postal code.
- H3: carrier reports in-transit, delayed, or exception status.

These are deliberately narrower than conclusions like *buyer received the item*. A delivery scan at the correct ZIP cannot distinguish buyer receipt from doorstep loss, theft, an incorrect unit, or carrier error. Those require additional evidence and possibly human adjudication.

**First independent implementation:** `app/services/hypothesis_engine.py` supplies immutable `HypothesisReview` and `HypothesisAssessment` results; reports `SUPPORTED`, `CONTRADICTED`, `CONFLICTED`, or `UNRESOLVED`; lists supporting and contradicting graph node IDs; describes a *discriminating action ID* with rationale. It is read-only and does not alter readiness, state machine, or the API. It requires a uniquely identified order and shipment, an observation→shipment DERIVED_FROM link, and an eligible carrier observation. The strongest usable provenance tier (`VERIFIED_EXTERNAL`, then `SYNTHETIC_FIXTURE`) is selected without mixing synthetic and external evidence. Merely VERIFIED submitted/model evidence is **not** accepted as external corroboration. These rules assume the upstream provenance tag itself is trustworthy; the analyzer does not authenticate a carrier independently.

**Important limitations:** This initial assessor compares postal codes rather than complete addresses, does not infer which of several carrier scans is chronologically latest, lacks per-event correction/supersession semantics, and does not handle multiple shipments. It abstains when linkage or core facts are inadequate. Conflicting reports are retained rather than averaged. A selected `SYNTHETIC_FIXTURE` observation is explicitly labeled as simulated support. Avoid interpreting it as a probabilistic confidence engine.

**Next architecture, pending coordinator/schema agreement:**

1. Define proposition-specific hypothesis templates for each supported dispute category with mutually exclusive outcomes *where logically justified* and a separate residual/unknown category. Track claim provenance and temporal scope.
2. Introduce `EvidenceObservation` semantics for normalized fact, timestamp, entity binding, authority, observed-vs-inferred, and supersedes relations. Store these fields only through a coordinator-approved schema change.
3. Connect observations to hypotheses using typed, inspectable relevance/entailment/contradiction rules. Record `not discriminating` explicitly and allow independent conflicting evidence.
4. Generate candidate acquisitions for *currently distinguishable* hypotheses. Compute a transparent nonprobabilistic coverage or elimination proxy initially; reserve the term *expected information gain* for a model with empirically measured `P(outcome|action, state)`, appropriate smoothing, and held-out calibration.
5. Reuse the existing `PolicyDecision` externally only after uncertainty and score semantics are coordinated with backend/frontend. Stop on insufficiency, missing authority, conflicts, or exhausted actions and hand off to human review; do not equate handoff with buyer/merchant fault.

### Illustrative contrast

An INR case with a delivered carrier scan at the correct ZIP and a buyer nonreceipt claim can support H1, contradict H2, but still **cannot conclude the buyer actually received the item**. Request carrier handoff evidence. If the carrier later supplies a different ZIP for the same shipment, retain both observation IDs, classify competing reports as `CONFLICTED`, and request reconciliation. Do not force the higher-score story to win.

## 3. Small, testable milestones

- **M0 (this PR):** Correct duplicate contradiction-action generation; add side-effect-free qualitative INR hypothesis assessments; show simulated/external separation and contradictory-report abstention. Keep schemas and HTTP responses unchanged.
- **M1:** Add proposition–observation adapter, explicit facts/timestamps, and graph-linked provenance assertions behind a coordinator-approved interface. Add tests against submitted-as-verified misuse and carrier-correction sequences.
- **M2:** Add eligible-acquisition action inventory with measured availability/friction (including unreachable external API) and repeat-prevention. Compare against existing HeuristicNBEPolicy.
- **M3:** Train/estimate outcome frequencies *only if sufficient independent data exist*. Otherwise publish rule-based ambiguity reduction (not information gain or probabilities).
- **M4:** Held-out and adversarial scenario suite, counterfactual evidence perturbations, evaluator-level regression and safety checks. Gate promotion on performance and abstention quality, not nicer explanations.

## 4. Independent evaluation design

**Data:** Construct synthetic test scenarios independently of policy implementation and action names, with hidden seed/family assignments and held-out structure. Later add consented de-identified real case histories with adjudicator-reviewed labels if available. Split by underlying merchant/carrier/order scenario family, not random near-duplicate rows. Cover INR, SNAD, duplicate, incorrect amount, unauthorized transactions, and unsupported categories. Include unverified uploaded screenshots, synthetic-but-verified fixtures, missing/incomplete ZIP, multiple shipments, delayed/out-of-order scans, conflicting scans, evidence corrections, provider timeouts, and action exhaustion.

**Baselines:** existing fixed checklist, random policy, current heuristic; a simplest missing-requirements prioritizer; and an evidence-presence-only ablation. Where feasible, compare an oracle with complete admissible ground truth as an upper bound. Keep the same acquisition budget, observable evidence, and operational constraints for all policies.

**Measurements:**

- Hypothesis status precision/recall against *labeled carrier reports*; explicit contradiction sensitivity and unsupported-evidence false-positive rate.
- Decision/readiness/escalation outcomes evaluated separately against independent adjudicator requirements.
- Rate of inappropriate `SUPPORTED` reports when origin is submitted/model-only; rate of under/over-abstention on resolvable/unresolvable cases.
- Action usefulness as evidence-obtained-per-action (and per unit measured labor/latency), action repetition, cost, steps, and buyer/merchant contact count.
- Safety invariants: no false claim of external verification, no fund movement, no unilateral adjudication; robustness when observations are added in different orders or are serially corrected.
- If probabilistic NBE is later implemented: held-out Brier score, log loss, calibration curves, uncertainty-reduction calibration by action outcome and confidence intervals. **Not applicable to M0.**

Use bootstrap confidence intervals grouped by scenario family, multiple controlled seeds, paired case-by-case comparisons, and negative results. Freeze evaluation scenario definitions before tuning. Test adversarial counterfactuals such as flipping a ZIP, removing external origin, or replacing a DERIVED_FROM edge. A policy that merely gets five canonical case IDs right has **not** demonstrated generalization.

**This PR's tests are unit/regression tests, not an empirical claim of better investigation accuracy.**

## 5. Required backend interfaces / coordinator requests

1. **Read-only observation feed**: typed fact/value, stable observation ID, evidence-item ID, shipment/order linkage, observation timestamp, source authority and origin, verification type, independent-check audit trail, and supersession marker. This should not depend on label substrings.
2. **Action lifecycle**: typed attempted/failed/available/unavailable outcomes, response time, monetary or labor cost, and receipt of evidence, so an already attempted action cannot be endlessly recommended.
3. **Immutable investigation snapshots**: graph state and read-only evaluation at each decision point, enabling state-conditional, leakage-free offline replay.
4. **Normalized provenance semantics**: distinct cryptographic integrity validation, user-submitted content, simulated adapter response, actual external check, and unresolved conflict. Verified upload integrity must not imply externally verified content.
5. **Optional hypothesis response**: versioned list of hypothesis IDs, status, supporting/contradicting evidence IDs, unexplained evidence, abstention reason, and discriminating action; to be introduced **only after coordinator agreement**.
6. **Benchmark contract**: scenario fixture schema separate from policy action IDs, oracle ground truth hidden from inference code, provider failure simulation, and independent cost accounting.

## Change safety

M0 adds no extra model calls, does not modify graph storage or event state transitions, and does not change any shared Pydantic schema or REST endpoint. The hypothesis analyzer is not silently wired into readiness: that would be a consequential semantics change and must be reviewed with the coordinator.
