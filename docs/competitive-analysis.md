# Competitive and Technical Analysis

**Project:** PayPal AI Dispute Investigator  
**Date:** October 2026  
**Audience:** Technical Reviewers, Hackathon Evaluators, System Architects  

---

## 1. Industry Landscape & Existing Capabilities

Payment disputes and chargebacks represent a tens-of-billions dollar operational friction in global commerce. Existing market solutions fall into three main categories:

### A. PayPal Resolution Center (Native Workflow)
- **Mechanism:** Asynchronous portal where buyer and seller exchange unstructured messages and upload raw attachments (receipts, carrier tracking).
- **Pain Points:**
  - **Back-and-forth latency:** Typical cases take 10 to 30 days because requests for clarification are vague (e.g., "Please submit proof of delivery").
  - **Unstructured dump:** Users submit screenshots of text messages, camera photos of receipts, or tracking links that require human adjudicators to manually cross-reference.
  - **No contradiction resolution:** If a tracking record shows delivery to Seattle and the buyer claims address was Portland, the system does not actively isolate the discrepancy.

### B. Automated Representment Platforms (Chargeflow, Chargeblast, Disputifier)
- **Mechanism:** Ingest disputes from payment processors (Stripe, PayPal, Braintree, Shopify Payments), pull order history and carrier status from merchant ERP/e-commerce platforms, and automatically generate templated PDF representment letters.
- **Strengths:** 
  - Rapid response submission before dispute expiration deadlines.
  - Integration with e-commerce stacks (Shopify, WooCommerce).
  - High win-rate optimization through historical pattern matching on reason codes.
- **Core Limitations:**
  - **Unidirectional Merchant Advocate:** Designed solely to protect merchant revenue. They generate persuasive, boilerplate legalistic letters rather than objective truth-seeking investigations.
  - **Static Evidence Assembly:** If tracking information is missing or contradictory, they either submit what they have or alert a human queue; they do not conduct an active, graph-driven evidence acquisition dialogue.
  - **Template Dump:** Often overwhelm adjudicators with 20-page PDFs containing terms of service, IP logs, and order confirmations, obscuring the single critical issue in dispute.

---

## 2. Our Proposed Differentiation: Active Graph-Grounded Investigation

Rather than a boilerplate document generator or an autonomous black-box judge, our platform acts as an **objective, active evidence investigator**:

| Dimension | Existing Automation (e.g. Chargeflow) | PayPal AI Dispute Investigator |
| :--- | :--- | :--- |
| **Primary Goal** | Win dispute for merchant via legalistic representment PDF | Assemble decision-ready, provenance-verified case for human review |
| **Data Representation** | Flat documents & key-value order metadata | Typed **Evidence Graph** (Claims, Transactions, Shipments, Observations, Contradictions) |
| **Evidence Acquisition** | Static batch ingestion at dispute creation | **Next-Best-Evidence (NBE)** active loop: evaluates information gain, cost, and relevance to ask the single best question |
| **Contradiction Handling** | Glossed over in favor of merchant claims | Explicitly identified and tracked with bidirectional `CONTRADICTS` graph edges |
| **Decision Authority** | Claims automated submission; black-box win-rate optimization | Strict separation: AI never issues verdicts or auto-refunds; produces auditable handoff packages |
| **Image & Document Integrity** | Pass-through storage of merchant/buyer images | Multi-layer analysis (EXIF verification, hashing, duplicate checking, tamper screening with explicit uncertainty) |
| **Explainability** | Generic reasoning paragraphs | Graph provenance trace: every statement links directly to verified source nodes |

---

## 3. Potential Overlap & Genuine Novelty

### What is NOT Novel (and we do NOT claim as such)
- Extracting order IDs from PayPal transactions is standard engineering.
- Using LLMs to summarize customer messages or draft emails is common.
- Representing dispute data as JSON or database records is baseline software.

### What IS Novel in Our Approach
1. **Dynamic Evidence-Graph State Machine**: Modeling disputes not as tickets, but as a directed hypothesis-and-evidence network where claims require specific verification paths.
2. **Next-Best-Evidence (NBE) Selection Policy**: A mathematically and heuristically grounded policy that ranks candidate investigation actions by:
   $$\text{Utility}(a) = \frac{\Delta \text{Uncertainty}(a) \times \text{Relevance}(a)}{\text{AcquisitionCost}(a) + \text{FrictionCost}(a)}$$
   This prevents user fatigue by asking 1 targeted question instead of 6 generic ones.
3. **Deterministic Decision-Readiness Standard**: A clear, rule-governed handoff criterion per dispute type (e.g., INR requires verified carrier delivery coordinates matching the checkout destination).
4. **Epistemic Humility & Probabilistic Image Assessment**: Refusal to treat AI image detection as binary proof of fraud, returning calibrated confidence ratings (`INCONCLUSIVE`, `PLAUSIBLE_TAMPERING_SUSPECTED`, etc.) accompanied by concrete verification actions.

---

## 4. Technical Risks & Uncertainties

1. **Carrier API Availability & Mocking**:
   - *Risk:* Real-time carrier APIs (USPS, FedEx, UPS) require separate merchant developer accounts and have strict rate limits.
   - *Mitigation:* Implement standard carrier webhook format with realistic fixture verification, falling back gracefully to carrier tracking lookup or uploaded manifest analysis.
2. **LLM Hallucination in Evidence Synthesis**:
   - *Risk:* Model may state that a parcel was delivered when tracking was ambiguous.
   - *Mitigation:* LLMs are strictly forbidden from writing unlinked claims to the graph. Observations must be parsed via deterministic validators and linked directly to raw evidence items.
3. **User Friction in Interactive Acquisition**:
   - *Risk:* Users dislike multiple follow-up inquiries.
   - *Mitigation:* The NBE policy penalizes follow-ups; the target is $\le 2$ targeted questions to reach `DECISION_READY`.
4. **Adversarial Document Manipulation**:
   - *Risk:* Fraudsters generate synthetic carrier screenshots with manipulated tracking numbers.
   - *Mitigation:* Multi-source cross-verification: matching tracking IDs against carrier data directly rather than relying solely on uploaded screenshots.
