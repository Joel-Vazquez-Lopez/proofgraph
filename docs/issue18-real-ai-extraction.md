# Issue #18 — Gemini-first and optional OpenAI claim extraction

## What runs, and what remains deterministic

The primary model is **Google Gemini `gemini-3.5-flash-lite`** (stable model available in the Google AI Studio API **free tier**, subject to per-project and per-model limits). Google describes structured JSON output support; free-tier requests may be used to improve its products. Check your own project's quota and data-processing terms before transmitting anything other than synthetic data.

Optional alternative: **OpenAI `gpt-4o-mini`**. The reviewer explicitly calls `POST /api/v1/disputes/{dispute_id}/ai/extract`, with reviewer or admin permission and case tenancy checks. Neither model adjudicates disputes, refunds anyone, marks evidence verified, or selects the official investigation action. The EvidenceGraph, NBE policy, decision readiness, audit chronology, and PayPal Sandbox adapter remain independent.

Model output is a structured list of `source_id`, `quote`, `claim_type`, and `evidence_need`. The backend validates **exact contiguous verbatim quotes from known, bounded source texts** and controlled enums. It adds `HYPOTHESIS` nodes marked `origin=MODEL_INFERENCE` and `verification_status=UNVERIFIED`, with source citations and model/provider provenance. The graph stays idempotent for identical model/source outputs. Valid model output cannot alter `state`, `readiness_json`, or `policy_decision_json`. Local heuristics remain authoritative and are returned as `fallback_action_id`.

Gemini uses a real server-side POST to Google's fixed HTTPS `/v1beta/models/{GEMINI_MODEL}:generateContent` endpoint with `x-goog-api-key`, structured JSON output, bounded output tokens, and no redirects/retries. A model allowlist prevents malformed model identifiers from changing the URL destination. OpenAI uses its Chat Completions endpoint with strict JSON Schema.

## Local setup (no keys in repository or browser)

From the **repository root**, install Python and Node dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r apps/api/requirements.txt
npm --prefix apps/web ci
```

Configure a Gemini key **locally**, for example using an ignored repository-root `.env` file:

```dotenv
AI_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=<set-your-own-key-locally>
```

Do **not** place any API key in `.env.example`, GitHub commits, chat messages, screenshots, `NEXT_PUBLIC_*` frontend variables, or client headers. A process environment variable overrides ignored `.env` values. The existing `app.config` reads local root or `apps/api/.env`. To turn off all external AI transfers, set `AI_PROVIDER=disabled`. To use OpenAI instead, use:

```dotenv
AI_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
OPENAI_API_KEY=<set-your-own-key-locally>
```

The default provider is `gemini`, but **no external request is made unless a reviewer clicks Analyze dispute text with AI**. Missing credentials return `FALLBACK_NOT_CONFIGURED`; the user sees `NO_MODEL_OUTPUT` and the deterministic action instead of invented AI output.

Launch server and frontend in separate terminal sessions:

```bash
# Terminal A, repository root (with Python environment active)
uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000

# Terminal B, repository root
npm --prefix apps/web run dev
```

Visit `http://localhost:3000`, open a synthetic dispute as a demo reviewer, and click the optional AI analysis control. The panel displays `Provider: gemini · Model: gemini-3.5-flash-lite · Status: MODEL_SUCCESS` **only when grounded model output exists**. Failed calls show the attempted provider/model with explicit fallback.

## Automated contract, security, and regression checks (no real provider required)

From repository root:

```bash
pytest -v
npm --prefix apps/web test
npm --prefix apps/web run build
cd apps/web
npx playwright test --config=playwright.config.cjs
```

The browser suite requires its usual local Next.js/FastAPI environment and Playwright Chromium install; GitHub Actions provisions these. The standard CI pipeline also runs `benchmarks/demo_intelligence.py`, `benchmarks/evaluate_adaptive_nbe.py`, and `benchmarks/run_benchmark.py`.

**Standard CI only mocks the external HTTP provider boundary**, never calls live Gemini or OpenAI, and verifies payloads, authorization, source quote validation, safety restrictions, provenance persistence, deterministic fallback, and merchant UI. These results must not be described as real model inference.

## Live Gemini smoke test (synthetic dispute only)

The following test uses a seeded `SYNTHETIC_FIXTURE` case, writes a fixed invented buyer sentence to the case graph, invokes the **real FastAPI endpoint**, and requires a real HTTPS Gemini response with exact quote grounding. It asserts the policy/readiness remain unchanged and that persisted graph nodes are labeled `MODEL_INFERENCE / UNVERIFIED`.

From repository root, with your API key already configured in **server-side** environment or ignored `.env`:

```bash
export AI_PROVIDER=gemini
export GEMINI_MODEL=gemini-3.5-flash-lite
export RUN_LIVE_GEMINI_TEST=1
pytest -v apps/api/tests/test_gemini_claim_extractor.py::test_optional_live_gemini_claim_extraction
```

**The test must report PASSED, not SKIPPED.** If the key is unavailable, the test is skipped by design. If the model is unavailable or rate-limited, the test **fails** rather than simulating success. Review the actual result and record the model identifier and test timestamp before marking PR #21 ready for review. Do not paste credentials or full model outputs into CI/PR comments.

The optional OpenAI equivalent remains available:

```bash
export AI_PROVIDER=openai
export OPENAI_MODEL=gpt-4o-mini
export RUN_LIVE_AI_TEST=1
pytest -v apps/api/tests/test_ai_claim_extractor.py::test_optional_live_openai_claim_extraction
```

The opt-in `.github/workflows/live-ai-smoke.yml` also supports manual provider selection with appropriate repository Actions secret `GEMINI_API_KEY` or `OPENAI_API_KEY`. GitHub's manual workflow button may not be available until the workflow is on the repository's default branch; **local command-line smoke is the intended verification before PR merge**.

## Failure handling, provenance and privacy

- Input is restricted to up to four existing source claim nodes and buyer/seller statements, with each source capped at 2,000 characters. Files, payment credentials, account identifiers, shipping receipts, and full case graphs are not sent as standalone objects. Raw statements could themselves include private data: synthetic only until provider terms/privacy requirements are reviewed.
- Source content is explicitly untrusted. Embedded prompt injection, fake source IDs, nonverbatim quotes, unsupported evidence types, and AI-claimed external verification cannot generate verified evidence. Model-generated prose cannot create a refund, change state, or override NBE.
- The Gemini API key remains server-only in `x-goog-api-key`; OpenAI stays server-only in `Authorization`. Both use a fixed HTTPS host, bounded timeout and output, redirects disabled, and **do not log or return upstream provider error bodies**.
- Provider-specific provenance (`provider` and `model`) is stored with derived graph nodes. Quotes may still be misclassified: **exact quote validation establishes textual traceability, not factual truth or model accuracy**.
- Missing keys, unrecognized provider/model, blocked or truncated responses, malformed output, rate limiting, network failures and no accepted quotes fall back to explicitly labeled `FALLBACK_*` results; the deterministic policy continues unmodified.
- Free API tier usage limits and privacy conditions can change. Check Google AI Studio's current project availability before live use.

## Current verification status

The normal CI test suite proves local contract behavior **with HTTP mocks**, not real model execution. Real Gemini inference remains **unverified until the operator locally runs the opt-in smoke test and obtains a PASS**.
