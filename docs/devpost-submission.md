# Devpost Submission Package: PayPal AI Dispute Investigator

**Hackathon:** PayPal AI Hackathon 2026 — *Build what's next with PayPal and AI*  
**Submission Deadline:** November 12, 2026 @ 9:00pm GMT+1  
**Project Repository:** Public Git Repository with MIT License  

---

## 1. Project Title & Elevator Pitch

### Project Title
**PayPal AI Dispute Investigator**

### Tagline / Elevator Pitch (Under 140 Characters)
> *Active, graph-grounded AI agent for PayPal disputes that asks fewer, better questions and builds decision-ready case dossiers.* (125 characters)

---

## 2. Devpost Submission Fields (Ready to Copy & Paste)

### Inspiration
Every day, PayPal moves money for millions of consumers and businesses across the globe. But when transactions go wrong, payment disputes frequently devolve into cumbersome, adversarial document dumps.

Traditional dispute automation tools (like Chargeflow) treat disputes as passive PDF templating exercises—blasting merchants and buyers with exhaustive checklists for invoices, tracking numbers, and utility bills regardless of what is already verified. Case handlers are forced to parse conflicting statements across disjointed email threads, delaying resolution for weeks.

We asked: **What happens when you put an active, evidence-grounded AI agent behind the wheel of dispute resolution?**

Not an AI that arrogantly decides who wins or moves funds unilaterally, but an agent that:
1. **Understands the dispute** and isolates the precise factual claims.
2. **Builds a typed, verifiable evidence graph** of transactions, orders, shipments, and carrier observations.
3. **Asks fewer, better questions** by calculating the *Next-Best-Evidence* action that maximizes information gain while minimizing human friction.
4. **Detects physical contradictions** (such as carrier delivery to Seattle when the purchase order was for Portland).
5. **Assembles a transparent, decision-ready adjudication dossier** for authorized human and PayPal dispute reviewers.

---

### What It Does
The **PayPal AI Dispute Investigator** is a production-oriented, full-stack dispute investigation platform:

- **PayPal Developer Platform Integration:** Integrates with the official PayPal REST APIs (`/v1/customer/disputes`, `/v1/oauth2/token`, Orders, and Payments) to ingest live dispute metadata, buyer claims, transaction amounts, and settlement logs.
- **Typed Evidence Graph:** Backed by NetworkX and persistent SQL storage, modeling dispute claims, merchant orders, carrier tracking, physical observations, and contradictions as first-class graph entities.
- **Next-Best-Evidence (NBE) Policy:** Uses a principled heuristic selection policy:
  $$\text{Utility} = \frac{w_r \cdot \text{Relevance} + w_u \cdot \text{UncertaintyReduction} + w_c \cdot \text{ContradictionWeight}}{1.0 + \text{AcquisitionFriction}}$$
  It queries zero-friction automated carrier APIs first before placing burden on human users.
- **Evidence Provenance & Integrity Model:** Strictly decouples evidence origin (`VERIFIED_EXTERNAL`, `USER_SUBMITTED`, `SYNTHETIC_FIXTURE`, `MODEL_INFERENCE`, `UNVERIFIED`) from verification status. A user-submitted tracking number alone can *never* establish delivery without an independent carrier verification event.
- **Adaptive Scenarios (A through E):** Gracefully navigates front-door porch drops without signature, in-transit weather exceptions, unverified tracking numbers, destination address mismatches, and unresponsive merchants with loop prevention.
- **Deterministic Decision-Readiness Evaluator:** Evaluates dispute criteria (Item Not Received, SNAD, Duplicate Charge) to determine when a case satisfies handoff standards.
- **Interactive Web Workspace (Next.js 15):** Features a human-friendly Case Overview, an interactive React Flow graph with non-overlapping hierarchical nodes and live discrepancy highlights, one-click carrier telemetry verification, a secure 10 MB drag-and-drop file upload dropzone with magic-byte validation (JPEG, PNG, WEBP, PDF), and exportable Markdown adjudication dossiers.

---

### How We Built It
We engineered a clean, modular full-stack architecture:

1. **Backend & Graph Engine (FastAPI & Python 3.13):**
   - **NetworkX:** Directed, typed multigraph tracking evidence provenance and contradiction cycles.
   - **SQLAlchemy & SQLite:** Persistent storage of dispute cases, graph nodes, edges, and immutable audit timelines.
   - **Pydantic v2:** End-to-end schema validation across all shared models.
   - **Carrier Gateway Adapter:** Isolated simulation adapter for synthetic demonstration fixtures, with cross-environment security gates blocking real PayPal Sandbox cases from ingesting synthetic data.
   - **Security Layer:** Role-Based Access Control (`BUYER`, `MERCHANT`, `REVIEWER`, `SYSTEM_ADMIN`) enforcing tenancy, streaming file upload limits (10 MB chunk inspection), and binary magic-byte verification.
2. **Frontend Investigation Workspace (Next.js 15 & React 19):**
   - **React Flow (@xyflow/react):** Custom hierarchical DAG layout with distinct semantic borders, animated contradiction edges, and interactive node inspection drawers.
   - **Tailwind CSS & Lucide Icons:** Modern, responsive, PayPal-branded dashboard featuring instant case search, status filtering, and an AI Recommended Next Action banner with one-click action triggers.
3. **Independent Empirical Benchmark:**
   - Multi-turn simulation framework (`benchmarks/run_benchmark.py`) evaluating 3 policies across 5 canonical scenarios against hidden ground truth.

---

### Non-Negotiable Safety Principles
A central tenet of our design is **human-in-the-loop safety**:
- **No Unilateral Adjudication:** The AI never automatically issues refunds, moves money, or unilaterally closes disputes.
- **Provenance Integrity:** Generated or simulated data is never labeled as independently verified.
- **Humility in Uncertainty:** Missing evidence is not treated as proof of dishonesty, and AI detectors are treated probabilistically rather than as definitive fraud verdicts.
- **Human Authorization:** Consequential actions and final adjudications remain strictly reserved for authenticated human reviewers.

---

### Challenges We Ran Into
- **The Evidence Fabrication Trap:** In early builds, receiving a tracking number immediately generated a "DELIVERED" observation. We recognized this as a fundamental flaw: user-submitted text must remain unverified until an explicit, external carrier verification event occurs. Decoupling origin from verification status required a complete overhaul of our graph models.
- **Cross-Environment Isolation:** Ensuring that demonstration fixtures could never silently bleed into live PayPal Sandbox disputes. We built explicit safety gates in `CarrierVerificationService` to enforce this boundary.
- **Graph Layout Overlaps:** Tree layouts in React Flow frequently cause edge labels to intersect node boxes. We redesigned the positioning algorithm into distinct 4-tier horizontal bands with generous spacing and pill badges.
- **Avoiding Benchmark Self-Evaluation:** Replacing a self-scoring benchmark with an independent multi-turn simulation environment that measures real human friction, question counts, and critical evidence coverage against hidden ground truth.

---

### Accomplishments That We're Proud Of
- **88% Reduction in Human Questions:** In our empirical multi-turn benchmark ($N = 5$ canonical scenarios), our Heuristic NBE policy asked an average of **0.6 questions per dispute** compared to **5.0 questions** for the fixed checklist baseline.
- **100% Irrelevant Question Elimination:** Reduced irrelevant inquiries from 9.0 to 0.0 by intelligently prioritizing automated API queries over generic document demands.
- **100% Escalation & Readiness Accuracy:** Handled address contradictions and unresponsive merchants by cleanly escalating to human review without infinite loops.
- **Zero Safety Violations:** Exactly 0 unauthorized fund transfers or unilateral closures across all benchmark and test runs.
- **33 Automated Unit, Scenario & Security Tests:** Full automated test suite passing in under 1 second.

---

### What We Learned
- **Provenance is Everything in Dispute Resolution:** An evidence system must track not just *what* was submitted, but *who* submitted it, *when*, and *through what verified channel*.
- **AI's Best Role is Case Preparation, Not Adjudication:** In high-stakes financial operations, users and merchants distrust "black box" automated decisions. But they love an AI that organizes the case, clarifies discrepancies, and eliminates 90% of paperwork friction.

---

### What's Next for PayPal AI Dispute Investigator
- **Live PayPal Webhook Streaming:** Ingesting real-time dispute dispute events (`CUSTOMER.DISPUTE.CREATED`, `CUSTOMER.DISPUTE.UPDATED`) via PayPal Webhooks.
- **Multi-Carrier Gateway Expansion:** Direct integration with live FedEx, UPS, and DHL APIs using enterprise webhook notifications.
- **Calibrated Multi-Modal LLM Evidence Extraction:** Extracting line-item receipts and damage photos with strict JSON Schema constrained generation.

---

## 3. Built With (Tags for Devpost)

`python` `fastapi` `next.js` `react` `typescript` `tailwind-css` `paypal-api` `networkx` `pydantic` `sqlite` `ai-agents` `machine-learning` `fintech` `docker`

---

## 4. Try It Out / Verification Instructions for Judges

### Option 1: One-Command Startup (Recommended)
Clone the repository and run:
```bash
git clone <repository-url>
cd paypal-dispute-investigator
./run.sh
```
- **Dashboard UI:** http://localhost:3000
- **FastAPI Interactive Docs:** http://localhost:8000/docs

### Option 2: Docker Compose
```bash
docker-compose up --build
```

### Option 3: Run Automated Test Suite (33 Tests)
```bash
apps/api/.venv/bin/pytest -v
```

### Option 4: Run Empirical Multi-Turn Benchmark
```bash
apps/api/.venv/bin/python3 benchmarks/run_benchmark.py
```
