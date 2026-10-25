# ProofGraph merchant-journey audit — Agent 3

Date: 2026-10-25  
Scope: Next.js frontend at `apps/web`, current shared-schema contract, and synthetic demonstration fixtures. This is a source review, not a browser usability study.

## Core journey

1. **Choose a dispute:** `page.tsx` requests `GET /api/v1/disputes`; `CaseList` shows summary cards, filters and search. The page starts on one fixture-specific ID.
2. **Understand the dispute:** `CaseOverview` renders a claim summary and optionally the buyer/merchant statements; it also shows evidence and outstanding questions.
3. **Take an action:** a branch of `CaseOverview` offers tracking, carrier lookup, file upload, or a review summary. These post to existing evidence endpoints; the main page reloads case data.
4. **Inspect details:** `AdvancedWorkspace` provides the graph, evidence provenance, audit timeline and heuristic policy diagnostics.
5. **Review/export:** `ReviewPackageModal` builds a Markdown summary in the browser.

## Findings, ranked

| Priority | Area | Current user impact | Fix / dependency |
| --- | --- | --- | --- |
| **P0** | Primary next action in `CaseOverview` | Every non-ready, non-review case without a shipment gets “Add tracking information,” including non-delivery categories such as duplicate transactions. A `SIGNIFICANTLY_NOT_AS_DESCRIBED` case without a shipment cannot reach its intended file-upload action. | **Addressed in this PR:** shipping actions are now gated on `ITEM_NOT_RECEIVED`; SNAD can reach the upload step; other categories use the backend policy description and review summary. |
| **P0** | Carrier evidence logic | Code compared `shipment.verification_status` to `VERIFIED_EXTERNAL`, a value that belongs to the **origin** enum. It therefore failed to recognize a delivery observation; synthetic fixture “verified” statuses were also easy to mistake for independent checks. | **Addressed in this PR:** examine a matching `OBSERVATION` with `verification_status === VERIFIED` and `status === DELIVERED`; explain `origin` separately and explicitly distinguish synthetic records. No new API fields. |
| **P0** | Review mismatch panel | Review-required UI hard-coded “Seattle” as the order address and “Portland” as delivery. The checked fixture is actually **order: Portland; delivery: Seattle**. Hard-coded geography also fails for any other dispute. | **Addressed in this PR:** render `order.content.destination_address` and `observation.content.delivered_to_address`; if absent, render the actual contradiction/rationale without a location comparison. |
| **P0** | Evidence upload/tracking success | `page.tsx` claimed documents were independently verified after upload, and tracking was carrier-verified after submission. | **Owned by coordinator PR #1** ([verification-message correction](https://github.com/Joel-Vazquez-Lopez/proofgraph/pull/1)); intentionally not duplicated. |
| **P1** | Success feedback visibility | `page.tsx` calls `setFeedback` after an action, then `fetchDisputeDetail` immediately sets feedback to `null`. The banner with the result can vanish during the mandatory refresh. | Separate follow-up: clear on case switch or new action, not on successful re-fetch; verify PR #1's corrected messages are actually visible. |
| **P1** | Case-list guidance | `CaseList` uses dispute-ID-specific `oneLineNeed` sentences, regardless of new evidence or current policy output. Names also have fixture-specific fallbacks (e.g. SNAD watch while the current fixture order is a lens). | Prefer server-provided `item_name` and a status-driven fallback; use chosen action only after fetching detail, or coordinate a summary field with backend. |
| **P1** | Review package semantics | `ReviewPackageModal` calls evaluator `satisfied_requirements` “Established & Verified Facts,” and the exported report appends “Verified” to each. A satisfied evaluator requirement is not independently verified provenance. The modal also inserts fallback transaction/merchant facts not necessarily backed by a node. | Follow-up: separate *requirements satisfied* from *externally verified claims*, surface source and status where available, avoid ungrounded defaults. Coordinate with Agent 2 on provenance guarantees. |
| **P1** | Loading and failure modes | Non-OK list/detail responses and network failures are console-only; the list can look empty and a failed detail can leave the previously selected case visible. There is no retry button or accessible explanation. | Follow-up: explicit request-error states and retry; guard stale responses when switching cases rapidly. |
| **P2** | Detail prose | Several descriptions assume the customer claims non-delivery or that all payment records originate from PayPal; original order address was read from `shipping_address` rather than existing `destination_address`. | **Partly addressed in this PR:** fix order field and avoid asserting PayPal-verified payment. Remaining category narratives should be derived from typed claim/policy fields. |
| **P2** | Keyboard/accessibility | `CaseList` case cards are clickable `div` elements without keyboard activation; review modal lacks labelled-dialog semantics, focus trap/return focus, and Escape handling. Confirmation/loading feedback is not announced as a live region. | Make case cards buttons, add dialog semantics/focus management, live status/error announcements, and test tab flow. |
| **P2** | Narrow screens | Main grid stacks on small screens, but the left column retains `sticky top-[72px]`; dense headers and card details are likely to need viewport testing. | Manual mobile-width QA after running the app; do not assert responsiveness without testing. |
| **P2** | Demo credibility | Prefilled sample tracking and fixture-ID-specific product descriptions can look like baked-in reasoning. Source data is deterministic and synthetic. | Show a real case transition using the API, label simulation, and demonstrate the counterexample where order and delivery address differ. |
| **P2** | Test tooling | `apps/web/package.json` has no frontend test script; `lint` invokes `next lint`, which is not supported by Next.js 15. The current GitHub Actions job runs `npm ci` and `npm run build`, despite being named “Frontend Lint & Build.” | Coordinator follow-up: configure ESLint CLI with an explicit config or replace the broken lint target; add component tests for the state/label matrix. |

## First focused improvement in this branch

Changes in `CaseOverview.tsx` only:

- Route non-shipping disputes to their relevant next action rather than always using missing tracking as the first fallback.
- Read delivery status from the matching carrier observation, not the shipment's origin/status mismatch.
- Make synthetic demonstration provenance explicit; do not promote simulated or submitted evidence to independent verification.
- Remove hard-coded destination mismatch locations; use the API's existing address and contradiction fields.
- Fix `DUPLICATE_TRANSACTION` category label and the existing order destination field.
- Render backend missing-requirement strings when there is no more-specific shipping gap.
- Stop asserting that every payment entry is confirmed from PayPal's live ledger.

No endpoint, request body, response schema, carrier integration, or algorithm was changed.

## Verification matrix for manual demo QA

| Fixture case | What should be visible after this PR | Primary action |
| --- | --- | --- |
| `PP-D-INR-8841` (no shipment) | No tracking recorded; delivery not confirmed | Save merchant tracking. Successful submit must **not** imply external carrier verification. |
| `PP-D-INR-9923` (address discrepancy) | Order **Portland, OR 97201**; simulated delivery **Seattle, WA 98101** | Review discrepancy and inspect sources; no hard-coded reversed cities. |
| `PP-D-SNAD-3012` (condition dispute) | A condition/document gap, with delivery record labelled as demo data if shown | Upload condition evidence, not ask for shipping tracking. |
| `PP-D-DUP-4044` (duplicate transaction) | No delivery-specific requirement implied by the absence of shipment | Show current backend policy description and review case summary. |

Further scenarios: case with tracking but no usable carrier observation; case with external verified delivery observation; review-required case with no addresses; failed API requests; empty list; narrow viewport; keyboard navigation; case switch during request.

## Demo sequence (honest and reproducible)

Start on INR-8841, show missing tracking and the user-facing next action; submit example tracking using the existing endpoint; explain that the demonstration carrier data is simulated; inspect the updated graph and provenance in Advanced. Switch to INR-9923 to demonstrate a contradiction grounded in real graph fields and escalate for human review. Finally, show SNAD-3012 to prove the interface changes its recommended action based on dispute type.

Do **not** narrate synthetic carrier data as a live carrier lookup, treat hash/file validation as document authenticity, call heuristic scores probabilities, or claim the app decides disputes.

## Coordination

- **Coordinator PR #1:** verification success wording; review as a separate dependency.
- **Agent 2:** confirm which carrier observation/source combinations may legitimately be called independently verified; the frontend currently uses existing `origin`, `verification_status` and `status` conservatively.
- **Agent 1:** expose future competing hypotheses through a documented API contract before building a hypotheses UI. Do not display invented hypothesis scores.
- **Follow-up ownership:** case-list live descriptions, review-package evidence semantics, request-error feedback and accessibility can be split into small PRs.
