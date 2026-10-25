# Demo Video Script & Recording Storyboard

**Project:** PayPal AI Dispute Investigator  
**Target Duration:** 2 minutes 45 seconds (Strict Hackathon Limit: Under 3:00)  
**Platform:** YouTube (Publicly accessible)  
**Guidelines:** No background copyrighted music, high-resolution screen capture of the live web application (http://localhost:3000), clear spoken voiceover.

---

## Video Timeline & Script Breakdown

```
[0:00 - 0:25] Introduction & The Problem
[0:25 - 0:50] Architecture & Evidence Graph Overview
[0:50 - 1:25] Scenario 1: Adaptive Investigation & One-Click Carrier Verification (Case PP-D-INR-8841)
[1:25 - 2:00] Scenario 2: Factual Contradiction Detection (Case PP-D-INR-9923)
[2:00 - 2:25] Decision-Ready Adjudication Package & Audit Dossier
[2:25 - 2:45] Empirical Benchmark Results & Non-Autonomous Safety Principles
```

---

### Scene 1: The Problem & Vision (0:00 – 0:25)
* **Visual on Screen:**
  - Start on the **PayPal AI Dispute Investigator** homepage (http://localhost:3000).
  - Show the clean header, the "Sandbox Mode Active" indicator, and the list of disputed cases.
* **Voiceover:**
  > *"Every day, PayPal moves billions of dollars for millions of businesses and consumers worldwide. But when a dispute occurs, resolution frequently devolves into slow, adversarial document dumps—costing merchants time, frustrating buyers, and burdening adjudicators with weeks of manual review.*
  >
  > *This is the **PayPal AI Dispute Investigator**: an active, graph-grounded investigation platform built for the PayPal AI Hackathon. Our core principle: **The AI asks fewer, better questions, grounds conclusions in verifiable evidence, and explicitly acknowledges uncertainty.**"*

---

### Scene 2: The Core Workflow & Evidence Graph (0:25 – 0:50)
* **Visual on Screen:**
  - Click on dispute `PP-D-INR-8841` (Sarah Connor • Sony Headphones).
  - Point to the **Buyer Claim vs Merchant Response** comparison box.
  - Switch to the **Evidence Graph** tab.
  - Pan across the hierarchical graph showing the `DISPUTE`, `TRANSACTION`, `ORDER`, and `CLAIM` nodes connected by typed edges.
* **Voiceover:**
  > *"Instead of treating dispute management as a rigid checklist, our system ingests transaction records from the PayPal REST API and constructs a typed evidence graph using NetworkX.*
  >
  > *Every claim, payment, shipment, and observation is modeled with strict evidence provenance. A merchant's tracking number alone is treated as user-submitted and unverified—it can never establish delivery without independent carrier telemetry."*

---

### Scene 3: Active Next-Best-Evidence & One-Click Carrier Verification (0:50 – 1:25)
* **Visual on Screen:**
  - Switch back to the **Evidence Overview** tab.
  - Hover over the **AI Recommended Next Action** hero banner showing *"Query USPS Tracking Telemetry"*.
  - Show that tracking number `940010009999` is recorded, but carrier telemetry is pending.
  - Click the **`[⚡ Execute Carrier Verification]`** button.
  - Show the instant loading state, success banner, and watch the status dynamically update.
  - Show the new **Carrier Telemetry** card indicating *"Delivered to Springfield, OR 97477"*.
* **Voiceover:**
  > *"Here, our Next-Best-Evidence policy evaluates candidate actions by balancing expected information gain against human acquisition friction. Rather than bothering the buyer or merchant, it prioritizes a zero-friction automated carrier API query.*
  >
  > *With one click, the system queries the carrier gateway, ingests verified telemetry into the graph, confirms the destination postal code matches the purchase order, and advances the case towards decision-readiness."*

---

### Scene 4: Factual Contradiction Isolation (1:25 – 2:00)
* **Visual on Screen:**
  - Click on dispute `PP-D-INR-9923` in the left sidebar.
  - Show the prominent red alert badge: **`HUMAN REVIEW REQUIRED`**.
  - Show the **Active Contradiction Warning Box**: *"Carrier delivered to Seattle WA 98101, but buyer purchase order specified Portland OR 97201."*
  - Switch to the **Evidence Graph** tab and zoom into the animated red **`CONTRADICTS`** edge running from the Carrier Observation to the Order node.
  - Click on the contradiction node to open the **Node Detail Drawer** displaying verified telemetry.
* **Voiceover:**
  > *"Now consider a real-world edge case: dispute PP-D-INR-9923. The carrier reports successful delivery, but the buyer reports non-receipt.*
  >
  > *A naive automated system might dismiss the buyer. But our engine cross-references the carrier delivery coordinates against the merchant's purchase order. It detects that the package was delivered to Seattle, Washington—while the buyer's order was for Portland, Oregon.*
  >
  > *The graph isolates the contradiction with an animated discrepancy edge, immediately blocks automatic closure, and routes the case for targeted clarification and human review."*

---

### Scene 5: Decision-Ready Dossier & Audit Log (2:00 – 2:25)
* **Visual on Screen:**
  - Click the **`Decision-Ready Report`** tab.
  - Scroll through the Executive Summary, the verified factual checklist, and the provenance links.
  - Hover over the **`[Export Markdown]`** button.
  - Click the **`Audit Log`** tab to show the immutable timeline of state transitions.
* **Voiceover:**
  > *"Once all necessary evidence is assembled, the system generates a structured adjudication package.*
  >
  > *Every finding links back to verifiable graph nodes. Authorized human adjudicators receive a clear, tamper-proof dossier with complete audit history, enabling confident, transparent case determinations in minutes instead of weeks."*

---

### Scene 6: Empirical Results & Safety Principles (2:25 – 2:45)
* **Visual on Screen:**
  - Show terminal or summary graphic displaying the benchmark results:
    - **88% reduction in human questions** (0.6 vs 5.0)
    - **100% elimination of irrelevant inquiries**
    - **100% decision-readiness accuracy**
    - **33/33 automated tests passing**
  - Return to the live dashboard.
* **Voiceover:**
  > *"In our empirical benchmark across canonical dispute scenarios, our policy achieved an **88% reduction in unnecessary human questions** and eliminated irrelevant paperwork entirely.*
  >
  > *Crucially: **the AI never determines who wins and never moves funds autonomously.** Consequential decisions remain strictly in human hands.*
  >
  > *The PayPal AI Dispute Investigator demonstrates how PayPal and AI can work together to turn friction into clarity. Thank you."*

---

## Quick Recording Checklist Before You Record:
1. **Resolution:** 1080p (1920x1080) or 1440p screen recording.
2. **Browser:** Chrome or Safari running full screen on http://localhost:3000.
3. **Servers Running:** Run `./run.sh` from the repository root to have both backend and frontend active.
4. **Mic:** Clean audio with minimal echo; do not add background music.
5. **Length Check:** Ensure final edited video is under 2 minutes and 50 seconds.
