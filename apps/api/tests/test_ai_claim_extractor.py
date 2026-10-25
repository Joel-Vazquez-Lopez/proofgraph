"""Issue #18 integration: real backend HTTP path, provider-contract mocks, safety."""
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.db_models import Base, engine, init_db, SessionLocal, DisputeCaseDB
from app.services import ai_claim_extractor


CASE_ID = "PP-D-INR-8841"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    Base.metadata.drop_all(bind=engine)
    init_db()
    with TestClient(app) as client:
        yield client


def _state(client):
    response = client.get(f"/api/v1/disputes/{CASE_ID}")
    assert response.status_code == 200
    return response.json()


def _real_quote_source(client):
    snapshot = _state(client)
    claim = next(n for n in snapshot["evidence_graph"]["nodes"]
                 if n["type"] == "CLAIM" and n["content"].get("text"))
    quote = claim["content"]["text"][:min(40, len(claim["content"]["text"]))]
    assert len(quote) >= 4
    return claim["id"], quote


def _mock_response(source_id, quote, *, claims=None, finish="stop"):
    return httpx.Response(
        200,
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        json={
            "model": "gpt-4o-mini-2024-07-18",
            "choices": [{
                "finish_reason": finish,
                "message": {"content": json.dumps({
                    "claims": claims if claims is not None else [{
                        "source_id": source_id, "quote": quote,
                        "claim_type": "NON_RECEIPT", "evidence_need": "HANDOFF_PROOF"
                    }]
                })}
            }],
        },
    )


def test_no_credentials_reports_fallback_no_model_call_and_graph_unchanged(client, monkeypatch):
    before = _state(client)
    def forbidden(*args, **kwargs):
        raise AssertionError("No external call without API key")
    monkeypatch.setattr(ai_claim_extractor.httpx, "post", forbidden)
    response = client.post(f"/api/v1/disputes/{CASE_ID}/ai/extract")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "FALLBACK_NOT_CONFIGURED"
    assert result["provider"] == "openai"
    assert result["model_called"] is False
    assert result["claims"] == []
    assert result["fallback_action_id"] == before["current_policy_decision"]["chosen_action"]["action_id"]
    after = _state(client)
    assert after["evidence_graph"] == before["evidence_graph"]
    assert after["state"] == before["state"]
    assert after["readiness"] == before["readiness"]


def test_disabled_provider_never_calls_model(client, monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "disabled")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "dummy")
    monkeypatch.setattr(ai_claim_extractor.httpx, "post", lambda *a, **k: pytest.fail("unexpected external call"))
    result = client.post(f"/api/v1/disputes/{CASE_ID}/ai/extract").json()
    assert result["status"] == "FALLBACK_DISABLED"
    assert result["model_called"] is False
    assert result["provider"] == "none"


def test_real_api_route_invokes_openai_http_and_persists_only_model_inference(client, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-only-not-real-secret")
    node_id, quote = _real_quote_source(client)
    before = _state(client)
    calls = []

    def intercept(url, *, json, headers, timeout, follow_redirects):
        payload = json
        calls.append((url, payload, headers))
        assert url == "https://api.openai.com/v1/chat/completions"
        assert payload["model"] == "gpt-4o-mini"
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert payload["temperature"] == 0
        assert headers["Authorization"] == "Bearer test-only-not-real-secret"
        assert follow_redirects is False
        sources = __import__("json").loads(payload["messages"][1]["content"])["source_documents"]
        assert any(x["source_id"] == node_id and quote in x["text"] for x in sources)
        assert "transaction_id" not in payload["messages"][1]["content"]
        return _mock_response(node_id, quote)

    monkeypatch.setattr(ai_claim_extractor.httpx, "post", intercept)
    first = client.post(f"/api/v1/disputes/{CASE_ID}/ai/extract")
    assert first.status_code == 200, first.text
    result = first.json()
    assert len(calls) == 1
    assert result["status"] == "MODEL_SUCCESS"
    assert result["model_called"] is True
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4o-mini"
    assert "test-only-not-real-secret" not in first.text
    assert result["claims"][0]["quote"] == quote
    assert result["claims"][0]["source_id"] == node_id
    assert result["claims"][0]["evidence_question"].endswith("?")
    assert result["claims"][0]["inference_node_id"].startswith("ai_claim_")

    after = _state(client)
    derived = [n for n in after["evidence_graph"]["nodes"]
               if n["id"].startswith("ai_claim_")]
    assert len(derived) == 1
    assert derived[0]["origin"] == "MODEL_INFERENCE"
    assert derived[0]["verification_status"] == "UNVERIFIED"
    assert derived[0]["metadata"]["independently_verified"] is False
    assert derived[0]["content"]["source_id"] == node_id
    assert any(e["type"] == "DERIVED_FROM" and e["source_id"] == derived[0]["id"]
               and e["target_id"] == node_id for e in after["evidence_graph"]["edges"])
    assert after["state"] == before["state"]
    assert after["readiness"] == before["readiness"]
    assert after["current_policy_decision"] == before["current_policy_decision"]

    # A second explicit model call cannot multiply the same graph assertion.
    second = client.post(f"/api/v1/disputes/{CASE_ID}/ai/extract")
    assert second.status_code == 200
    assert len(calls) == 2
    assert len([n for n in _state(client)["evidence_graph"]["nodes"]
                if n["id"].startswith("ai_claim_")]) == 1

    report = client.get(f"/api/v1/disputes/{CASE_ID}/report").json()
    assert all("ai_claim_" not in fact for fact in report["verified_facts"])


def test_invalid_citation_is_rejected_even_if_model_labels_it_verified(client, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "dummy")
    source_id, _ = _real_quote_source(client)
    before = _state(client)
    monkeypatch.setattr(ai_claim_extractor.httpx, "post", lambda *a, **k: _mock_response(
        source_id, "Externally verified delivery and signed receipt, buyer lying"
    ))
    response = client.post(f"/api/v1/disputes/{CASE_ID}/ai/extract")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "FALLBACK_NO_GROUNDED_CLAIMS"
    assert result["model_called"] is True
    assert result["claims"] == []
    assert _state(client)["evidence_graph"] == before["evidence_graph"]


def test_partial_model_output_keeps_only_grounded_quotes(client, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "dummy")
    source_id, quote = _real_quote_source(client)
    claims = [
        {"source_id": source_id, "quote": quote, "claim_type": "NON_RECEIPT",
         "evidence_need": "HANDOFF_PROOF"},
        {"source_id": "invented_provider_data", "quote": "Delivered", "claim_type": "DELIVERY_ASSERTION",
         "evidence_need": "TRACKING"},
    ]
    monkeypatch.setattr(ai_claim_extractor.httpx, "post", lambda *a, **k: _mock_response(
        source_id, quote, claims=claims
    ))
    result = client.post(f"/api/v1/disputes/{CASE_ID}/ai/extract").json()
    assert result["status"] == "MODEL_PARTIAL"
    assert result["rejected_items"] == 1
    assert len(result["claims"]) == 1
    assert result["claims"][0]["source_id"] == source_id


@pytest.mark.parametrize("fault", ["network", "unauthorized", "malformed", "truncated"])
def test_provider_failures_fallback_without_case_mutation(client, monkeypatch, fault):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "dummy")
    source_id, quote = _real_quote_source(client)
    before = _state(client)
    def failing(url, **kwargs):
        if fault == "network":
            raise httpx.ConnectTimeout("provider timeout")
        if fault == "unauthorized":
            return httpx.Response(401, request=httpx.Request("POST", url), json={"error": "bad key"})
        if fault == "malformed":
            return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": []})
        return _mock_response(source_id, quote, finish="length")
    monkeypatch.setattr(ai_claim_extractor.httpx, "post", failing)
    result = client.post(f"/api/v1/disputes/{CASE_ID}/ai/extract").json()
    assert result["status"].startswith("FALLBACK_")
    assert result["model_called"] is True
    assert result["claims"] == []
    after = _state(client)
    assert after["evidence_graph"] == before["evidence_graph"]
    assert after["readiness"] == before["readiness"]


def test_reviewer_permission_blocks_merchant_buyer_and_cross_case_exfiltration(client, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "dummy")
    monkeypatch.setattr(ai_claim_extractor.httpx, "post", lambda *a, **k: pytest.fail("no external call"))
    details = _state(client)
    for role, user_id in [
        ("MERCHANT", details["seller_id"]),
        ("BUYER", details["buyer_id"]),
        ("MERCHANT", "other-seller"),
    ]:
        response = client.post(f"/api/v1/disputes/{CASE_ID}/ai/extract",
                               headers={"X-User-Role": role, "X-User-Id": user_id})
        assert response.status_code == 403


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_AI_TEST") != "1" or not os.environ.get("OPENAI_API_KEY"),
    reason="Live OpenAI smoke test requires RUN_LIVE_AI_TEST=1 and OPENAI_API_KEY",
)
def test_optional_live_openai_claim_extraction(monkeypatch):
    """Makes a genuine outbound model call; never runs with fixture data only."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", os.environ["OPENAI_API_KEY"])
    Base.metadata.drop_all(bind=engine)
    init_db()
    with TestClient(app) as tc:
        response = tc.post(f"/api/v1/disputes/{CASE_ID}/ai/extract")
        assert response.status_code == 200, response.text
        outcome = response.json()
        assert outcome["model_called"] is True
        assert outcome["status"] in ("MODEL_SUCCESS", "MODEL_PARTIAL"), outcome["message"]
        assert all(x["source_id"] and x["quote"] for x in outcome["claims"])
