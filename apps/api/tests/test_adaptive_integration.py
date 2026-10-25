"""Opt-in end-to-end investigation test through existing FastAPI routes."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.models.db_models import Base, engine, init_db


@pytest.fixture
def adaptive_client(monkeypatch):
    monkeypatch.setattr(settings, "NBE_POLICY_TYPE", "discriminative")
    Base.metadata.drop_all(bind=engine)
    init_db()
    with TestClient(app) as client:
        yield client


def test_real_api_reassesses_after_tracking_and_carrier_data(adaptive_client):
    client = adaptive_client
    case_id = "PP-D-INR-8841"
    initial = client.get(f"/api/v1/disputes/{case_id}")
    assert initial.status_code == 200
    case = initial.json()
    assert case["current_policy_decision"]["policy_name"] == "HypothesisDiscriminationPolicy"
    assert case["current_policy_decision"]["chosen_action"]["action_id"] == "act_merchant_tracking"

    submitted = client.post(f"/api/v1/disputes/{case_id}/evidence", json={
        "action_id": "act_merchant_tracking",
        "submitter_role": "MERCHANT",
        "tracking_number": "940010009999",
        "carrier_name": "USPS",
        "verify_carrier_now": False,
    })
    assert submitted.status_code == 200, submitted.text
    tracking = client.get(f"/api/v1/disputes/{case_id}").json()
    assert tracking["current_policy_decision"]["chosen_action"]["action_id"] == "act_carrier_lookup"
    assert not tracking["readiness"]["is_decision_ready"]
    shipment = next(n for n in tracking["evidence_graph"]["nodes"] if n["type"] == "SHIPMENT")
    assert shipment["origin"] == "USER_SUBMITTED"
    assert shipment["verification_status"] == "UNVERIFIED"

    checked = client.post(f"/api/v1/disputes/{case_id}/verify-carrier")
    assert checked.status_code == 200, checked.text
    updated = client.get(f"/api/v1/disputes/{case_id}").json()
    decision = updated["current_policy_decision"]["chosen_action"]
    assert decision["action_id"] == "act_request_signature_or_proof"
    assert "buyer_physically_received_item" in decision["rationale"]
    observations = [n for n in updated["evidence_graph"]["nodes"] if n["type"] == "OBSERVATION"]
    assert observations
    assert all(obs["origin"] == "SYNTHETIC_FIXTURE" for obs in observations)
    assert "Evidence basis: SIMULATED" in decision["rationale"]
    assert updated["readiness"]["is_decision_ready"] is False


def test_existing_wrong_address_demo_case_selects_discrepancy_reconciliation(adaptive_client):
    detail = adaptive_client.get("/api/v1/disputes/PP-D-INR-9923").json()
    decision = detail["current_policy_decision"]["chosen_action"]
    assert decision["action_id"] == "act_resolve_contradiction"
    assert "Evidence basis: SIMULATED" in decision["rationale"]
    assert "obs_delivery_5678" in decision["rationale"]
    assert detail["readiness"]["is_decision_ready"] is False
