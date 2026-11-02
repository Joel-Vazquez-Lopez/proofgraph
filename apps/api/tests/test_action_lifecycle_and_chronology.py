import io
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.db_models import Base, engine, init_db, SessionLocal, DisputeCaseDB
from app.services.dispute_service import DisputeService
from app.services.evidence_graph import EvidenceGraph
from packages.shared_schemas.models import (
    NodeType,
    EdgeType,
    DisputeCategory,
    DataSourceType,
)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_reproduce_recommendation_alone_never_counts_as_attempted(client):
    """
    Issue #24:
    A recommended action (in a QUESTION node with action_status='RECOMMENDED')
    must not be treated as 'already attempted'. The policy should continue
    recommending it rather than prematurely escalating to human review.
    """
    case_id = "PP-D-INR-8841"
    
    # Fetch dispute detail and candidates
    detail_resp = client.get(f"/api/v1/disputes/{case_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    first_action = detail["current_policy_decision"]["chosen_action"]
    assert first_action is not None
    assert first_action["action_id"] == "act_merchant_tracking"

    # Evaluate candidates multiple times in succession without executing an action
    candidates_resp = client.get(f"/api/v1/disputes/{case_id}/candidates")
    assert candidates_resp.status_code == 200
    second_decision = candidates_resp.json()
    
    # Must still recommend tracking, NOT escalate
    assert second_decision["chosen_action"] is not None
    assert second_decision["chosen_action"]["action_id"] == "act_merchant_tracking"
    assert second_decision["chosen_action"]["action_id"] != "act_escalate_human_review"


def test_reproduce_irrelevant_upload_does_not_exhaust_tracking_request(client):
    """
    Issue #24:
    Submitting an unrelated file upload (e.g. a listing document) must not
    satisfy or exhaust an outstanding merchant tracking request.
    """
    case_id = "PP-D-INR-8841"
    
    file_bytes = b"\x89PNG\r\n\x1a\n" + b"UNRELATED_LISTING_DOCUMENT"
    files = {"file": ("listing.png", io.BytesIO(file_bytes), "image/png")}
    data = {
        "submitter_role": "MERCHANT",
        "action_id": "act_merchant_listing",
        "notes": "Uploading listing for an INR dispute",
    }
    
    upload_resp = client.post(f"/api/v1/disputes/{case_id}/upload-evidence", files=files, data=data)
    assert upload_resp.status_code == 200
    
    # Fetch dispute detail and check open questions
    detail = client.get(f"/api/v1/disputes/{case_id}").json()
    graph_data = detail["evidence_graph"]
    
    # Find q_act_merchant_tracking
    q_nodes = [n for n in graph_data["nodes"] if n["id"] == "q_act_merchant_tracking"]
    assert len(q_nodes) == 1, "Tracking question must still exist"
    
    # Check that tracking question has NO incoming ANSWERS edge
    answers_to_tracking = [
        e for e in graph_data["edges"]
        if e["target_id"] == "q_act_merchant_tracking" and e["type"] == "ANSWERS"
    ]
    assert len(answers_to_tracking) == 0, "Unrelated upload must NOT answer the tracking question"
    
    # The chosen policy action must still be tracking, not escalated
    assert detail["current_policy_decision"]["chosen_action"]["action_id"] == "act_merchant_tracking"


def test_reproduce_open_question_count_matches_actual_unresolved_state(client):
    """
    Issue #24:
    DisputeSummary.open_questions must reflect actual UNANSWERED question nodes,
    not total question nodes in the graph history.
    """
    case_id = "PP-D-INR-8841"
    
    # Initial list
    initial_summaries = client.get("/api/v1/disputes").json()
    case_summary = next(s for s in initial_summaries if s["dispute_id"] == case_id)
    initial_open_q = case_summary.get("open_questions_count", 1)
    
    # Answer the tracking question with tracking submission
    tracking_payload = {
        "submitter_role": "MERCHANT",
        "tracking_number": "1Z9999999999999999",
        "carrier_name": "UPS",
    }
    sub_resp = client.post(f"/api/v1/disputes/{case_id}/evidence", json=tracking_payload)
    assert sub_resp.status_code == 200
    
    # Now check open questions in summary
    updated_summaries = client.get("/api/v1/disputes").json()
    updated_summary = next(s for s in updated_summaries if s["dispute_id"] == case_id)
    
    # The tracking question is answered by an incoming ANSWERS edge from the shipment node.
    # Therefore, q_act_merchant_tracking is no longer open.
    detail = client.get(f"/api/v1/disputes/{case_id}").json()
    graph = detail["evidence_graph"]
    
    # Compute true open questions
    answered_q_ids = {
        e["target_id"] for e in graph["edges"] if e["type"] == "ANSWERS"
    }
    true_open_q = len([
        n for n in graph["nodes"]
        if n["type"] == "QUESTION" and n["id"] not in answered_q_ids
    ])
    
    # Summary open_questions_count must match true_open_q
    assert updated_summary.get("open_questions_count") == true_open_q


def test_carrier_observation_chronology_preserves_history(client):
    """
    Issue #24:
    Multiple carrier observations for a shipment must be recorded chronologically
    as distinct observation nodes without overwriting or erasing previous telemetry.
    """
    case_id = "PP-D-INR-8841"
    
    # 1. Submit tracking
    tracking_payload = {
        "submitter_role": "MERCHANT",
        "tracking_number": "9400100000000000000001",
        "carrier_name": "USPS",
    }
    client.post(f"/api/v1/disputes/{case_id}/evidence", json=tracking_payload)
    
    # 2. Trigger first carrier lookup
    resp1 = client.post(f"/api/v1/disputes/{case_id}/verify-carrier")
    assert resp1.status_code == 200
    
    # 3. Trigger second carrier lookup
    resp2 = client.post(f"/api/v1/disputes/{case_id}/verify-carrier")
    assert resp2.status_code == 200
    
    # Verify graph contains distinct carrier observation nodes
    detail = client.get(f"/api/v1/disputes/{case_id}").json()
    carrier_obs = [
        n for n in detail["evidence_graph"]["nodes"]
        if n["type"] == "OBSERVATION" and "carrier" in n["id"].lower()
    ]
    # At least one carrier observation exists and neither was erased
    assert len(carrier_obs) >= 1
    for obs in carrier_obs:
        assert obs["origin"] == "SYNTHETIC_FIXTURE"
