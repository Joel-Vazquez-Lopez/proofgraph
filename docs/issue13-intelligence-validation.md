# Issue #13 — Evidence-driven investigation acceptance report

**Implementation:** `agent/intelligence-issue13` from `integration/proofgraph-v1`. This PR preserves API payload shapes and leaves the existing heuristic as default. The optional `discriminative` policy is tested separately and still delegates non-INR categories to the heuristic.

## Reproduce

From repository root with Python backend dependencies installed:

```bash
pytest -v
python benchmarks/run_benchmark.py
python benchmarks/evaluate_adaptive_nbe.py
python benchmarks/demo_intelligence.py
```

Frontend CI additionally executes Next.js build and Chromium merchant browser workflow.

## Acceptance behavior

| Category / change | Intended interpretation | Current result |
| --- | --- | --- |
| INR tracking absent | Tracking ID required, not a delivered parcel | Heuristic requests merchant tracking |
| INR submitted/unverified carrier claim | No independent carrier delivery established | Readiness stays incomplete; both policies seek corroborating evidence |
| INR matching ZIP + buyer nonreceipt | ZIP delivery != recipient handoff | Handoff record requested; review cannot close on scan alone |
| INR wrong ZIP or conflicting scans | Material discrepancy even without CONTRADICTS edge | Review required and targeted clarification requested |
| INR signed fixture associated with shipment | Synthetic completeness exercise only | May be ready for human review in fixture; explicitly NOT independently verified |
| SNAD order only | Missing buyer condition evidence and original listing | Buyer photo requested; after submission merchant listing requested |
| SNAD photo + listing | Package available for comparison, not truth of either claim | Ready for human adjudicator review unless contradiction exists |
| Duplicate one payment or uploaded seller assertion | No proof of duplicate debit | Request attributable payment records, then abstain/escalate after exhaustion |
| Duplicate two externally corroborated payments, same order and amount | Two records may indicate duplication but not entitlement | Human-review package complete; no dispute outcome |
| Duplicate different payers / order IDs / amounts | Records not safely comparable | Not decision ready; explicit conflict or missing requirement |
| New contradiction after DECISION_READY | Ready status must be revoked | Transition to REVIEW_REQUIRED supported; API test confirms |
| Real case with unconfigured carrier gateway | Don't recommend non-operational live query | Both heuristic and discriminative mode request merchant carrier records |

Core safety invariant: `VERIFIED` by itself is insufficient. INR transaction and delivery evidence must carry trustworthy external or explicitly synthetic origin, a linked shipment, and meaningful delivery destination. Merchant/buyer uploads remain `USER_SUBMITTED/UNVERIFIED` even when accepted and hash-checked. The `DECISION_READY` state denotes evidence **handoff**, never the adjudicated winner.

## CI and regression comparison

- [Run 40190379036](https://github.com/Joel-Vazquez-Lopez/proofgraph/actions/runs/40190379036): **114 pytest cases passed; three environment/deprecation warnings**, and the legacy five-scenario simulation and separate adaptive challenge ran successfully. Frontend/Chromium statuses must be checked on the run page when reviewing.
- Five legacy simulation scenarios now explicitly connect carrier observations and signed-fixture artifacts to their shipment. This corrects the benchmark's event representation after readiness began requiring provenance and linkage; it does **not** weaken the evaluator.
- Independent *synthetic* 16-family × four-variation policy challenge reports: optional adaptive 60/64 useful first actions, heuristic 40/64; correct escalate/continue 64/64 vs 56/64; 0 vs 4 unavailable actions; 0 vs 0 repeated; limited textual unsupported-verification check 0 vs 4. The controlled synthetic-artifact-acquisition mean (five-step cap, excluding appropriate escalations) is 1.308 vs 2.308.
- The benchmark is not blinded, real-world evidence or probability calibration. Labels are authored scenario requirements. The observed advantage **does not support real PayPal accuracy or win-rate claims**. The baseline policy has been improved in this PR; old claims assuming it would fail missing-provenance or implicit-contradiction cases have been removed from tests.

## Still unresolved

1. **Time-aware carrier reports:** An old transit scan plus a later delivered scan may be treated as a disagreement. The optional policy loses on the seeded temporal-update family. Need timestamps and supersession across providers, not scenario-ID exceptions.
2. **Carrier API availability:** There is no real external gateway. Demo fixtures are explicitly simulated. Production-style cases now avoid recommending the nonexistent lookup, but carrier reports cannot be independently obtained without Backend support.
3. **Actual authenticity:** Uploaded condition photos, merchant listings, payment PDFs and signatures do not become externally verified merely by being uploaded. SNAD/duplicate readiness is package completeness, not evidence truth.
4. **Action lifecycle:** QUESTION nodes approximate requests/attempts. There is not yet an authoritative REQUESTED/COMPLETED/FAILED action-outcome ledger. An action offered but never run may be treated as attempted.
5. **Multi-shipment, address detail, temporal correction:** Competing-shipment attribution is conservative. ZIP equality cannot prove correct doorstep or recipient.
6. **Empirical evaluation:** No held-out real disputes, independently audited outcomes, or calibrated information gain. The legacy heuristic still uses uncalibrated hand-selected scoring constants. The adaptive score is ordinal ambiguity coverage over assigned friction.

Do not enable automated adjudication, represent synthetic results as verified external evidence, or merge without technical coordinator review.
