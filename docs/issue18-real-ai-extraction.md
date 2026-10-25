# Issue #18 — Actual model-backed dispute claim extraction

## Provider and exact model

- **Provider:** OpenAI, external API at the fixed backend URL `https://api.openai.com/v1/chat/completions`.
- **Model:** `gpt-4o-mini` (configurable with `OPENAI_MODEL`, default `gpt-4o-mini`).
- **AI feature:** a reviewer invokes `POST /api/v1/disputes/{dispute_id}/ai/extract`. The backend makes a genuine HTTP POST with an OpenAI **strict JSON Schema** response format. A model extracts short *verbatim* buyer/merchant statements, classifies their claimed topic, and suggests a typed evidence question.
- **Reliable investigation layer:** EvidenceGraph/NetworkX, `HeuristicNBEPolicy`, optional `HypothesisDiscriminationPolicy`, readiness/state machine remain independent and **never read the AI nodes as verified transaction, shipment or carrier observations**. The model cannot award a dispute, move money, or mark evidence verified.

This is a meaningful but intentionally narrow generative-model capability, **not** a deterministic template pretending to be AI. Source-text matching and policy decisions remain deterministic guardrails.

## Configuration

From repository root (using the normal backend installation):

```bash
pip install -r apps/api/requirements.txt
export AI_PROVIDER=openai
export OPENAI_MODEL=gpt-4o-mini
export OPENAI_API_KEY="YOUR_REAL_KEY"  # Set locally, not in Git or screenshots
uvicorn app.main:app --app-dir apps/api --port 8000
```

A key is never returned in API responses, log messages, graph nodes, or frontend. The server sends the key only in its Authorization header to the fixed HTTPS OpenAI host. Do not put the API key in `NEXT_PUBLIC_*` environment variables. `AI_TIMEOUT_SECONDS=8.0` is currently a fixed safe budget within server configuration.

**Without a valid key**, the API returns `status=FALLBACK_NOT_CONFIGURED`, `model_called=false`, `provenance=NO_MODEL_OUTPUT`, a clear message, and the already-chosen deterministic investigation action. With `AI_PROVIDER=disabled` it returns `FALLBACK_DISABLED` without calling a model.

The UI exposes an opt-in **Analyze dispute text with AI** control. It never silently transmits dispute text during normal case navigation. Explicit reviewer or system-admin permission is required; a merchant/buyer cannot invoke the external transfer endpoint even on their own case. Development auth is header-based demo-only; real deployment needs actual identity and approved personal-data terms.

## Verification commands

### No credentials needed: deterministic CI and provider-contract tests

```bash
pytest -v apps/api/tests/test_ai_claim_extractor.py
pytest -v
npm --prefix apps/web test
npm --prefix apps/web run build
```

CI intercepts the OpenAI HTTP boundary **only in tests** to exercise real FastAPI request handling, source selection, strict schema payload construction, output validation, persistence and safe failure. It does **not** establish that an OpenAI server actually responded. Provider stubs are not misrepresented as live AI calls.

### Real model smoke test — must opt in with actual credentials

```bash
export OPENAI_API_KEY="YOUR_REAL_KEY"
export RUN_LIVE_AI_TEST=1
pytest -v apps/api/tests/test_ai_claim_extractor.py::test_optional_live_openai_claim_extraction
```

The live test makes a **real outbound OpenAI API call**, fails if the response is not quote-grounded, and never exposes the key. **This smoke test is skipped in default CI**; no live-model verification is claimed without it.

You can also call the endpoint as a reviewer through the web UI or with:

```bash
curl -X POST http://localhost:8000/api/v1/disputes/PP-D-INR-8841/ai/extract \
  -H 'X-User-Role: REVIEWER' \
  -H 'X-User-Id: reviewer_demo_user'
```

Example response **shape only** (not a claim of a live model call):

```json
{
  "status": "MODEL_SUCCESS",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "model_called": true,
  "claims": [{
    "source_id": "claim_buyer_PP-D-INR-8841",
    "quote": "<exact substring of a real source>",
    "claim_type": "NON_RECEIPT",
    "evidence_need": "HANDOFF_PROOF",
    "evidence_question": "Can delivery handoff or recipient acknowledgement be corroborated?",
    "inference_node_id": "ai_claim_<hash>"
  }],
  "rejected_items": 0,
  "message": "OpenAI model returned quote-grounded candidate assertions. All are unverified...",
  "fallback_action_id": "act_merchant_tracking",
  "provenance": "MODEL_INFERENCE / UNVERIFIED — textual analysis, not evidence verification"
}
```

## Safety and boundaries

1. Only up to four existing graph claim statements plus buyer/seller case statements are sent; each source is limited to 2,000 characters. The request excludes transaction IDs, files, images, full evidence graph, and independent account details. **Dispute text may itself contain sensitive information**; explicit reviewer action and proper disclosure/consent requirements remain important.
2. Provider prompt treats all input as untrusted and says to ignore embedded instructions. An attacker can still influence AI extraction, so server-side validation **requires** a verbatim contiguous quote present in an allowed source ID, with one known claim category and one controlled evidence-need type. Unknown citations, invalid types, and nonverbatim content are rejected.
3. A valid output creates an immutable-style derived `HYPOTHESIS` graph node with `origin=MODEL_INFERENCE`, `verification_status=UNVERIFIED`, `independently_verified=false`, source node reference, model, verbatim quote, and `DERIVED_FROM` edge where a graph node exists. A second request with identical claims is idempotent by stable hash.
4. No AI output becomes a `VERIFIED_EXTERNAL` observation, and `readiness_json`, `state`, `policy_decision_json` remain unchanged. Questions are **suggestions** only; the authoritative deterministic next action is separately exposed as `fallback_action_id`.
5. Network timeout, 401/other HTTP errors, truncated outputs, refusals, invalid schema/JSON, or no grounded claims return explicit `FALLBACK_*` statuses. No synthetic or heuristic answer is presented as model text. The backend never returns an upstream error body, which may echo sensitive input.
6. The model is not run automatically on every case load: each click is a billable external request. No caching of the model response outside graph provenance nodes is used. Requests are explicitly privileged but the prototype's demo-header auth must be replaced for production.

## Current limitations

- **Live verification** requires a working OpenAI API key and network access. Default CI uses provider mocks; release eligibility depends on actually running the live smoke test and documenting the result.
- Exact quote grounding prevents invented quotations but not an inaccurate classification of the quote or incorrect evidence-need choice. No calibrated accuracy, uncertainty probabilities, or human-evaluated retrieval study is asserted.
- Reading and transmitting real buyer/merchant dispute text to an external AI provider requires explicit data handling review; this hackathon prototype is not a production privacy implementation.
- AI extraction is not an adjudication system, does not verify photos/payment records, and does not improve the deterministic policy merely by existing. It is a separate, explainable assistant artifact available in the evidence graph and the UI.
