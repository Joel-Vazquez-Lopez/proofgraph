"""Offline contract tests for the *real* PayPal backend adapter's HTTP path.

httpx.MockTransport supplies deterministic protocol responses only in this test
module. The live smoke CLI has no mocked transport and requires Sandbox secrets.
"""
import base64
import json

import httpx
import pytest

from app.adapters.paypal_sandbox import PayPalSandboxAdapter
from app.config import settings
from app.services.paypal_sandbox_smoke import run_smoke, main


@pytest.fixture
def sandbox_adapter(monkeypatch):
    monkeypatch.setattr(settings, "PAYPAL_ENVIRONMENT", "sandbox")
    monkeypatch.setattr(settings, "PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_ID", "unit_sandbox_client_id")
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", "unit_sandbox_client_secret")
    return PayPalSandboxAdapter()


def wire_http(monkeypatch, handler):
    """Use real httpx request encoding and headers, but no external network."""
    original_client = httpx.Client
    requests = []

    def record(request):
        requests.append(request)
        return handler(request)

    transport = httpx.MockTransport(record)
    monkeypatch.setattr(
        httpx, "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    return requests


def oauth_ok(request):
    assert request.method == "POST"
    assert request.url.scheme == "https"
    assert request.url.host == "api-m.sandbox.paypal.com"
    assert request.url.path == "/v1/oauth2/token"
    assert request.content == b"grant_type=client_credentials"
    assert request.headers["authorization"] == (
        "Basic " + base64.b64encode(
            b"unit_sandbox_client_id:unit_sandbox_client_secret"
        ).decode("ascii")
    )
    return httpx.Response(200, json={
        "access_token": "unit-secret-access-token",
        "token_type": "Bearer",
        "expires_in": 3600,
    })


def test_backend_uses_same_env_settings_and_reads_empty_disputes(monkeypatch, sandbox_adapter):
    assert sandbox_adapter.client_id == settings.PAYPAL_CLIENT_ID
    assert sandbox_adapter.client_secret == settings.PAYPAL_CLIENT_SECRET

    def handler(request):
        if request.url.path.endswith("/oauth2/token"):
            return oauth_ok(request)
        assert request.method == "GET"
        assert request.url.path == "/v1/customer/disputes"
        assert request.headers["authorization"] == "Bearer unit-secret-access-token"
        return httpx.Response(200, json={"items": []})

    requests = wire_http(monkeypatch, handler)
    result = run_smoke(sandbox_adapter)

    assert result["result"] == "PASS"
    assert result["oauth_token"] == {"http_status": 200, "status": "PASS"}
    assert result["disputes_list"] == {"http_status": 200, "status": "PASS", "item_count": 0}
    assert result["dispute_detail"]["status"] == "NOT_RUN"
    assert result["checked_at_utc"]
    assert [r.method for r in requests] == ["POST", "GET"]
    serialized = json.dumps(result)
    assert "unit_sandbox_client_secret" not in serialized
    assert "unit-secret-access-token" not in serialized
    assert "unit_sandbox_client_id" not in serialized


def test_optional_dispute_details_remain_private_and_read_only(monkeypatch, sandbox_adapter):
    dispute_id = "PP-D-NO-LOGS-123"

    def handler(request):
        if request.url.path.endswith("/oauth2/token"):
            return oauth_ok(request)
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer unit-secret-access-token"
        if request.url.path == "/v1/customer/disputes":
            return httpx.Response(200, json={"items": [{"dispute_id": dispute_id}]})
        assert request.url.path == f"/v1/customer/disputes/{dispute_id}"
        return httpx.Response(200, json={"dispute_id": dispute_id, "messages": ["private buyer statement"]})

    requests = wire_http(monkeypatch, handler)
    result = run_smoke(sandbox_adapter, dispute_id=dispute_id)
    assert result["result"] == "PASS"
    assert result["disputes_list"]["item_count"] == 1
    assert result["dispute_detail"] == {"http_status": 200, "status": "PASS"}
    assert [r.method for r in requests] == ["POST", "GET", "GET"]
    serialized = json.dumps(result)
    assert dispute_id not in serialized
    assert "private buyer statement" not in serialized


def test_oauth_failure_reports_http_status_without_response_body(monkeypatch, sandbox_adapter):
    message = "upstream secret-like-error-body"

    def handler(request):
        assert request.url.path == "/v1/oauth2/token"
        return httpx.Response(401, text=message)

    requests = wire_http(monkeypatch, handler)
    result = run_smoke(sandbox_adapter)
    assert result["result"] == "FAIL"
    assert result["oauth_token"]["http_status"] == 401
    assert result["disputes_list"]["status"] == "NOT_RUN"
    assert result["reason"] == "AUTHENTICATION_OR_DISPUTES_PERMISSION_DENIED"
    assert len(requests) == 1
    assert message not in json.dumps(result)


def test_disputes_permission_denied_is_not_an_empty_list(monkeypatch, sandbox_adapter):
    def handler(request):
        if request.url.path.endswith("/oauth2/token"):
            return oauth_ok(request)
        return httpx.Response(403, text="private upstream error details")

    requests = wire_http(monkeypatch, handler)
    result = run_smoke(sandbox_adapter)
    assert len(requests) == 2
    assert result["oauth_token"]["http_status"] == 200
    assert result["disputes_list"]["http_status"] == 403
    assert result["disputes_list"]["item_count"] is None
    assert result["result"] == "FAIL"
    assert "private upstream" not in json.dumps(result)


def test_unset_credentials_report_blocked_without_http(monkeypatch, sandbox_adapter):
    sandbox_adapter.client_secret = ""
    requests = wire_http(monkeypatch, lambda request: pytest.fail("No network when missing credentials"))
    result = run_smoke(sandbox_adapter)
    assert result["result"] == "BLOCKED"
    assert result["reason"] == "SANDBOX_CREDENTIALS_NOT_CONFIGURED"
    assert not requests


@pytest.mark.parametrize("environment,url", [
    ("live", "https://api-m.paypal.com"),
    ("sandbox", "https://not-paypal.example.test"),
    ("sandbox", "https://api-m.paypal.com"),
])
def test_smoke_cannot_contact_production_or_arbitrary_host(
    monkeypatch, sandbox_adapter, environment, url
):
    monkeypatch.setattr(settings, "PAYPAL_ENVIRONMENT", environment)
    sandbox_adapter.base_url = url
    requests = wire_http(monkeypatch, lambda request: pytest.fail("Unsafe endpoint was contacted"))
    result = run_smoke(sandbox_adapter)
    assert result["result"] == "BLOCKED"
    assert result["reason"] == "UNSAFE_OR_NON_SANDBOX_CONFIGURATION"
    assert not requests


def test_optional_missing_dispute_is_visible_as_404_not_success(monkeypatch, sandbox_adapter):
    def handler(request):
        if request.url.path.endswith("/oauth2/token"):
            return oauth_ok(request)
        if request.url.path == "/v1/customer/disputes":
            return httpx.Response(200, json={"items": []})
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})

    requests = wire_http(monkeypatch, handler)
    result = run_smoke(sandbox_adapter, dispute_id="PP-D-UNKNOWN")
    assert len(requests) == 3
    assert result["oauth_token"]["status"] == "PASS"
    assert result["disputes_list"]["status"] == "PASS"
    assert result["dispute_detail"] == {"http_status": 404, "status": "NOT_FOUND"}
    assert result["result"] == "FAIL"


def test_cli_emits_only_safe_json_and_nonzero_exit_on_missing_credentials(
    monkeypatch, sandbox_adapter, capsys
):
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", "")
    monkeypatch.setattr(
        "app.services.paypal_sandbox_smoke.PayPalSandboxAdapter",
        lambda: PayPalSandboxAdapter(),
    )
    monkeypatch.setattr("sys.argv", ["paypal_sandbox_smoke"])
    assert main() == 1
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["result"] == "BLOCKED"
    assert parsed["reason"] == "SANDBOX_CREDENTIALS_NOT_CONFIGURED"


@pytest.mark.parametrize("payload", [{}, {"items": None}, {"items": "not-a-list"}])
def test_http_200_without_valid_items_does_not_pass_as_empty(
    monkeypatch, sandbox_adapter, payload
):
    def handler(request):
        if request.url.path.endswith("/oauth2/token"):
            return oauth_ok(request)
        return httpx.Response(200, json=payload)

    wire_http(monkeypatch, handler)
    result = run_smoke(sandbox_adapter)
    assert result["oauth_token"]["http_status"] == 200
    assert result["disputes_list"]["http_status"] == 502
    assert result["disputes_list"]["item_count"] is None
    assert result["result"] == "FAIL"


def test_malformed_oauth_token_does_not_look_authenticated(monkeypatch, sandbox_adapter):
    requests = wire_http(
        monkeypatch,
        lambda request: httpx.Response(200, json={"expires_in": 3600}),
    )
    result = run_smoke(sandbox_adapter)
    assert result["result"] == "FAIL"
    assert result["oauth_token"]["http_status"] == 502
    assert result["disputes_list"]["status"] == "NOT_RUN"
    assert len(requests) == 1
