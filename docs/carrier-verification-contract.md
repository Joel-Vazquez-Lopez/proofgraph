# Carrier lookup and verification semantics

**Scope:** PR A, carrier provenance only. No real external carrier gateway or live PayPal Sandbox request is implemented or claimed.

## Classification

| Case source | Lookup backend | Lookup outcome | Observation origin | Independent external verification? |
| --- | --- | --- | --- | --- |
| `SYNTHETIC_FIXTURE` | `SyntheticCarrierAdapter.KNOWN_RECORDS` | `SIMULATED` with `status=DELIVERED/IN_TRANSIT/EXCEPTION/NOT_FOUND` | `SYNTHETIC_FIXTURE` | **No** |
| `PAYPAL_SANDBOX`, `MERCHANT_ERP`, `BUYER_SUBMISSION`, `CARRIER_API` | No configured carrier provider | `UNAVAILABLE`, `status=UNKNOWN` | `UNVERIFIED` | **No** |
| Future real carrier integration (not implemented) | Trusted external provider, with auditable transaction | `EXTERNALLY_VERIFIED` | `VERIFIED_EXTERNAL` | Only after independent source proof |

A successful POST indicates the application **recorded a lookup attempt/outcome**. It never implies the shipment was independently verified. Every graph observation includes `content.verification_outcome`, `content.independently_verified`, `content.is_synthetic`, `origin`, and `metadata.verification_scope`; the report has an explicit `simulated_facts` list, while `verified_facts` excludes fixture-origin nodes. Timeline messages, labels, and edge provenance identify simulation and unavailable gateways. `verified_at` remains empty for simulated and unavailable lookups.

A merchant-submitted tracking record stays `origin=USER_SUBMITTED`, `verification_status=UNVERIFIED` even if a synthetic fixture happens to match its destination ZIP. The simulated match is retained as `metadata.simulated_crosschecks` and must not upgrade the merchant's real-world claim.

## Backward compatibility

- No endpoint or existing top-level request/response field was removed.
- `InvestigationReport.simulated_facts` is additive, defaulting to `[]`. Existing `verified_facts` is now intentionally **stricter**: fixture facts are no longer included. This is a report behavior change, not a wire incompatibility.
- `evidence_provenance_trail` row dictionaries gain `origin`, `verification_scope`, and `independently_verified`.
- Carrier observation `content` gains `verification_outcome` and `independently_verified`, plus explicit observation metadata.
- `EvidenceSubmissionResult.message` and timeline are more precise, retaining the previous fields. Demo user interface should surface `SIMULATED` distinctly and not render `VERIFIED` alone as an external-confidence badge.
- Existing stored graphs with `origin=SYNTHETIC_FIXTURE` remain classified as simulated in **newly generated reports** even without the new metadata fields. Historic snapshots/exported reports are not rewritten.
- No new persistence table or DB migration is required. All changes are within stored JSON graph/report structures.

## Coordination with Agent 1 (required before readiness change)

The **existing** evaluator and fixture benchmark currently use `verification_status=VERIFIED` on synthetic observations to represent **scenario truth**, not independent real-world confirmation. This PR deliberately maintains the enum in that demo-specific sense, adds an explicit `verification_scope=SIMULATED_FIXTURE`, and excludes fixture facts from externally verified reporting. It does **not** modify `evaluator.py`, `nbe_policy.py`, hypothesis logic, or seeded fixture definitions.

**Decision requested of coordinator / Agent 1:** adopt a two-axis validity contract where `verification_status=VERIFIED` is reserved strictly for real-world corroboration and scenario-grounded facts live in `simulation_status` (or equivalent), with Agent 1's evaluator updated to consume **fixture assumptions under demo mode only**, not generic verified claims. This would change existing readiness semantics, synthetic benchmark labels, and possibly frontend readiness copy. It needs explicit approval and migration/testing before it can replace the conservative compatibility layer.

## Coordination with Agent 3

The frontend must not flatten `verification_status=VERIFIED` without checking `origin` and `verification_scope`. Use `simulated_facts` for demo disclosures and `verified_facts` only for corroborated facts. A successful carrier lookup may be simulated or unavailable; use the explicit outcome rather than the HTTP success state.

## Testing / limitations

Regression coverage includes synthetic known/missing fixture records, nonfixture source isolation, shipment-origin preservation, generated JSON/Markdown reports, no gateway assertions, and the instant-lookup evidence endpoint. Existing scenario/benchmark policy behavior is intentionally unchanged. No live PayPal Sandbox or real carrier provider verification was attempted. No production-grade authentication or tracking ID collision changes are included; those are separate assignments.
