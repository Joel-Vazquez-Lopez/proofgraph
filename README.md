# PayPal AI Dispute Investigator

[![Project Status: Hackathon Prototype](https://img.shields.io/badge/Status-Hackathon_Prototype-orange.svg)](docs/phase-2-audit.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)

> **Submission Project for PayPal AI Hackathon 2026**  
> **Core Principle:** The AI asks fewer, better questions, grounds its conclusions in verifiable evidence, and explicitly acknowledges uncertainty.

---

## Real AI integration — explicit, optional, and unverified

ProofGraph has **two different layers**: deterministic evidence graph / next-evidence policies, and an optional **real OpenAI `gpt-4o-mini` claim extractor** introduced for Issue #18. The backend calls OpenAI's Chat Completions API with strict JSON Schema when an operator sets `AI_PROVIDER=openai` and `OPENAI_API_KEY`, and a reviewer explicitly clicks **Analyze dispute text with AI**. The model proposes quote-grounded assertions and possible evidence questions; each artifact is marked `MODEL_INFERENCE / UNVERIFIED`. It cannot verify facts, change readiness, or decide a dispute. Without configuration it explicitly falls back to deterministic policy, never fake model output.

The deterministic next-action scores described elsewhere in this README are **hand-configured heuristics**, not calibrated probabilities or measured information gain. Image hash/magic-byte checks do **not** authenticate document content. Benchmark percentages are from hand-written synthetic scenarios, **not** real-world dispute accuracy.

**To verify an actual model call**, run the credential-gated live smoke test (default CI mocks the provider and skips the live call):

```bash
export AI_PROVIDER=openai
export OPENAI_MODEL=gpt-4o-mini
export OPENAI_API_KEY="YOUR_REAL_KEY"   # Secret; never commit this
export RUN_LIVE_AI_TEST=1
pytest -v apps/api/tests/test_ai_claim_extractor.py::test_optional_live_openai_claim_extraction
```

See [Issue #18 implementation, safety limits, fallback, and live verification](docs/issue18-real-ai-extraction.md).

---

## 1. Product Vision & Architecture

Payment disputes frequently devolve into cumbersome, asynchronous document dumps between buyers, merchants, and PayPal adjudicators. Existing dispute automation tools (e.g. Chargeflow) treat disputes as passive PDF templating exercises.

The **PayPal AI Dispute Investigator** introduces an active, graph-grounded investigation platform:

1. **Understands the dispute & isolates claims:** Extracts factual claims from buyer statements and merchant logs.
2. **Constructs a Typed Evidence Graph:** Models claims, transactions, orders, shipments, observations, and contradictions using NetworkX and persistent SQL storage.
3. **Next-Best-Evidence (NBE) Selection:** Computes information gain, relevance, and acquisition friction to request the **single most informative piece of evidence** rather than blasting users with generic checklists.
4. **Isolates Contradictions:** Maps discrepancy edges (e.g. carrier delivery address contradicting the order shipping destination).
5. **Calibrated Image & Document Integrity:** Fingerprints evidence with SHA-256, inspects file magic bytes (JPEG, PNG, WEBP, PDF), and flags potential alteration indicators with probabilistic humility.
6. **Deterministic Decision-Readiness Evaluator:** Evaluates dispute-category criteria (Item Not Received, SNAD, Duplicate Charge).
7. **Prepares Auditable Packages:** Produces provenance-linked dossiers for human or PayPal adjudicators.

> ⚠️ **Non-Negotiable Safety Principle:** The AI never unilaterally determines dispute outcomes, moves funds, or auto-refunds. Consequential adjudication is reserved exclusively for authenticated humans or official PayPal reviewers.

---

## 2. Repository Structure

```text
paypal-dispute-investigator/
├── apps/
│   ├── web/                    # Next.js 15 dashboard & React Flow visualization
│   └── api/                    # FastAPI backend, state machine, graph engine, security
│       ├── app/security/       # RBAC authorization & streaming upload validation
│       └── app/services/       # Carrier gateway, graph engine, NBE policies, evaluator
├── packages/
│   └── shared_schemas/         # Typed Pydantic models for graph, NBE & reports
├── docs/
│   ├── paypal-capability-audit.md  # Official PayPal REST API audit & limitations
│   ├── benchmark-methodology.md    # Multi-turn benchmark design & empirical results
│   ├── phase-2-audit.md            # Correctness, provenance & security verification audit
│   ├── competitive-analysis.md     # Chargeflow & market comparison
│   ├── architecture.md             # System architecture & state machine
│   └── security-model.md           # Zero-trust upload & prompt isolation
├── benchmarks/
│   └── run_benchmark.py        # Independent scenario-based simulation benchmark (Scenarios A-E)
├── fixtures/                   # Deterministic offline scenario fixtures
├── docker-compose.yml          # Multi-container local orchestration
├── pytest.ini                  # Pytest runner configuration
└── README.md
```

---

## 3. PayPal REST API Integration Status

Our implementation adheres to strict classification standards documented in [`docs/paypal-capability-audit.md`](docs/paypal-capability-audit.md):

| PayPal Capability | Official REST API | Status in Platform |
| :--- | :--- | :--- |
| **OAuth 2.0 Auth** | `POST /v1/oauth2/token` | **VERIFIED CLIENT** (Sandbox token retrieval & caching) |
| **List Disputes** | `GET /v1/customer/disputes` | **DOCUMENTED** (Filtered by `dispute_state`, `reason`) |
| **Get Dispute Details** | `GET /v1/customer/disputes/{id}` | **DOCUMENTED** (Parsed into evidence graph) |
| **Provide Evidence** | `POST /v1/customer/disputes/{id}/provide-evidence` | **DOCUMENTED** (Fulfillment & tracking payloads) |
| **Dispute Adjudication** | *Internal PayPal only* | **UNAVAILABLE / SIMULATED** (AI prepares handoff dossier) |
| **Offline Scenarios** | *Local test harness* | **VERIFIED** (`SyntheticDisputeAdapter` with explicit provenance tags) |

---

## 4. Quickstart: Running Locally

### Prerequisites
- Python 3.12+ (Python 3.13 supported)
- Node.js 18+ (Node 20+ recommended)
- Git

### A. Start the Backend API

```bash
cd apps/api

# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

*The API is now live at `http://localhost:8000` (Swagger docs: `http://localhost:8000/docs`).*

### B. Start the Web Dashboard

```bash
cd apps/web

# 1. Install dependencies
npm install

# 2. Start Next.js development server
npm run dev
```

*The dashboard is now live at `http://localhost:3000`.*

---

## 5. Verification: Running Automated Tests

Run the full backend test suite covering state machine transitions, graph contradictions, NBE heuristics, image integrity, evidence provenance, adaptive scenarios (A–E), security tenancy, and the vertical slice API:

```bash
# From repository root
apps/api/.venv/bin/pytest -v
```

Expected result:
```text
======================== 33 passed, 2 warnings in 0.58s ========================
```

---

## 6. Running the Empirical Benchmark

Execute the multi-turn scenario simulation benchmark across Scenarios A through E:

```bash
# From repository root
apps/api/.venv/bin/python3 benchmarks/run_benchmark.py
```

### Empirical Benchmark Summary ($N=5$ Canonical Scenarios)

| Policy | Mean Steps | Mean Human Questions | Mean Irrelevant Questions | Critical Coverage | Escalation Accuracy | Readiness Accuracy | Safety Violations |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Fixed Checklist** | 5.0 | 5.0 | 9.0 | 68.3% | 40.0% | 80.0% | 0 |
| **Random / Unguided** | 5.0 | 4.8 | 5.4 | 73.3% | 40.0% | 80.0% | 0 |
| **Heuristic NBE (Ours)** | **2.2** | **0.6** | **0.0** | **78.3%** | **100.0%** | **100.0%** | **0** |

*See [`docs/benchmark-methodology.md`](docs/benchmark-methodology.md) for full experimental setup and analysis.*

---

## 7. Evidence Provenance & Adaptive Investigation (Phase 2)

1. **Elimination of Fabricated Verified Telemetry:**
   A tracking number submitted by a merchant is strictly labeled `origin=USER_SUBMITTED` and `status=UNVERIFIED`. It can never become verified delivery evidence without an explicit, independent carrier verification event.
2. **Cross-Environment Safety Boundary:**
   Disputes originating from `PAYPAL_SANDBOX` are strictly blocked from silently querying synthetic carrier fixtures. If external carrier credentials are unconfigured, uncertainty is explicitly preserved.
3. **Adaptive Investigation Scenarios:**
   - **Scenario A (Confirmed Delivery vs Buyer Non-Receipt):** When carrier reports residence delivery without signature and buyer disputes receipt, the investigator does not dismiss the buyer's claim. It identifies open delivery questions (signature/drop photo) before deciding readiness.
   - **Scenario B (In-Transit / Weather Exception):** Prioritizes automated transit monitoring and preserves in-transit status without demanding irrelevant buyer documents.
   - **Scenario C (Unverified Tracking):** Preserves uncertainty when tracking returns `NOT_FOUND` and requests physical merchant drop-off receipts.
   - **Scenario D (Contradiction):** Detects address mismatches (e.g. Seattle 98101 vs. Portland 97201), requests targeted clarification, and escalates to human review.
   - **Scenario E (Insufficient Evidence):** Prevents infinite polling loops when merchant fulfillment evidence is unavailable, triggering clean human escalation.
4. **Security & Tenancy Enforcement:**
   Role-based access control (`BUYER`, `MERCHANT`, `REVIEWER`, `SYSTEM_ADMIN`) prevents cross-case data leakage. File uploads enforce streaming 10 MB limits, magic byte inspection (JPEG, PNG, WEBP, PDF), and path traversal sanitization.
