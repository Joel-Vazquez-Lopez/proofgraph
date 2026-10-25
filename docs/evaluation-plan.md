# Empirical Evaluation Plan & Benchmark Specification

**Project:** PayPal AI Dispute Investigator  
**Objective:** Scientifically evaluate active Next-Best-Evidence (NBE) selection vs standard baselines across critical investigation metrics.

---

## 1. Investigation Policy Baselines

We compare three distinct policies on an identical synthetic benchmark suite:

1. **Baseline A (Fixed Checklist):**
   - Asks a static, fixed list of 5-8 questions for every dispute category regardless of existing records or claims.
   - Represents traditional manual dispute operations and basic forms.

2. **Baseline B (Generic Unstructured LLM):**
   - Prompts an LLM with the full dispute text and asks: *"What questions should we ask the customer or merchant?"*
   - Unconstrained by graph state, contradiction edges, or acquisition cost.

3. **Proposed Approach (Evidence-State-Aware Next-Best-Evidence):**
   - Examines active graph requirements, identifies minimal missing claims, calculates uncertainty reduction divided by acquisition friction, and selects exactly one highest-utility question.

---

## 2. Quantitative Evaluation Metrics

1. **Steps to Decision-Readiness:**
   Mean number of investigation inquiry turns required before the case reaches `DECISION_READY` or `REVIEW_REQUIRED`.
2. **Irrelevant Question Ratio (%):**
   Percentage of questions asked that query information already verified or non-material to the dispute outcome.
3. **Critical Evidence Coverage (%):**
   Percentage of mandatory adjudication criteria satisfied upon reaching completion.
4. **Contradiction Resolution Rate (%):**
   Ability of the policy to explicitly identify and resolve discrepancies (e.g. tracking address vs order address).
5. **Human Friction Score:**
   Aggregated weight of manual interventions requested from the end user.

---

## 3. Benchmark Dataset Scenarios

The benchmark fixtures live in `benchmarks/fixtures/`:
- `INR_01_CLEAR_DELIVERY`: Seller fulfilled, valid carrier tracking, delivered to matching address. (Expectation: 1 automated carrier check $\to$ `DECISION_READY`).
- `INR_02_WRONG_ADDRESS`: Tracking shows delivered, but carrier ZIP differs from checkout address. (Expectation: Contradiction detected $\to$ Target inquiry $\to$ `REVIEW_REQUIRED`).
- `INR_03_CARRIER_LOST`: Tracking stuck at facility for 21 days with exception status. (Expectation: Lost in transit identified $\to$ `DECISION_READY`).
- `SNAD_01_DEFECTIVE`: Buyer claims item arrived shattered. Merchant had fragile packaging. (Expectation: Request targeted damaged unboxing photo with integrity analysis).
- `DUP_01_DOUBLE_CHARGE`: Two identical transactions within 3 seconds, single order ID. (Expectation: Instant idempotent reconciliation $\to$ `DECISION_READY`).

The benchmark runner script is implemented in `benchmarks/run_benchmark.py` and produces an auditable summary table.
