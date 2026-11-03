# ProofGraph final local acceptance rehearsal (without Docker)

Run against `integration/proofgraph-v1` plus the proposed UI PR; do not use real buyer data. Keep API and web development servers running in separate terminals.

## Startup
- API: `cd apps/api && source .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
- Web: `cd apps/web && npm ci && npm run dev`
- Confirm `http://localhost:8000/`, `http://localhost:3000` and the case list respond.

## Automated checks (record actual output)
- Backend from repository root: `apps/api/.venv/bin/python -m pytest -q`
- Frontend: `cd apps/web && npm test && npm run build`
- Chromium: `cd apps/web && npx playwright test` (install browser if needed)
- Benchmark: `apps/api/.venv/bin/python benchmarks/run_benchmark.py`; reconcile published figures with actual output before submission. **No benchmark run is claimed by this document.**

## Manual end-to-end walkthrough
1. Open synthetic INR case Keychron. Note chosen action and missing evidence before change. Add a *synthetic* tracking number. Confirm user-submitted provenance, no automatic carrier verification, new graph state, and changed or explicitly unchanged chosen action with rationale.
2. Refresh browser and restart API process. Verify saved evidence persists locally and is not duplicated.
3. Open synthetic Sony INR case. Confirm Portland order destination vs Seattle simulated delivery contradiction, explicit human review, and no false independent-carrier claim.
4. Open SNAD and duplicate-charge fixtures. Confirm distinct category-specific evidence requirements and recommended actions.
5. Run Gemini extraction with explicitly configured server-side credentials. Verify exact quotes, source IDs, unverified model provenance, grouped duplicate questions, graph node updates, and no change to deterministic decision from model text alone. Test missing-key fallback separately.
6. Click **View evidence graph**. Confirm graph tab opens, selected nodes show provenance and raw source attributes, contradictions remain visibly distinct, and model nodes never appear externally verified.
7. Open review package. Confirm it is **prepared for human review**, not submitted to PayPal. Check browser console and network errors.

## Release gate
- Attach command output, screenshots, and a short video demonstrating the transitions.
- Keep live PayPal Sandbox read-only unless explicitly authorized otherwise; a synthetic fixture is not PayPal API verification.
- Confirm issue #28 benchmark reconciliation, security review, and deployment limitations before declaring submission ready.
- Do not merge into `main` without explicit owner approval.
