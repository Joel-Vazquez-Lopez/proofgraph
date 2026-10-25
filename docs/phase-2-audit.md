# Phase 2 Engineering Audit & Verification Report

**Project:** PayPal AI Dispute Investigator  
**Target Submission:** PayPal AI Hackathon 2026  
**Audit Scope:** Evidence Integrity, Correctness, Provenance Model, Adaptive Scenarios, Security Boundaries, and Objective Benchmark  
**Date of Audit:** October 2026  
**Auditor Classification:** Lead Software Engineer & AI Systems Architect  

---

## Executive Summary

Phase 2 was initiated following an independent technical review that uncovered critical correctness, evidence fabrication, authorization, and benchmark evaluation flaws in the initial prototype. Over the course of Phase 2 development:

1. **Eliminated Fabricated Verified Telemetry:** Submitting a carrier tracking number no longer automatically generates synthetic verified delivery observations. A tracking number alone remains strictly `origin=USER_SUBMITTED` and `status=UNVERIFIED` until an independent verification event occurs.
2. **Introduced Rigorous Provenance Model:** Separated evidence origin (`VERIFIED_EXTERNAL`, `USER_SUBMITTED`, `SYNTHETIC_FIXTURE`, `MODEL_INFERENCE`, `UNVERIFIED`) from verification status (`UNVERIFIED`, `VERIFIED`, `REJECTED`, `CONTRADICTED`), with explicit auditable transition logs and timestamps.
3. **Established Cross-Environment Safety Boundary:** Sealed real `PAYPAL_SANDBOX` cases against silently ingesting synthetic carrier fixtures. Unconfigured carrier integrations explicitly preserve uncertainty.
4. **Implemented Adaptive Scenarios (A through E):** Engineered nuanced investigation policies for confirmed delivery without signature (Scenario A), in-transit weather exceptions (Scenario B), unverified carrier tracking (Scenario C), destination address contradictions (Scenario D), and merchant unresponsiveness / loop prevention (Scenario E).
5. **Redesigned Independent Empirical Benchmark:** Replaced self-assigned utility metrics with an independent multi-turn simulation environment evaluating `FixedChecklistPolicy`, `RandomUnguidedPolicy`, and `HeuristicNBEPolicy` across all canonical scenarios.
6. **Enforced Security, Tenancy & Safe Ingestion:** Implemented RBAC tenancy (`BUYER`, `MERCHANT`, `REVIEWER`, `SYSTEM_ADMIN`) to prevent cross-case data leakage, streaming 10 MB upload limits to prevent memory exhaustion, magic byte validation (JPEG, PNG, WEBP, PDF), and filename sanitization against path traversal.
7. **Expanded Automated Test Suite to 33 Tests:** 100% test pass rate across unit, scenario, security, provenance, and vertical-slice suites.

---

## 1. Correctness Audit: Elimination of Fabricated Evidence

### Prior Vulnerability
In the Phase 1 implementation of `apps/api/app/services/dispute_service.py`, whenever a user or test submitted a tracking number (e.g. `USPS 940010009999`), the service immediately generated a carrier telemetry observation node with `status="DELIVERED"` and marked it as `verification_status=VERIFIED`. This falsely represented user-supplied text as independently verified carrier data.

### Phase 2 Remediation
- **Separation of Submission from Verification:** When a tracking number is submitted via `POST /disputes/{id}/evidence` or `/upload-evidence`, the system only creates or updates a `SHIPMENT` node with:
  ```python
  origin = EvidenceOrigin.USER_SUBMITTED
  verification_status = EvidenceVerificationStatus.UNVERIFIED
  ```
- **Explicit Verification Event Required:** Carrier delivery observations are **only** generated when an independent verification event is explicitly dispatched (via `POST /disputes/{id}/verify-carrier` or `verify_carrier_now=True`).
- **Audit Logging:** Every verification event records the verifier source, timestamp, and audit notes inside the node's `verification_audit` metadata.

---

## 2. Evidence Provenance Model

Evidence origin and verification status are decoupled into independent dimensions:

```text
EvidenceOrigin:
  ├── VERIFIED_EXTERNAL    (Directly fetched from PayPal Payments, live Carrier APIs)
  ├── USER_SUBMITTED       (Uploaded by Buyer or Merchant, e.g. receipt, statement, tracking#)
  ├── SYNTHETIC_FIXTURE    (Explicitly tagged offline simulation scenario)
  ├── MODEL_INFERENCE      (Generated questions or suggestions from NBE policy)
  └── UNVERIFIED           (Default unverified state)

EvidenceVerificationStatus:
  ├── UNVERIFIED           (Initial state for user submissions)
  ├── VERIFIED             (Corroborated by independent external source or audit)
  ├── CONTRADICTED         (Directly challenged by contradictory evidence edge)
  └── REJECTED             (Failed integrity validation, e.g. corrupted magic bytes)
```

### Verification Transition Invariant
A node maintains its historical origin throughout its lifecycle. For example, a receipt uploaded by a buyer starts as `USER_SUBMITTED / UNVERIFIED`. Following adjudicator or ERP cross-reference, it transitions to `USER_SUBMITTED / VERIFIED`. Origin is immutable; status is transitionable.

---

## 3. Cross-Environment Safety Boundary

To ensure synthetic demonstration data can never contaminate real PayPal accounts:

1. **`CarrierVerificationService` Environment Check:**
   When `CarrierVerificationService.verify_tracking(...)` is called:
   - If `case_data_source == DataSourceType.PAYPAL_SANDBOX`, it is strictly forbidden from querying `SyntheticCarrierAdapter`.
   - If the external live carrier gateway is unconfigured, it returns `status="UNKNOWN"` and `origin=EvidenceOrigin.UNVERIFIED` with an explicit audit note:
     > *"External carrier telemetry query unconfigured or pending carrier sync. Tracking status remains UNVERIFIED. Cannot assume delivery."*
   - Only cases explicitly flagged as `SYNTHETIC_FIXTURE` are allowed to resolve against synthetic carrier fixtures.
2. **Automated Regression Test:**
   `test_paypal_sandbox_cannot_silently_ingest_synthetic_carrier_fixtures` in `apps/api/tests/test_provenance.py` proves this boundary is strictly enforced.

---

## 4. Adaptive Investigation Scenarios (A through E)

The investigation engine and `HeuristicNBEPolicy` adapt dynamically to five distinct evidence states:

### Scenario A — Confirmed Delivery vs. Buyer Non-Receipt
* **Challenge:** A carrier records delivery to the correct destination ZIP, but the recipient did not sign (front-door porch drop). The buyer claims the package was never received.
* **Engine Response:** In `evaluator.py`, the engine acknowledges the carrier scan but refuses to dismiss the buyer's claim. It identifies an open delivery question and prompts the merchant for carrier signature records, GPS delivery coordinates, or drop photos before reaching decision-readiness.

### Scenario B — Shipment In-Transit / Weather Delay
* **Challenge:** Carrier telemetry indicates `IN_TRANSIT` with a severe weather exception.
* **Engine Response:** Recognizes that delivery is pending. Rather than demanding unnecessary buyer documents, the policy prioritizes `act_carrier_transit_monitor`. If delayed beyond the expected window, it escalates to human review.

### Scenario C — Unknown / Unverified Delivery
* **Challenge:** Merchant submitted tracking, but carrier query returns `NOT_FOUND`.
* **Engine Response:** Preserves uncertainty. Does not assume delivery. Prompts merchant for an official physical carrier drop-off receipt; if unavailable, escalates.

### Scenario D — Factual Destination Contradiction
* **Challenge:** Order specifies Portland, OR 97201; carrier scan indicates delivery to Seattle, WA 98101.
* **Engine Response:** Forms a directed `CONTRADICTS` edge in the evidence graph. This immediately blocks `DECISION_READY` and forces `recommended_state = REVIEW_REQUIRED`. The policy prompts the buyer for address clarification, and once verified, escalates to human adjudication.

### Scenario E — Insufficient Evidence & Loop Prevention
* **Challenge:** Necessary evidence (fulfillment tracking) is unavailable, and the merchant has already been queried once.
* **Engine Response:** Detects that `act_merchant_tracking` exists in `attempted_actions`. Prevents infinite inquiry loops and triggers immediate escalation (`ESCALATE_HUMAN_REVIEW`) within 1 turn.

---

## 5. Objective Benchmark Redesign & Empirical Results

The flawed self-scored benchmark was replaced by an independent multi-turn simulation framework (`benchmarks/run_benchmark.py`).

### Summary of Empirical Findings ($N = 5$ Scenarios)

| Metric | Fixed Checklist | Random / Unguided | Heuristic NBE (Ours) | Relative Impact |
| :--- | :---: | :---: | :---: | :---: |
| **Mean Turns / Steps** | 5.0 | 5.0 | **2.2** | **56.0% faster case assembly** |
| **Mean Human Questions** | 5.0 | 4.8 | **0.6** | **88.0% question reduction** |
| **Mean Irrelevant Questions** | 9.0 | 5.4 | **0.0** | **100.0% elimination of wasted inquiries** |
| **Critical Evidence Coverage** | 68.3% | 73.3% | **78.3%** | **+10.0% coverage gain** |
| **Escalation Accuracy** | 40.0% | 40.0% | **100.0%** | **+60.0% escalation precision** |
| **Decision-Readiness Accuracy**| 80.0% | 80.0% | **100.0%** | **+20.0% readiness precision** |
| **Authorization Violations** | 0 | 0 | **0** | **Zero safety breaches** |

*Methodology documented in [`docs/benchmark-methodology.md`](benchmark-methodology.md).*

---

## 6. Security & Tenancy Architecture

### A. Case Tenancy & Role-Based Access Control (RBAC)
Implemented in `app/security/auth.py`:
- Identities authenticate via `X-User-Role` (`BUYER`, `MERCHANT`, `REVIEWER`, `SYSTEM_ADMIN`) and `X-User-Id`.
- **Tenancy Enforcement:** `verify_case_access` ensures that a buyer can only access disputes where `case.buyer_id == auth.user_id`, and a merchant can only access disputes where `case.seller_id == auth.user_id`. Unauthorized cross-case requests are rejected with `403 Forbidden`.
- **Consequential Action Guard:** Unilateral adjudication actions, state overrides, and external submissions require `require_consequential_action_permission` (restricted strictly to `REVIEWER` or `SYSTEM_ADMIN`).

### B. Secure Streaming File Upload & Magic Byte Inspection
Implemented in `app/security/file_validator.py`:
- **Streaming Upload Limit:** File uploads are read in 64 KB chunks up to a strict **10 MB limit** (`MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024`). Files exceeding this size are rejected with `413 Content Too Large` before loading into memory.
- **Magic Byte Verification:** File extensions are ignored for type validation. Headers are inspected for authentic byte signatures:
  - JPEG: `\xff\xd8\xff`
  - PNG: `\x89PNG\r\n\x1a\n`
  - WEBP: `RIFF....WEBP`
  - PDF: `%PDF-`
  Spoofed files (e.g. text/scripts renamed to `.jpg`) are rejected with `400 Bad Request`.
- **Path Traversal Sanitization:** Filenames are sanitized via `sanitize_filename` to strip null bytes, directory separators (`/`, `\`), and leading dots (`..`), preventing local file overwrite vulnerabilities.

### C. Prompt Injection & AI Safety Isolation
- LLM policies and deterministic heuristics operate strictly over typed Pydantic data models.
- Raw user text in buyer claims or notes is treated as unverified data content; it is never interpolated into executable prompts or trusted for state transitions.

---

## 7. Verification & Automated Test Suite

The automated test suite in `apps/api/tests/` was expanded from 18 to **33 passing tests**:

```text
============================= test session starts ==============================
platform darwin -- Python 3.13.13, pytest-9.1.1
rootdir: /Users/joelvazquezlopez/.gemini/antigravity/scratch/paypal-dispute-investigator
testpaths: apps/api/tests

apps/api/tests/test_api_endpoints.py::test_health_endpoint PASSED        [  3%]
apps/api/tests/test_api_endpoints.py::test_list_disputes PASSED          [  6%]
apps/api/tests/test_api_endpoints.py::test_get_dispute_and_graph PASSED  [  9%]
apps/api/tests/test_api_endpoints.py::test_end_to_end_inr_investigation_slice PASSED [ 12%]
apps/api/tests/test_evaluator.py::test_inr_missing_tracking_not_ready PASSED [ 15%]
apps/api/tests/test_evaluator.py::test_inr_fulfilled_and_delivered_is_ready PASSED [ 18%]
apps/api/tests/test_evaluator.py::test_inr_with_contradiction_escalates PASSED [ 21%]
apps/api/tests/test_evidence_graph.py::test_evidence_graph_nodes_and_edges PASSED [ 24%]
apps/api/tests/test_evidence_graph.py::test_contradiction_detection PASSED [ 27%]
apps/api/tests/test_evidence_graph.py::test_open_questions_and_answering PASSED [ 30%]
apps/api/tests/test_image_integrity.py::test_image_hashing_and_consistency PASSED [ 33%]
apps/api/tests/test_image_integrity.py::test_pdf_or_binary_fallback PASSED [ 36%]
apps/api/tests/test_nbe_policy.py::test_nbe_selects_tracking_when_missing PASSED [ 39%]
apps/api/tests/test_nbe_policy.py::test_nbe_prioritizes_automated_carrier_lookup_over_manual_outreach PASSED [ 42%]
apps/api/tests/test_nbe_policy.py::test_nbe_prioritizes_resolving_contradiction PASSED [ 45%]
apps/api/tests/test_provenance.py::test_origin_and_verification_status_separation PASSED [ 48%]
apps/api/tests/test_provenance.py::test_tracking_alone_cannot_establish_verified_delivery PASSED [ 51%]
apps/api/tests/test_provenance.py::test_paypal_sandbox_cannot_silently_ingest_synthetic_carrier_fixtures PASSED [ 54%]
apps/api/tests/test_scenarios.py::test_scenario_a_confirmed_delivery_preserves_unresolved_claim PASSED [ 57%]
apps/api/tests/test_scenarios.py::test_scenario_b_no_delivery_in_transit PASSED [ 60%]
apps/api/tests/test_scenarios.py::test_scenario_c_unknown_delivery_unverified_tracking PASSED [ 63%]
apps/api/tests/test_scenarios.py::test_scenario_d_contradictory_evidence_address_mismatch PASSED [ 66%]
apps/api/tests/test_scenarios.py::test_scenario_e_insufficient_evidence_loop_prevention PASSED [ 69%]
apps/api/tests/test_security.py::test_path_traversal_sanitization PASSED [ 72%]
apps/api/tests/test_security.py::test_magic_bytes_inspection PASSED      [ 75%]
apps/api/tests/test_security.py::test_case_access_tenancy_buyer_blocked_from_other_cases PASSED [ 78%]
apps/api/tests/test_security.py::test_case_access_tenancy_merchant_blocked_from_other_merchants PASSED [ 81%]
apps/api/tests/test_security.py::test_invalid_role_rejected PASSED       [ 84%]
apps/api/tests/test_security.py::test_upload_file_rejected_if_magic_bytes_invalid PASSED [ 87%]
apps/api/tests/test_security.py::test_upload_file_rejected_if_exceeds_size_limit PASSED [ 90%]
apps/api/tests/test_state_machine.py::test_valid_state_transitions PASSED [ 93%]
apps/api/tests/test_state_machine.py::test_invalid_state_transitions PASSED [ 96%]
apps/api/tests/test_state_machine.py::test_idempotent_transition PASSED  [100%]

======================== 33 passed, 2 warnings in 0.58s ========================
```

---

## 8. Repository Hygiene & Integrity Checklist

- [x] Removed misleading GitHub badges (`paypal/ai-dispute-investigator`).
- [x] Explicitly documented hackathon prototype identity in README and docs.
- [x] Strict isolation between live PayPal Sandbox queries and synthetic carrier fixtures.
- [x] Zero-tolerance for automated unilateral payments or refunds.
- [x] Fully reproducible benchmark runner with independent environment simulation.
- [x] Complete test suite passing with zero failures.
