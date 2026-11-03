# Issue #19 — PayPal Sandbox verification evidence and reproducible smoke test

**Date recorded:** 2026-10-25 (UTC date)  
**Target environment:** PayPal Sandbox, `https://api-m.sandbox.paypal.com`  
**Credentials/tokens committed:** None  
**Scope:** OAuth client-credentials authentication, read-only list disputes, optional read-only show dispute details. **No evidence submission or other mutating dispute operations.**

## Evidence and what has actually been verified

| Evidence source | Check | Status | Limit |
| --- | --- | --- | --- |
| Developer's local live API test, reported 2026-10-25 | OAuth authentication with locally configured Sandbox credentials | **SUCCESS REPORTED by operator** | Operator confirmed success; raw HTTP transcript/status code was not provided to the backend agent |
| Developer's local live API test, reported 2026-10-25 | PayPal Disputes API request | **SUCCESS REPORTED by operator** | Exact HTTP status, response size, and token claims were not supplied to backend agent |
| Backend adapter code + offline HTTP contract tests in this PR | Same `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET`, OAuth Basic authentication and `GET /v1/customer/disputes` via `httpx` | **AUTOMATED CONTRACT TEST** | HTTP responses in unit tests are simulated; **not** independent live Sandbox execution |
| `python -m app.services.paypal_sandbox_smoke` | Actual ProofGraph backend adapter against PayPal Sandbox | **PENDING live invocation by credential holder** | This development agent cannot access the operator's local unshared secrets; no live backend run is claimed |

This record preserves the operator's reported successful real test **without inventing independent confirmation**. Once the smoke command is executed with the configured credentials, its redacted JSON output (date, environment, HTTP statuses, number of disputes and final result only) can be attached to this issue or PR. **Never paste credentials, Authorization headers, access tokens, response bodies, buyer names, or dispute IDs into GitHub.**

## Credential equivalence: direct test vs ProofGraph backend

The deployed backend's `app.config.settings` reads precisely:

- `PAYPAL_CLIENT_ID`
- `PAYPAL_CLIENT_SECRET`
- `PAYPAL_ENVIRONMENT` (must be `sandbox`)
- `PAYPAL_BASE_URL` (must be `https://api-m.sandbox.paypal.com` for this smoke check)

`PayPalSandboxAdapter` obtains these values from the **same `settings` object used by the FastAPI backend**. The smoke test creates that adapter, invokes its actual `_get_access_token()`, `list_disputes()`, and optionally `get_dispute()` methods. It does not create a separate cURL-only client that could accidentally test different credentials or headers.

The backend now loads an **untracked** `.env` from the repository root (preferred) or `apps/api/.env` on startup. Already-exported process environment variables take precedence. Merely putting credentials in a local shell variable without exporting them does not make them visible to Python.

This confirms which credential names and code path are used, **not that the operator's local secret values are available to this agent**.

## Run the real live smoke check locally

Install the existing backend requirements, place the Sandbox values in a local ignored `.env` or export them into the shell, and run:

```bash
cd apps/api
python -m pip install -r requirements.txt
python -m app.services.paypal_sandbox_smoke
```

Optional: check an existing Sandbox dispute, without printing its details:

```bash
python -m app.services.paypal_sandbox_smoke --dispute-id PP-D-YOUR-SANDBOX-DISPUTE-ID
```

The smoke command reports a **UTC timestamp** and explicit HTTP status for each attempted step:

- **OAuth:** `POST /v1/oauth2/token` with HTTP Basic client authentication and `grant_type=client_credentials`. Token bytes are never output.
- **List:** `GET /v1/customer/disputes` using the adapter's Bearer token.
- **Optional details:** `GET /v1/customer/disputes/{id}`. The ID and response content are not printed.
- **Never invoked:** `provide-evidence`, offers, refunds, escalation, or adjudication.

A response with **HTTP 200 and `{"items": []}` is a successful empty Sandbox list** (`item_count: 0`). An HTTP **401/403** is a credential/permission problem, **429** is a rate limit, **503** denotes network failure, **404** for optional dispute details means not found, and **502** denotes a malformed supposedly successful response. No step may be marked PASS just because a local adapter returns `[]` with missing credentials.

If no credentials are configured, the command prints `result: BLOCKED` and exits nonzero. Other non-PASS outcomes also exit nonzero. It refuses any production or custom base URL, ensuring the smoke test **cannot silently contact live production PayPal**. Upstream response body/error text and exception details are never printed.

The JSON output contains only safe metadata (`result`, categorical `reason`, `checked_at_utc`, `environment`, step status codes and `item_count`); the `credential_source` label denotes the backend settings object, **not secret values**.

## Automated GitHub Actions run (optional, opt-in)

`.github/workflows/paypal-sandbox-smoke.yml` adds a manual `workflow_dispatch` that invokes **the same backend adapter smoke command**. Before using it, the repository administrator must explicitly configure Actions secrets named `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` with Sandbox app credentials. The workflow must exist on the repository's default branch before it can be dispatched from Actions; adding the file to this unmerged PR does **not** automatically run a live test. Normal pull-request CI is always offline and never receives these secrets.

Workflow permissions are read-only; the job executes no PayPal dispute mutations. The optional input is a Sandbox dispute ID for GET details. Do not store API tokens or any real-world customer data as workflow artifacts.

## Interpreting errors and missing disputes

- In <https://developer.paypal.com/dashboard/applications/sandbox>, choose the **Sandbox**, not Live, app. The app's Client ID/Secret are **not** sandbox account email/password credentials.
- If OAuth succeeds but the disputes endpoint returns **403**, the app or business account may lack Disputes API permission/scope or the API call may require merchant authorization. A token alone does **not** establish Disputes API access.
- If the list returns **200 with zero items**, authentication/access was accepted but that Sandbox account has no visible disputes. Test disputes must be created through a separate appropriately authorized Sandbox flow.
- Optional dispute details may return **404** if the record does not exist for that authorized account.
- To verify additional permissions, see PayPal's official [API authentication](https://developer.paypal.com/api/rest/authentication) and [Disputes setup](https://developer.paypal.com/platforms/disputes/set-up/) guidance.

## Product integration limitation

**This smoke test verifies the actual `PayPalSandboxAdapter` network integration.** At this stage the FastAPI disputes listing/detail routes still load persisted synthetic demonstration cases through `DisputeService`; they do not automatically pull external PayPal disputes into the evidence graph. Nor does a working PayPal API token make local synthetic carrier observations independently verified. Importing and reconciling real PayPal cases, tenancy, and production-grade authentication are separate tasks.

No raw credentials, access tokens, PayPal dispute response bodies, or real customer identifiers appear in this document.
