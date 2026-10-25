import pytest
from fastapi.testclient import TestClient
from app.main import app
from packages.shared_schemas.models import InvestigationState


from app.models.db_models import Base, engine, init_db


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "paypal_sandbox_configured" in data


def test_list_disputes(client):
    response = client.get("/api/v1/disputes")
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 4
    ids = [i["dispute_id"] for i in items]
    assert "PP-D-INR-8841" in ids
    
    # Verify case-data consistency: exact product and buyer mappings
    item_map = {i["dispute_id"]: i for i in items}
    assert item_map["PP-D-INR-8841"]["item_name"] == "Keychron Q1 Pro Wireless Mechanical Keyboard"
    assert item_map["PP-D-INR-8841"]["buyer_name"] == "Sarah Connor"
    assert item_map["PP-D-INR-9923"]["item_name"] == "Sony WH-1000XM5 Noise Canceling Headphones"
    assert item_map["PP-D-INR-9923"]["buyer_name"] == "Alex Rivera"


def test_get_dispute_and_graph(client):
    response = client.get("/api/v1/disputes/PP-D-INR-8841")
    assert response.status_code == 200
    data = response.json()
    assert data["dispute_id"] == "PP-D-INR-8841"
    assert data["category"] == "ITEM_NOT_RECEIVED"
    assert data["state"] == "AWAITING_EVIDENCE"
    assert data["item_name"] == "Keychron Q1 Pro Wireless Mechanical Keyboard"
    assert data["buyer_name"] == "Sarah Connor"
    assert "evidence_graph" in data
    assert len(data["evidence_graph"]["nodes"]) >= 3


def test_end_to_end_inr_investigation_slice(client):
    """
    Vertical slice test demonstrating the full Phase 2 evidence provenance lifecycle:
    1. Case PP-D-INR-8841 starts in AWAITING_EVIDENCE (missing tracking).
    2. Merchant submits tracking — ingested as USER_SUBMITTED / UNVERIFIED.
    3. A simulated carrier fixture lookup executes via /verify-carrier.
    4. Fixture reports DELIVERED (no signature) + buyer has non-receipt claim →
       Scenario A: case moves to INVESTIGATING with open delivery question.
    5. The simulated observation is explicitly scoped as SIMULATED_FIXTURE.
    6. Report is generated (reflects current state).
    """
    # 1. Verify initial state
    resp1 = client.get("/api/v1/disputes/PP-D-INR-8841")
    assert resp1.status_code == 200
    initial_data = resp1.json()
    assert initial_data["state"] == "AWAITING_EVIDENCE"
    assert not initial_data["readiness"]["is_decision_ready"]

    # 2. Merchant submits tracking number without instant verification
    submission_payload = {
        "action_id": "act_merchant_tracking",
        "submitter_role": "MERCHANT",
        "carrier_name": "USPS",
        "tracking_number": "940010009999",
        "verify_carrier_now": False,
        "notes": "Here is the USPS tracking number."
    }
    resp2 = client.post("/api/v1/disputes/PP-D-INR-8841/evidence", json=submission_payload)
    assert resp2.status_code == 200
    result_unverified = resp2.json()
    assert result_unverified["success"] is True
    # Phase 2 invariant: tracking alone is UNVERIFIED and does not claim decision-ready
    assert result_unverified["readiness"]["is_decision_ready"] is False

    # Check intermediate state: shipment node exists but is unverified
    resp_inter = client.get("/api/v1/disputes/PP-D-INR-8841")
    assert resp_inter.status_code == 200
    inter_data = resp_inter.json()
    shipment_nodes = [n for n in inter_data["evidence_graph"]["nodes"] if n["type"] == "SHIPMENT"]
    assert len(shipment_nodes) == 1
    assert shipment_nodes[0]["origin"] == "USER_SUBMITTED"
    assert shipment_nodes[0]["verification_status"] == "UNVERIFIED"

    # 3. Trigger explicitly simulated carrier fixture lookup
    resp_verify = client.post("/api/v1/disputes/PP-D-INR-8841/verify-carrier")
    assert resp_verify.status_code == 200
    result_verified = resp_verify.json()
    assert result_verified["success"] is True

    # 4. Scenario A: Carrier delivered without signature + buyer has non-receipt claim
    #    → case INVESTIGATING (not DECISION_READY) with open delivery question
    assert result_verified["new_state"] == "INVESTIGATING"
    assert result_verified["readiness"]["is_decision_ready"] is False
    # The readiness must identify the unresolved buyer non-receipt question
    missing_reqs = result_verified["readiness"]["missing_requirements"]
    assert any("buyer" in m.lower() and "non-receipt" in m.lower() for m in missing_reqs)

    # 5. Check updated dispute detail — fixture observation is not an external verification
    resp3 = client.get("/api/v1/disputes/PP-D-INR-8841")
    assert resp3.status_code == 200
    updated_detail = resp3.json()
    assert updated_detail["state"] == "INVESTIGATING"

    obs_nodes = [n for n in updated_detail["evidence_graph"]["nodes"] if n["type"] == "OBSERVATION"]
    assert len(obs_nodes) >= 1
    assert obs_nodes[0]["verification_status"] == "VERIFIED"  # fixture scenario truth only
    assert obs_nodes[0]["origin"] == "SYNTHETIC_FIXTURE"
    assert obs_nodes[0]["metadata"]["verification_scope"] == "SIMULATED_FIXTURE"
    assert obs_nodes[0]["metadata"]["independently_verified"] is False
    assert obs_nodes[0]["verified_at"] is None

    # 6. Report is generated reflecting current investigative state
    resp_report = client.get("/api/v1/disputes/PP-D-INR-8841/report")
    assert resp_report.status_code == 200
    report = resp_report.json()
    assert report["dispute_id"] == "PP-D-INR-8841"
    assert report["verified_facts"] == []
    assert len(report["simulated_facts"]) >= 1
    assert all("SIMULATED" in fact for fact in report["simulated_facts"])

    # Markdown report is generated
    resp_md = client.get("/api/v1/disputes/PP-D-INR-8841/report/markdown")
    assert resp_md.status_code == 200
    assert "# PayPal AI Dispute Investigation Package" in resp_md.text
