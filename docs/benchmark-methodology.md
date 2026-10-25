# Empirical Benchmark Methodology & Evaluation Report

**Project:** PayPal AI Dispute Investigator  
**Target Event:** PayPal AI Hackathon 2026  
**Module:** Multi-Turn Investigation Benchmark & Policy Evaluation (`benchmarks/run_benchmark.py`)  
**Evaluation Date:** October 2026  

---

## 1. Motivation & Problem Formulation

In conventional dispute processing (e.g., Chargeflow or traditional merchant portals), dispute management is treated either as:
1. **A static checklist:** Merchants and buyers are prompted with broad, exhaustive document requests (invoices, shipping labels, customer support chat transcripts, government IDs) regardless of what has already been verified.
2. **Ad-hoc unstructured inquiry:** Case handlers or naive prompt-based bots ask unstructured, repetitive, or irrelevant questions, driving high consumer friction and lengthy turnaround times.

The **PayPal AI Dispute Investigator** implements an **adaptive, graph-grounded investigation engine**. Instead of relying on rigid forms or unconstrained LLMs, the system employs an evidence-state-aware **Next-Best-Evidence (NBE) policy** that computes information gain, acquisition friction, and contradiction priority to select the single most informative action.

### Critical Benchmark Correction (Phase 2)
In early prototypes, benchmark evaluation incorrectly assessed policies using **utility scores self-assigned by the policies themselves**. This created an echo chamber where a policy could inflate its own score simply by computing a higher internal score.

**Phase 2 Benchmark Overhaul:**
The benchmark has been completely redesigned around an **independent multi-turn simulation environment** with hidden ground truth, explicit evidence acquisition costs, real state updates on the typed evidence graph, and an objective scoring function shared across all policies.

---

## 2. Evaluation Policies

Three distinct investigation policies were evaluated under identical environmental constraints:

| Policy | Classification | Operational Mechanism |
| :--- | :--- | :--- |
| **Fixed Checklist** | Baseline 1 (Status Quo) | Executes a rigid, sequential checklist (past invoices, full shipping label scans, buyer ID/utility bill) regardless of existing verified evidence or carrier scans. |
| **Random / Unguided** | Baseline 2 (Ablation) | Selects uniformly at random from available candidate actions without state awareness, representing unguided or unstructured exploration. |
| **Heuristic NBE (Ours)** | Proposed System | Deterministic, state-aware policy scoring candidates via:$$\text{Utility} = \frac{w_r \cdot \text{Relevance} + w_u \cdot \text{UncertaintyReduction} + w_c \cdot \text{ContradictionWeight}}{1.0 + \text{AcquisitionFriction}}$$ Incorporates loop prevention, contradiction resolution prioritization, and automated API preference. |

---

## 3. Canonical Dispute Scenarios (Scenarios A through E)

The benchmark simulates five canonical dispute scenarios representing the primary operational edge cases in payment disputes:

### Scenario A — Confirmed Delivery Scan vs. Buyer Non-Receipt
* **Context:** Merchant provided carrier tracking. Carrier reports package delivered to destination ZIP (e.g. Springfield 97477) without signature (front-door drop). Buyer claims they never received the package.
* **Ground Truth:** Delivery scan exists, but buyer non-receipt creates an open factual question. Requires delivery confirmation (GPS coordinates or signed delivery slip). Case must not prematurely close or dismiss buyer claim.
* **Expected Outcome:** Case transitions to `INVESTIGATING` with open question; upon delivery proof submission, becomes `DECISION_READY`.

### Scenario B — Undelivered Shipment In-Transit / Weather Delay
* **Context:** Carrier tracking exists, but telemetry indicates shipment is currently `IN_TRANSIT` with a regional weather exception delay.
* **Ground Truth:** Delivery is incomplete. The investigator must not prematurely declare the case decision-ready or demand unrelated documents.
* **Expected Outcome:** Policy schedules carrier transit monitoring; prolonged delays escalate for human adjudicator intervention (`expected_escalation = True`, `is_decision_ready = False`).

### Scenario C — Unverified Tracking Number (Carrier Unknown / Not Found)
* **Context:** Merchant submitted a tracking identifier, but the independent carrier API returns `NOT_FOUND` / `UNKNOWN`.
* **Ground Truth:** Tracking number alone never establishes delivery. Delivery status remains unverified.
* **Expected Outcome:** Policy requests physical carrier acceptance drop-off receipt; if unavailable, halts loops and escalates to human review (`expected_escalation = True`, `is_decision_ready = False`).

### Scenario D — Factual Destination Contradiction (Address Mismatch)
* **Context:** Order specifies destination in Portland, OR (ZIP 97201). Carrier telemetry confirms delivery to Seattle, WA (ZIP 98101).
* **Ground Truth:** Factual discrepancy between carrier delivery record and buyer purchase order.
* **Expected Outcome:** Engine flags contradiction edge. Policy prioritizes address clarification inquiry. When discrepancy persists, immediately escalates to human review (`REVIEW_REQUIRED`) and blocks decision-readiness.

### Scenario E — Insufficient Evidence / Loop Prevention
* **Context:** Merchant failed to provide tracking after inquiry. No shipping records exist.
* **Ground Truth:** Information acquisition path is exhausted. No further automated evidence can be retrieved.
* **Expected Outcome:** Policy recognizes attempted inquiry, prevents infinite polling loops, and triggers immediate escalation to human review (`REVIEW_REQUIRED`).

---

## 4. Evaluation Metrics

Each policy is evaluated across nine quantitative and qualitative dimensions:

1. **Investigation Steps:** Number of multi-turn interactions required to conclude the investigation (max cap: 5).
2. **Human Questions Asked:** Total inquiries directed to human parties (Buyer or Merchant), generating cognitive friction.
3. **Irrelevant Questions:** Inquiries made that were unneeded given the dispute state (e.g. demanding buyer utility bills for an INR dispute, or asking for invoices when the order is verified).
4. **Critical Evidence Coverage (%):** Percentage of ground-truth critical requirements verified in the final evidence graph.
5. **Unresolved Contradictions:** Count of unflagged or unhandled factual contradictions in the final state.
6. **Unsupported Claims:** Count of claims made without supporting verified evidence nodes (must be 0).
7. **Correct Escalation Accuracy (%):** Whether the policy appropriately triggered human escalation when ground truth demanded it (Scenarios B, C, D, E) and avoided unnecessary escalation when resolvable (Scenario A).
8. **Decision-Readiness Accuracy (%):** Whether the policy's final `is_decision_ready` determination aligned with ground-truth adjudicative readiness standards.
9. **Authorization Violations:** Any attempt by an autonomous policy to execute unauthorized monetary transfers, refunds, or unilateral case closures (must be 0).

---

## 5. Empirical Results

All evaluations were executed deterministically using fixed random seeds (`seed=42` for unguided exploration) using Python 3.13 in the project environment.

### Scenario-by-Scenario Matrix

| Scenario | Policy | Steps | Human Questions | Irrelevant Inquiries | Critical Coverage | Escalation Decision | Readiness Match | Auth Violations |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Scenario A** (Delivery vs Non-Receipt) | Fixed Checklist | 5 | 5 | 9 | 50.0% | CORRECT | MISMATCH | 0 |
| | Random / Unguided | 5 | 4 | 4 | 75.0% | CORRECT | MISMATCH | 0 |
| | **Heuristic NBE (Ours)** | **2** | **1** | **0** | **100.0%** | **CORRECT** | **MATCH** | **0** |
| **Scenario B** (In-Transit Delay) | Fixed Checklist | 5 | 5 | 9 | 66.7% | FAIL | MATCH | 0 |
| | Random / Unguided | 5 | 5 | 5 | 66.7% | FAIL | MATCH | 0 |
| | **Heuristic NBE (Ours)** | **3** | **0** | **0** | **66.7%** | **CORRECT** | **MATCH** | **0** |
| **Scenario C** (Unverified Tracking) | Fixed Checklist | 5 | 5 | 9 | 50.0% | FAIL | MATCH | 0 |
| | Random / Unguided | 5 | 5 | 7 | 50.0% | FAIL | MATCH | 0 |
| | **Heuristic NBE (Ours)** | **3** | **1** | **0** | **50.0%** | **CORRECT** | **MATCH** | **0** |
| **Scenario D** (Address Contradiction) | Fixed Checklist | 5 | 5 | 9 | 75.0% | CORRECT | MATCH | 0 |
| | Random / Unguided | 5 | 5 | 4 | 75.0% | CORRECT | MATCH | 0 |
| | **Heuristic NBE (Ours)** | **2** | **1** | **0** | **75.0%** | **CORRECT** | **MATCH** | **0** |
| **Scenario E** (Insufficient Evidence) | Fixed Checklist | 5 | 5 | 9 | 100.0% | FAIL | MATCH | 0 |
| | Random / Unguided | 5 | 5 | 7 | 100.0% | FAIL | MATCH | 0 |
| | **Heuristic NBE (Ours)** | **1** | **0** | **0** | **100.0%** | **CORRECT** | **MATCH** | **0** |

---

### Aggregate Performance Summary ($N = 5$ Scenarios)

| Evaluation Dimension | Fixed Checklist | Random / Unguided | Heuristic NBE (Ours) | Relative Improvement |
| :--- | :---: | :---: | :---: | :---: |
| **Mean Investigation Steps** | 5.0 | 5.0 | **2.2** | **56.0% faster resolution** |
| **Mean Human Questions Asked** | 5.0 | 4.8 | **0.6** | **88.0% question reduction** |
| **Mean Irrelevant Questions** | 9.0 | 5.4 | **0.0** | **100.0% irrelevant inquiry elimination** |
| **Critical Evidence Coverage** | 68.3% | 73.3% | **78.3%** | **+10.0% coverage improvement** |
| **Correct Escalation Accuracy** | 40.0% | 40.0% | **100.0%** | **+60.0% escalation accuracy** |
| **Decision-Readiness Accuracy** | 80.0% | 80.0% | **100.0%** | **+20.0% readiness precision** |
| **Authorization Violations** | 0 | 0 | **0** | **Zero safety violations (Invariant preserved)** |

---

## 6. Analysis of Key Findings

1. **Dramatic Human Friction Reduction (88% reduction in questions):**
   The Fixed Checklist asked an average of 5.0 questions per dispute, placing significant burden on merchants and buyers for documents already present in PayPal payment records. Heuristic NBE reduced this to **0.6 questions per dispute**, querying automated carrier APIs first before bothering human participants.
2. **Elimination of Irrelevant Inquiries (0.0 irrelevant questions):**
   The heuristic policy only requests evidence when an active gap or contradiction exists. It never asks for utility bills, proof of identity, or unrelated invoice histories on simple delivery verification cases.
3. **Robust Loop Prevention & Escalation (100% accuracy):**
   When evidence acquisition paths were exhausted (Scenario E) or blocked by unresolvable physical discrepancies (Scenario D), Heuristic NBE halted within 1–2 steps and escalated to human review with full provenance audit notes. Baselines blindly repeated the same questions up to the step limit.
4. **Adherence to Non-Negotiable Safety Principles:**
   Across all runs, **zero authorization violations occurred**. Policies do not have permission to execute refunds, debit merchant accounts, or close disputes unilaterally. Consequential actions remain strictly human-supervised.

---

## 7. Limitations & Future Extensions

- **Sample Size:** Benchmark currently evaluates 5 canonical dispute scenarios across Item Not Received (INR). While these cover the major failure modes identified in production audits, future benchmark iterations should expand to 50+ synthetic cases across SNAD and unauthorized transactions.
- **LLM-Assisted Policy Comparison:** An LLM-assisted policy was intentionally excluded from quantitative comparison in Phase 2 because non-deterministic generation introduces prompt sensitivity and potential hallucinations without strict schema grounding. Once calibrated JSON schema outputs with temperature 0.0 are finalized, an LLM-guided policy will be benchmarked under identical constraints.
- **Carrier API Availability:** Synthetic carrier fixtures were used for the simulation. Real carrier gateways (USPS, FedEx, UPS) exhibit network latency and occasional tracking API downtime, which should be modeled with simulated packet drops in future stress testing.
