# Phase 2 merchant investigation — validation and demo handoff

Date: 2026-10-25  
PR: #6, stacked on #4  
Scope: Next.js frontend, browser tests and the existing FastAPI synthetic scenario workflow

## Merchant journey now implemented

1. **Choose a case:** use case-list buttons (keyboard accessible) or the search/filter controls. Initial selection comes from accessible API cases, not a fixture ID.
2. **Understand the claim:** the main view presents the buyer statement and merchant account, actual order/payment entries, observed delivery evidence and where it came from.
3. **Understand what remains open:** evidence contradictions and evaluator missing requirements appear separately; the review package retains both.
4. **Take the next action:** item-not-received requests tracking or, if tracking is available but delivery remains unknown, offers a carrier lookup. SNAD offers condition-document upload. Unsupported/other actions are **explicitly manual**, never a fake executable button.
5. **See the investigation change:** POST action → feedback → reload detail/list → updated evidence and state. Feedback remains available; errors and stale responses do not mask the case.
6. **Review/export:** the review package lists source-labeled evidence and verification status, requirements marked satisfied by the evaluator, unresolved evidence gaps, contradictions, and the current rationale; the Markdown export uses the *same* provenance rules.

## Validation matrix

| Check | Automation / evidence |
| --- | --- |
| Source/unit regression tests | `npm test`, native Node test runner; source provenance, readiness distinction, empty records, contradictions, four category paths, stale response guard, error parsing, success copy |
| Next.js production build | `npm run build` via GitHub Actions frontend job |
| Backend pytest + empirical benchmark | Existing backend CI jobs |
| Actual browser with controlled API responses | Playwright Chromium running Next.js: tracking submission and changed case, mismatch/review modal provenance, SNAD upload and duplicate manual fallback, detail API retry, stale response race, mobile (375px) overflow and keyboard navigation |
| Real FastAPI synthetic integration | Separate browser smoke: Next.js `/api/v1` rewrite to FastAPI on localhost:8000, select a seeded INR fixture, submit tracking through real API, inspect updated evidence |
| Browser infrastructure | Pinned Ubuntu 24.04 for supported Playwright Chromium installation. The initial Ubuntu 26.04 failure was a runner compatibility problem, not a test failure. |

Browser tests use *simulated* carrier fixture data for the live-backend smoke and contract-shaped route intercepts for the controlled UI tests. Neither proves that external carrier verification works, nor that an uploaded document is authentic.

CI evidence:
- [Full five-test Chromium run, including mobile/keyboard: CI #25](https://github.com/Joel-Vazquez-Lopez/proofgraph/actions/runs/40185600361)
- [Chromium + FastAPI service bootstrapping (before adding the real API smoke assertion)](https://github.com/Joel-Vazquez-Lopez/proofgraph/actions/runs/40185772878)

## Coordinator review focus

- Confirm no "verified" badge is shown merely because a requirement is marked satisfied or a source is synthetic.
- Confirm PR #1's verification-wording change is reconciled with this branch's centralized `submissionMessage` helper.
- Review manual-next-step copy for categories where current backend policy has no executable frontend API route.
- Note `npm run lint` remains an existing broken `next lint` script under Next.js 15 and was **not run**. Build, tests and real Chromium automation run in CI; a separate lint tooling PR can enable lint cleanly.
- After merging PR #4, rebase/retarget PR #6 onto main; keep Phase 2 as draft pending coordinator review.

## Deferred: competing hypotheses

[Contract issue #9](https://github.com/Joel-Vazquez-Lopez/proofgraph/issues/9) asks Agent 1 for a typed, optional evidence-linked hypotheses payload and executable/manual action semantics. The frontend does **not** render synthetic or invented hypotheses today. The [proposal](frontend-hypotheses-contract-proposal.md) is informational, not a claim about implemented backend fields.
