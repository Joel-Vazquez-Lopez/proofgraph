# PayPal API Capability Audit & Integration Specification

**Project:** PayPal AI Dispute Investigator  
**Target Event:** PayPal AI Hackathon 2026  
**Audit Date:** October 2026  
**Status:** Living Document  

---

## 1. Executive Summary & Audit Methodology

This audit examines the official PayPal REST API capabilities relevant to dispute investigation and automated case package assembly. Every proposed integration capability is classified under one of three strict standards:

- **`VERIFIED`**: Confirmed through official developer documentation and executed against live sandbox/test endpoints.
- **`DOCUMENTED`**: Officially documented by PayPal Developer documentation, schema validated, and adapter-implemented, awaiting active developer sandbox credentials for live execution.
- **`UNAVAILABLE / SIMULATED`**: Capabilities either not exposed by PayPal REST APIs or outside developer scope (e.g. simulated internal adjudicator decisions, synthetic buyer-seller chats), implemented via explicit local simulation adapters with clear UI provenance markers.

> **Core Engineering Rule:** The application never invents PayPal endpoints, never fabricates dispute states, and never presents simulated adjudication as an official PayPal verdict.

---

## 2. Authentication & OAuth 2.0

### Endpoint
- `POST https://api-m.sandbox.paypal.com/v1/oauth2/token` (Sandbox)
- `POST https://api-m.paypal.com/v1/oauth2/token` (Production)

### Method & Headers
- **Auth:** HTTP Basic Auth (`client_id` : `client_secret`)
- **Headers:** `Accept: application/json`, `Accept-Language: en_US`
- **Body:** `grant_type=client_credentials`

### Scopes Required
- `https://uri.paypal.com/services/disputes/read`
- `https://uri.paypal.com/services/disputes/update`
- `https://uri.paypal.com/services/payments/realtimepayment`
- `https://uri.paypal.com/services/reporting`

### Classification: `DOCUMENTED` / Verified Client Implementation
- The client library implements standard token caching with expiry backoff (default TTL: 32400 seconds) and automatic refresh.

---

## 3. Disputes API (`v1/customer/disputes`)

### A. List Disputes
- **Endpoint:** `GET /v1/customer/disputes`
- **Query Parameters:**
  - `dispute_state`: Filter by states (`REQUIRED_ACTION`, `REQUIRED_OTHER_PARTY_ACTION`, `UNDER_PAYPAL_REVIEW`, `RESOLVED`, `OPEN_INQUIRIES`, `APPEALABLE`)
  - `dispute_life_cycle_stage`: `INQUIRY`, `CHARGEBACK`, `PRE_ARBITRATION`, `CLAIM`
  - `page_size`: 1 to 50 (default 10)
  - `start_time`: ISO 8601 UTC timestamp
- **Classification:** `DOCUMENTED`
- **Response Schema:**
  ```json
  {
    "items": [
      {
        "dispute_id": "PP-D-XXXXX",
        "create_time": "2026-10-01T12:00:00Z",
        "update_time": "2026-10-02T15:30:00Z",
        "dispute_amount": { "currency_code": "USD", "value": "189.99" },
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "dispute_state": "REQUIRED_ACTION",
        "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "dispute_life_cycle_stage": "CHARGEBACK"
      }
    ],
    "links": [...]
  }
  ```

### B. Show Dispute Details
- **Endpoint:** `GET /v1/customer/disputes/{dispute_id}`
- **Classification:** `DOCUMENTED`
- **Extracted Information:**
  - `dispute_id`: Unique identifier
  - `disputed_transactions`: Buyer transaction ID, seller transaction ID, invoice ID, gross amount
  - `reason`: Standard PayPal dispute reason codes:
    - `MERCHANDISE_OR_SERVICE_NOT_RECEIVED` (INR)
    - `MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED` (SNAD)
    - `UNAUTHORISED`
    - `CREDIT_NOT_PROCESSED`
    - `DUPLICATE_TRANSACTION`
    - `INCORRECT_AMOUNT`
  - `status`: `WAITING_FOR_BUYER_RESPONSE`, `WAITING_FOR_SELLER_RESPONSE`, `UNDER_PAYPAL_REVIEW`, `RESOLVED`
  - `dispute_outcome`: Present when closed (`RESOLVED_BUYER_FAVOUR`, `RESOLVED_SELLER_FAVOUR`, etc.)
  - `messages`: Chronological array of buyer and seller messages
  - `evidences`: Prior submitted evidence metadata (`evidence_type`, `documents`, `tracking_info`)
  - `seller_response_due_date`: Strict SLA deadline

### C. Provide Evidence
- **Endpoint:** `POST /v1/customer/disputes/{dispute_id}/provide-evidence`
- **Classification:** `DOCUMENTED`
- **Payload Schema:**
  ```json
  {
    "evidence_type": "PROOF_OF_FULFILLMENT",
    "notes": "Carrier tracking proves delivery to confirmed address.",
    "tracking_info": [
      {
        "carrier_name": "UPS",
        "tracking_number": "1Z9999999999999999"
      }
    ],
    "documents": [
      {
        "name": "delivery_signature_receipt.pdf",
        "url": "https://secure-store.example.com/evidence/123/receipt.pdf"
      }
    ]
  }
  ```
- **Known Limitations:**
  - Individual files cannot exceed 10 MB. Total payload capped at 50 MB.
  - Requires public or presigned secure URL when passing document URLs, or multipart file upload where supported.
  - Requires dispute status in an actionable state (`WAITING_FOR_SELLER_RESPONSE` or `WAITING_FOR_BUYER_RESPONSE`).

### D. Appeal Dispute / Provide Additional Info
- **Endpoint:** `POST /v1/customer/disputes/{dispute_id}/appeal`
- **Classification:** `DOCUMENTED`
- **Applicability:** Only valid within the appeal window after a dispute is resolved.

---

## 4. Orders and Payments APIs

### A. Show Order Details
- **Endpoint:** `GET /v2/checkout/orders/{order_id}`
- **Scope:** `https://uri.paypal.com/services/payments/orders`
- **Classification:** `DOCUMENTED`
- **Key Fields:** `intent`, `purchase_units` (items, shipping destination address, breakdown), `payer` details.

### B. Show Captured Payment Details
- **Endpoint:** `GET /v2/payments/captures/{capture_id}`
- **Classification:** `DOCUMENTED`
- **Key Fields:** `seller_protection` status (`ELIGIBLE`, `PARTIALLY_ELIGIBLE`, `NOT_ELIGIBLE`), `dispute_categories` covered.

---

## 5. Webhooks & Event Notifications

### Dispute Event Types Supported
- `CUSTOMER.DISPUTE.CREATED`
- `CUSTOMER.DISPUTE.RESOLVED`
- `CUSTOMER.DISPUTE.UPDATED`
- `PAYMENT.CAPTURE.DENIED`
- `PAYMENT.CAPTURE.REFUNDED`

### Security Verification
- **Verification Endpoint:** `POST /v1/notifications/verify-webhook-signature`
- **Headers Verified:** `paypal-auth-algo`, `paypal-cert-url`, `paypal-transmission-id`, `paypal-transmission-sig`, `paypal-transmission-time`, `webhook_id`.
- **Classification:** `DOCUMENTED`

---

## 6. Unavailable or Sandbox-Limited Operations

| Operation | Reality in PayPal REST API | Architecture Solution |
| :--- | :--- | :--- |
| **Autonomous Case Adjudication** | PayPal REST API does NOT expose adjudication algorithms or allow 3rd parties to finalize a dispute ruling. | **`UNAVAILABLE / SIMULATED`**: The system acts strictly as an **investigative decision-readiness engine**. It prepares an auditable package for human or PayPal dispute reviewers. |
| **Interactive Question-Answer with Counterparty via API** | Counterparty messaging is limited to the `messages` array during dispute updates; there is no real-time conversational socket or structured Q&A API. | **`SIMULATED ADAPTER`**: The platform provides a portal where the investigating party (merchant or buyer) answers targeted NBE questions and uploads documents. |
| **Carrier Telemetry Sync** | PayPal does not query carrier GPS or doorstep photos directly; merchants submit carrier strings. | **Integrated Tracking Enricher**: Our system integrates carrier mock/carrier tracking verification directly into the evidence graph. |
| **End-to-End Dispute Triggering in Sandbox** | Creating a dispute in Sandbox requires two distinct test accounts (personal buyer + business seller) simulating a checkout, dispute initiation in Sandbox Resolution Center, or via Sandbox dispute testing tools. | **Dual Adapter Strategy**: `PayPalSandboxAdapter` connects to live PayPal sandbox APIs, while `SyntheticDisputeAdapter` supplies verified realistic test fixtures for offline reproducibility. |

---

## 7. Dual Adapter Architecture

To guarantee 100% testability, zero downtime during hackathon evaluation, and transparent provenance:

1. **`PayPalDisputeAdapter` (Abstract Base Class)**:
   - `get_dispute(dispute_id: str) -> DisputeSchema`
   - `list_disputes(filter_params) -> List[DisputeSummary]`
   - `submit_evidence(dispute_id: str, evidence: EvidenceSubmission) -> SubmissionResult`
   - `verify_webhook(payload, headers) -> bool`

2. **`PayPalSandboxAdapter`**:
   - Communicates with `https://api-m.sandbox.paypal.com`.
   - Uses real OAuth token retrieval, JSON payloads, and error handling.
   - Raises structured `PayPalAPIError` with exact error codes if credentials are missing or unauthenticated.

3. **`SyntheticDisputeAdapter`**:
   - Provides fully realistic, deterministic dispute scenarios across:
     - `INR-001`: Item Not Received (Shipped, tracking missing carrier confirmation).
     - `INR-002`: Item Not Received (Delivered to wrong ZIP/address discrepancy).
     - `SNAD-001`: Significantly Not As Described (Counterfeit claim vs authorized distributor invoice).
     - `SNAD-002`: Damaged in Transit (Packaging photo analysis, carrier damage report).
     - `DUP-001`: Duplicate charge (Timestamp correlation, cart idempotency).
   - Marked explicitly with `is_synthetic: true` on all nodes and reports.
