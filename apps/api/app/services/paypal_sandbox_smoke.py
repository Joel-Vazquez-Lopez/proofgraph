"""Read-only live PayPal Sandbox health check using the production backend adapter.

Run from apps/api:
    python -m app.services.paypal_sandbox_smoke
    python -m app.services.paypal_sandbox_smoke --dispute-id PP-D-...

The smoke test NEVER submits evidence and NEVER emits credentials, access tokens,
dispute identifiers, response bodies, or arbitrary upstream error messages.
Without configured credentials it explicitly reports BLOCKED (not PASS).
"""
import argparse
from datetime import datetime, timezone
import json
import os
from typing import Any, Optional

from app.adapters.paypal_sandbox import PayPalAPIError, PayPalSandboxAdapter
from app.config import settings


OFFICIAL_SANDBOX_URL = "https://api-m.sandbox.paypal.com"


def _safe_failure_reason(status_code: int) -> str:
    """Categorical only: upstream error messages can contain sensitive data."""
    if status_code in (401, 403):
        return "AUTHENTICATION_OR_DISPUTES_PERMISSION_DENIED"
    if status_code == 404:
        return "DISPUTE_NOT_FOUND"
    if status_code == 429:
        return "RATE_LIMITED"
    if status_code == 503:
        return "NETWORK_UNAVAILABLE"
    return "UPSTREAM_HTTP_ERROR"


def run_smoke(
    adapter: Optional[PayPalSandboxAdapter] = None,
    *,
    dispute_id: Optional[str] = None,
) -> dict[str, Any]:
    """Exercise REAL adapter OAuth + list + optional details, returning safe metadata.

    Production code paths are used unchanged: _get_access_token, list_disputes
    and get_dispute. Tests may pass an adapter with an in-memory HTTP transport;
    the CLI always uses the real httpx client.
    """
    if adapter is None:
        adapter = PayPalSandboxAdapter()

    outcome: dict[str, Any] = {
        "check": "proofgraph_backend_paypal_sandbox",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": "sandbox",
        "credential_source": "backend_settings_env",
        "oauth_token": {"http_status": None, "status": "NOT_RUN"},
        "disputes_list": {"http_status": None, "status": "NOT_RUN", "item_count": None},
        "dispute_detail": {"http_status": None, "status": "NOT_RUN"},
        "result": "BLOCKED",
        "reason": None,
    }

    # Fail closed: a smoke test must never accidentally contact production
    # or a user-provided, attacker-controlled endpoint.
    if (
        settings.PAYPAL_ENVIRONMENT.strip().lower() != "sandbox"
        or adapter.base_url.rstrip("/") != OFFICIAL_SANDBOX_URL
    ):
        outcome["reason"] = "UNSAFE_OR_NON_SANDBOX_CONFIGURATION"
        return outcome

    if not adapter.is_configured() or (
        adapter.client_id.startswith("your_paypal_")
        or adapter.client_secret.startswith("your_paypal_")
    ):
        outcome["reason"] = "SANDBOX_CREDENTIALS_NOT_CONFIGURED"
        return outcome

    try:
        # Only this method obtains the token; never serialize or print it.
        adapter._get_access_token()
        outcome["oauth_token"] = {"http_status": 200, "status": "PASS"}
    except PayPalAPIError as error:
        outcome["oauth_token"] = {"http_status": error.status_code, "status": "FAIL"}
        outcome["result"] = "FAIL"
        outcome["reason"] = _safe_failure_reason(error.status_code)
        return outcome
    except Exception:
        outcome["result"] = "FAIL"
        outcome["reason"] = "OAUTH_UNEXPECTED_ERROR"
        return outcome

    try:
        # Empty 'items' with HTTP 200 is success; auth/scope failures raise.
        items = adapter.list_disputes()
        if not isinstance(items, list):
            raise TypeError("Expected the adapter to return a dispute list")
        outcome["disputes_list"] = {
            "http_status": 200,
            "status": "PASS",
            "item_count": len(items),
        }
    except PayPalAPIError as error:
        outcome["disputes_list"] = {"http_status": error.status_code, "status": "FAIL", "item_count": None}
        outcome["result"] = "FAIL"
        outcome["reason"] = _safe_failure_reason(error.status_code)
        return outcome
    except Exception:
        outcome["result"] = "FAIL"
        outcome["reason"] = "DISPUTES_UNEXPECTED_ERROR"
        return outcome

    if dispute_id:
        try:
            # Optional read-only endpoint; identifiers and content stay private.
            details = adapter.get_dispute(dispute_id)
            if details is None:
                outcome["dispute_detail"] = {"http_status": 404, "status": "NOT_FOUND"}
                outcome["result"] = "FAIL"
                outcome["reason"] = "DISPUTE_NOT_FOUND"
                return outcome
            outcome["dispute_detail"] = {"http_status": 200, "status": "PASS"}
        except PayPalAPIError as error:
            outcome["dispute_detail"] = {"http_status": error.status_code, "status": "FAIL"}
            outcome["result"] = "FAIL"
            outcome["reason"] = _safe_failure_reason(error.status_code)
            return outcome
        except Exception:
            outcome["result"] = "FAIL"
            outcome["reason"] = "DISPUTE_DETAILS_UNEXPECTED_ERROR"
            return outcome

    outcome["result"] = "PASS"
    outcome["reason"] = "READ_ONLY_SANDBOX_OAUTH_AND_DISPUTES_CONFIRMED"
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only PayPal Sandbox OAuth and disputes API check using ProofGraph's backend adapter."
    )
    parser.add_argument(
        "--dispute-id",
        default=os.getenv("PAYPAL_SANDBOX_DISPUTE_ID") or None,
        help="Optional existing sandbox dispute ID for GET details; never shown in output.",
    )
    args = parser.parse_args()
    result = run_smoke(dispute_id=args.dispute_id)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
