# Backend evidence provenance audit — 2026-10-25

Scope: `main` as audited at commit `57047acb991b57da0d0191718afc33f2297d4f95`; targeted fix on `agent/backend`. This is a source-code audit, **not** certification of a production deployment or a live PayPal/carrier integration.

## 1. End-to-end flow map

| Entry point | Ingestion / processing path | Downstream consequence |
| --- | --- | --- |
| `POST /api/v1/disputes/{id}/evidence` | JSON `EvidenceSubmissionRequest` → `verify_case_access` → `DisputeService.process_evidence_submission` | In-memory graph update → readiness evaluator → NBE policy → JSON persistence → `EvidenceSubmissionResult` |
| `POST /api/v1/disputes/{id}/upload-evidence` | Multipart → `validate_and_read_upload` (10 MB, filename sanitation, magic signature) → base64 → same service | Hash and EXIF/PIL integrity finding → `EVIDENCE_ITEM` (originally incorrectly VERIFIED; now UNVERIFIED) → report/detail |
| Tracking fields on either evidence endpoint | `SHIPMENT` marked USER_SUBMITTED/UNVERIFIED → optional `verify_carrier_now` or `action_id=act_carrier_lookup` | `CarrierVerificationService` → OBSERVATION → optional address contradiction/matching shipment update → evaluator |
| `POST /api/v1/disputes/{id}/verify-carrier` | Reads first SHIPMENT → same carrier verification service | Synthetic case: fixture lookup; PAYPAL_SANDBOX case: UNKNOWN placeholder, **not a real external carrier query** |
| `GET /api/v1/disputes/{id}`, `/graph`, `/report` | Deserialize `graph_json` → typed nodes → evaluator/cache or report generator | Client sees `origin`, `verification_status`; report currently collects VERIFIED observations into `verified_facts` without excluding SYNTHETIC_FIXTURE |

Key files: `routers/evidence.py`, `security/file_validator.py`, `security/auth.py`, `services/dispute_service.py`, `services/carrier_service.py`, `services/evidence_graph.py`, `services/evaluator.py`, `services/report_generator.py`, and `packages/shared_schemas/models.py`.

## 2. Incorrect or ambiguous verification states

1. **Fixed in this branch:** Uploaded documents were marked `USER_SUBMITTED / VERIFIED` immediately after local hashing/metadata inspection. The node must remain `USER_SUBMITTED / UNVERIFIED` until an independent corroboration or explicit human audit.
2. **Open; needs Agent 1 + Agent 3 coordination:** Synthetic carrier observations use `SYNTHETIC_FIXTURE / VERIFIED`. `_perform_carrier_verification_internal` treats simulated `DELIVERED`, `IN_TRANSIT`, or `EXCEPTION` as verified, potentially promoting shipments and driving readiness decisions. `VERIFIED` here denotes a *fixture fact*, not a real-world external verification, but downstream code does not consistently enforce that distinction.
3. **Open:** `verify-carrier` return message states "Independent carrier verification executed" even for a simulated fixture or unconfigured gateway. Success presently means the *lookup handler ran*, not that a carrier independently confirmed any fact.
4. **Open:** `SYNTHETIC_FIXTURE / VERIFIED` seed transaction, order, and shipment nodes have authoritative-looking labels (`PAYPAL_API`, `PAYPAL_PAYMENTS`, `CARRIER_TELEMETRY`). The report's "Verified Factual Observations" includes fixture observations, and `evidence_provenance_trail` omits `origin`, encouraging accidental conflation.
5. **Open:** `IntegrityStatus.CONSISTENT` only indicates compatible metadata; a hash fingerprints received bytes but does not authenticate a source or prove document claims. `status` in EVIDENCE_ITEM content means an integrity finding, not `verification_status`.
6. **Open:** Source `PAYPAL_SANDBOX` is not proof of a live PayPal call: the sandbox adapter exists but `DisputeService.list_disputes` / `get_dispute` currently operate on locally stored synthetic scenarios. No live integration execution was performed in this audit.

## 3. Proposed normalized contract (backward-compatible evolution)

**Keep distinct dimensions:**

| Dimension | Proposed interpretation | Example |
| --- | --- | --- |
| `origin` (existing) | Immutable acquisition provenance; NEVER changed solely because content was corroborated | `USER_SUBMITTED`, `SYNTHETIC_FIXTURE`, `VERIFIED_EXTERNAL` |
| `verification_status` (existing) | Real-world claim corroboration; `VERIFIED` reserved for demonstrable independent verification or named human audit | `UNVERIFIED`, `VERIFIED`, `CONTRADICTED`, `INCONCLUSIVE`, `REJECTED` |
| `integrity_status` (existing in integrity finding) | Local byte/metadata assessment; cannot set `verification_status` | `CONSISTENT`, `SUSPICIOUS`, `INCONCLUSIVE` |
| `simulation_status` (proposed) | Fixture-expected outcome kept separate from real-world truth | e.g. `DELIVERED` from a synthetic carrier |
| `verification_method` / `verified_by` / `verified_at` / `verification_audit` (proposed additions, some existing) | Explain exactly who/what verified a claim, the independent reference, timestamp, and limitations | carrier API request ID or human review ID |

Invariants: (a) acceptance / parsing / hash computation / local EXIF assessment **never** sets `VERIFIED`; (b) synthetic fixture values are never independently verified external facts; (c) unavailable gateway → `UNVERIFIED` / `UNKNOWN`; (d) keep `origin` immutable, append explicit audit evidence for verification transitions; (e) contradictory evidence must not be silently overwritten by repeated lookups; (f) JSON endpoint and multipart endpoint must enforce equivalent file-validation limits and MIME semantics.

**Migration / compatibility:** This PR changes only the `EVIDENCE_ITEM.verification_status` value for newly submitted files. No schema, endpoint, enum, or top-level response field changed. Pre-existing JSON graph rows marked VERIFIED by the old code are **not** automatically reclassified; audit and migrate them before treating them as verified. The later normalized contract needs an Agent 1 evaluator policy decision and an Agent 3 UI compatibility review before code changes.

## 4. Security risks (ranked)

| Severity | Risk | Suggested containment |
| --- | --- | --- |
| **Critical for any public/non-demo deployment** | `get_current_user` trusts arbitrary `X-User-Role` / `X-User-Id` headers and defaults to an unrestricted REVIEWER. Clients can impersonate a reviewer, read another user's disputes or submit evidence. | Keep demo endpoint local/restricted; use authenticated, server-verified identity and role claims before internet deployment. |
| **High** | Request `submitter_role` is unrelated to authenticated actor; clients can attribute evidence to MERCHANT or BUYER at will. | Derive actor from authenticated principal and authorize submitter role (coordinate frontend contract). |
| **High** | JSON `file_data_base64` path bypasses multipart's 10 MB size check, content-signature gate, and extension validation; declared MIME is trusted. | Apply shared decoded-byte limits and consistent media checks on both paths, including malformed base64 handling. |
| **High (evidence integrity)** | Simulated carrier events are presented as VERIFIED, then used by readiness and report logic as if independently validated. | Separate fixture truth from verified external evidence in graph, evaluator and report; test scenario impacts. |
| **Medium** | Shipment and observation IDs use only trailing four tracking characters; separate tracking numbers may overwrite nodes, mixing evidence. | Use stable collision-resistant IDs with carrier + full tracking digest; plan compatibility for historic graph IDs. |
| **Medium** | Verification response and timeline claim independent confirmation even when carrier gateway is unconfigured. | Return explicit outcome/method (simulated, unavailable, independent verified) and adjust messaging. |
| **Medium** | Broad `except Exception` exposes raw exception messages, and endpoint distinguishes backend errors inconsistently (400 vs 500). | Return structured public error codes; log detailed internal exceptions privately. |
| **Medium** | No durable upload blob persisted in evidence service; hash only identifies submitted bytes, not retained retrievable evidence; documentation overstates retention/immutability guarantees. | Either persist with integrity checks and retention controls or state metadata-only capability explicitly. |

## 5. Minimum regression-test plan

**Included in this PR:** JSON base64 PDF and multipart PNG upload flows assert `USER_SUBMITTED / UNVERIFIED`, `verified_at=None`, while SHA-256/integrity reporting and API response shape remain intact.

**Next tests, after coordination:** (1) real sandbox case rejects synthetic carrier data; (2) simulated delivery does not count as independent verification in readiness or report; (3) UNKNOWN / NOT_FOUND and contradictory address remain unresolved; (4) repeated or colliding tracking IDs cannot overwrite unrelated evidence; (5) malformed base64, excessive JSON file size, spoofed MIME and truncated content reject safely; (6) forgery of role and submitter identity cannot modify someone else's case; (7) terminal CLOSED and invalid state transitions yield deterministic errors and do not partially commit; (8) PayPal Sandbox tests with mocked HTTP for error mapping, separate opt-in test with real credentials when available; **do not claim live verification based on mocks**.

## Fix scope and verification status

The first correctness patch is in `DisputeService.process_evidence_submission`: uploaded files are now explicitly UNVERIFIED after local integrity analysis. No investigation algorithm policy, shared enum, or frontend response structure was modified. CI is responsible for running `pytest -v` and the benchmark on the PR; confirm exact CI status before merging.
