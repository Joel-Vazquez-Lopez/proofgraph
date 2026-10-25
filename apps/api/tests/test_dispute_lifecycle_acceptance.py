"""Issue #12: real FastAPI + SQLAlchemy dispute lifecycle acceptance tests.

These tests exercise the mounted app and persisted case graphs through TestClient.
There are no patched services, mocked transport responses, or fake HTTP response objects.
Synthetic carrier fixtures remain *clearly simulated*; external lookups are unavailable.
"""
import hashlib
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.db_models import Base, engine, init_db, SessionLocal, DisputeCaseDB
from packages.shared_schemas.models import DataSourceType


INR = "PP-D-INR-8841"
WRONG_ZIP = "PP-D-INR-9923"
MATCHING_TRACKING = "940010009999"
WRONG_ZIP_TRACKING = "1Z9999999912345678"
UNKNOWN_TRACKING = "NO_FIXTURE_9988"
DOCUMENT = b"%PDF-1.4\nMerchant shipping receipt (not independently verified).\n%%EOF"


@pytest.fixture(autouse=True)
def isolated_real_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    with TestClient(app) as api:
        yield api


def detail(client, case_id=INR):
    response = client.get(f"/api/v1/disputes/{case_id}")
    assert response.status_code == 200, response.text
    return response.json()


def graph(client, case_id=INR):
    response = client.get(f"/api/v1/disputes/{case_id}/graph")
    assert response.status_code == 200, response.text
    return response.json()


def report(client, case_id=INR):
    response = client.get(f"/api/v1/disputes/{case_id}/report")
    assert response.status_code == 200, response.text
    return response.json()


def nodes(payload, kind):
    return [n for n in payload["nodes"] if n["type"] == kind]


def submit_tracking(client, tracking=MATCHING_TRACKING, case_id=INR, *, lookup=False, carrier="USPS"):
    return client.post(f"/api/v1/disputes/{case_id}/evidence", json={
        "submitter_role": "MERCHANT",
        "action_id": "act_merchant_tracking",
        "carrier_name": carrier,
        "tracking_number": tracking,
        "verify_carrier_now": lookup,
        "notes": "Merchant supplied tracking ID; not independent delivery proof.",
    })


def upload_pdf(client, *, case_id=INR, name="receipt.pdf", role="MERCHANT"):
    return client.post(
        f"/api/v1/disputes/{case_id}/upload-evidence",
        data={"submitter_role": role, "notes": "Merchant supporting document"},
        files={"file": (name, io.BytesIO(DOCUMENT), "application/pdf")},
    )


def _verify_result(client, case_id=INR, **params):
    return client.post(f"/api/v1/disputes/{case_id}/verify-carrier", params=params)


def test_complete_merchant_journey_uses_real_api_and_persists_auditable_package(client):
    available = client.get("/api/v1/disputes")
    assert available.status_code == 200
    assert INR in {d["dispute_id"] for d in available.json()}

    start = detail(client)
    assert start["state"] == "AWAITING_EVIDENCE"
    assert start["category"] == "ITEM_NOT_RECEIVED"
    assert start["data_source"] == "SYNTHETIC_FIXTURE"
    assert start["readiness"]["is_decision_ready"] is False
    assert not nodes(start["evidence_graph"], "SHIPMENT")

    submitted = submit_tracking(client)
    assert submitted.status_code == 200, submitted.text
    after_submit = detail(client)
    shipment = nodes(after_submit["evidence_graph"], "SHIPMENT")[0]
    assert shipment["content"]["tracking_number"] == MATCHING_TRACKING
    assert shipment["verification_status"] == "UNVERIFIED"
    assert shipment["origin"] == "USER_SUBMITTED"
    assert shipment["verified_at"] is None
    assert not nodes(after_submit["evidence_graph"], "OBSERVATION")
    assert after_submit["readiness"]["is_decision_ready"] is False

    carrier = _verify_result(client)
    assert carrier.status_code == 200, carrier.text
    assert "simulated" in carrier.json()["message"].lower()
    after_carrier = detail(client)
    obs = nodes(after_carrier["evidence_graph"], "OBSERVATION")
    assert len(obs) == 1
    first_obs = obs[0]
    assert first_obs["content"]["verification_outcome"] == "SIMULATED"
    assert first_obs["content"]["independently_verified"] is False
    assert first_obs["origin"] == "SYNTHETIC_FIXTURE"
    assert first_obs["metadata"]["verification_scope"] == "SIMULATED_FIXTURE"
    assert first_obs["verified_at"] is None
    assert nodes(after_carrier["evidence_graph"], "SHIPMENT")[0]["verification_status"] == "UNVERIFIED"
    assert after_carrier["state"] == "INVESTIGATING"
    assert not after_carrier["readiness"]["is_decision_ready"]
    assert any("non-receipt" in m.lower() for m in after_carrier["readiness"]["missing_requirements"])

    upload = upload_pdf(client)
    assert upload.status_code == 200, upload.text
    finding = upload.json()["integrity_finding"]
    assert finding["sha256_hash"] == hashlib.sha256(DOCUMENT).hexdigest()
    assert finding["mime_type"] == "application/pdf"
    after_upload = detail(client)
    items = nodes(after_upload["evidence_graph"], "EVIDENCE_ITEM")
    assert len(items) == 1
    assert items[0]["origin"] == "USER_SUBMITTED"
    assert items[0]["verification_status"] == "UNVERIFIED"
    assert items[0]["verified_at"] is None
    assert len(after_upload["integrity_findings"]) == 1
    assert not after_upload["readiness"]["is_decision_ready"]

    # The second carrier request is an append-only observation event, not a rewrite.
    second_carrier = _verify_result(client)
    assert second_carrier.status_code == 200, second_carrier.text
    refreshed = detail(client)
    observation_history = nodes(refreshed["evidence_graph"], "OBSERVATION")
    assert len(observation_history) == 2
    assert len({n["id"] for n in observation_history}) == 2
    assert first_obs["id"] in {n["id"] for n in observation_history}
    assert first_obs["content"] == next(
        n["content"] for n in observation_history if n["id"] == first_obs["id"]
    )
    assert len(refreshed["timeline"]) >= len(start["timeline"]) + 4

    graph_response = graph(client)
    assert graph_response == refreshed["evidence_graph"]
    source_ids = {n["id"] for n in graph_response["nodes"]}
    assert all(e["source_id"] in source_ids and e["target_id"] in source_ids for e in graph_response["edges"])
    assert all(any(
        e["type"] == "DERIVED_FROM" and e["source_id"] == o["id"]
        and e["target_id"] == shipment["id"]
        for e in graph_response["edges"]
    ) for o in observation_history)

    package = report(client)
    assert package["data_source"] == "SYNTHETIC_FIXTURE"
    assert package["verified_facts"] == []
    assert len(package["simulated_facts"]) == 2
    assert len(package["integrity_findings"]) == 1
    assert package["readiness_evaluation"] == refreshed["readiness"]
    assert package["recommended_adjudication_handoff"] == "CONTINUE_EVIDENCE_GATHERING"
    inventory = {entry["node_id"]: entry for entry in package["evidence_provenance_trail"]}
    assert inventory[items[0]["id"]]["independently_verified"] is False
    assert inventory[items[0]["id"]]["origin"] == "USER_SUBMITTED"
    assert all(inventory[o["id"]]["verification_scope"] == "SIMULATED_FIXTURE" for o in observation_history)
    candidates = client.get(f"/api/v1/disputes/{INR}/candidates")
    assert candidates.status_code == 200
    assert candidates.json()["policy_name"]
    markdown = client.get(f"/api/v1/disputes/{INR}/report/markdown")
    assert markdown.status_code == 200
    assert "Simulated Demo Observations (NOT Externally Verified)" in markdown.text
    assert finding["sha256_hash"] in markdown.text


def test_missing_tracking_and_unrelated_upload_do_not_falsely_answer_tracking_question(client):
    start = detail(client)
    questions = nodes(start["evidence_graph"], "QUESTION")
    assert questions, "Seed case should ask for missing evidence"
    tracking_questions = [q for q in questions if "tracking" in q["label"].lower()]
    assert tracking_questions
    before = {q["id"] for q in tracking_questions}

    no_tracking = _verify_result(client)
    assert no_tracking.status_code == 400
    assert "no shipment" in no_tracking.json()["detail"].lower()
    assert {q["id"] for q in nodes(graph(client), "QUESTION")} == {q["id"] for q in questions}

    upload = upload_pdf(client)
    assert upload.status_code == 200, upload.text
    current = graph(client)
    answered = {e["target_id"] for e in current["edges"] if e["type"] == "ANSWERS"}
    assert before.isdisjoint(answered), "Document upload cannot satisfy an unrelated tracking request"
    assert any(x["id"] in before for x in nodes(current, "QUESTION"))
    assert not detail(client)["readiness"]["is_decision_ready"]
    assert report(client)["missing_evidence_inventory"]


def test_wrong_address_dispute_exposes_contradiction_and_keeps_simulated_scope(client):
    start = detail(client, WRONG_ZIP)
    contradictions = [e for e in start["evidence_graph"]["edges"] if e["type"] == "CONTRADICTS"]
    assert contradictions, "Existing Seattle vs Portland discrepancy must be retained"
    response = _verify_result(client, WRONG_ZIP)
    assert response.status_code == 200, response.text
    latest = detail(client, WRONG_ZIP)
    assert latest["readiness"]["requires_escalation"] is True
    assert latest["readiness"]["is_decision_ready"] is False
    assert latest["readiness"]["active_contradictions"]
    assert any(e["type"] == "CONTRADICTS" for e in latest["evidence_graph"]["edges"])
    observation = nodes(latest["evidence_graph"], "OBSERVATION")
    assert len(observation) == 2
    assert all(o["origin"] == "SYNTHETIC_FIXTURE" for o in observation)
    assert all(o["verified_at"] is None for o in observation)
    package = report(client, WRONG_ZIP)
    assert package["verified_facts"] == []
    assert package["identified_contradictions"]
    assert len(package["simulated_facts"]) == 2
    assert package["recommended_adjudication_handoff"] == "ESCALATE_TO_SENIOR_REVIEWER"


def test_unavailable_external_carrier_retains_unknowns_even_with_uploaded_receipt(client):
    # Real persisted case record; only replace its source to exercise the honest
    # unavailable-provider boundary, without any carrier network call.
    assert detail(client)
    with SessionLocal() as db:
        case = db.query(DisputeCaseDB).filter_by(dispute_id=INR).one()
        case.data_source = DataSourceType.PAYPAL_SANDBOX.value
        db.commit()

    submitted = submit_tracking(client)
    assert submitted.status_code == 200
    check = _verify_result(client)
    assert check.status_code == 200, check.text
    assert "unavailable" in check.json()["message"].lower()

    upload = upload_pdf(client)
    assert upload.status_code == 200, upload.text
    after = detail(client)
    obs = nodes(after["evidence_graph"], "OBSERVATION")
    assert obs
    assert obs[-1]["content"]["status"] == "UNKNOWN"
    assert obs[-1]["content"]["verification_outcome"] == "UNAVAILABLE"
    assert obs[-1]["metadata"]["independently_verified"] is False
    assert obs[-1]["verification_status"] == "UNVERIFIED"
    assert obs[-1]["origin"] == "UNVERIFIED"
    assert obs[-1]["verified_at"] is None
    assert nodes(after["evidence_graph"], "SHIPMENT")[0]["verification_status"] == "UNVERIFIED"
    assert nodes(after["evidence_graph"], "EVIDENCE_ITEM")[0]["verification_status"] == "UNVERIFIED"
    assert after["readiness"]["is_decision_ready"] is False

    package = report(client)
    assert package["verified_facts"] == []
    assert package["simulated_facts"] == []
    assert any(p["verification_scope"] == "EXTERNAL_UNAVAILABLE" for p in package["evidence_provenance_trail"])
    assert package["missing_evidence_inventory"]
    assert package["recommended_adjudication_handoff"] == "CONTINUE_EVIDENCE_GATHERING"
    assert "No independently verified observations" in client.get(
        f"/api/v1/disputes/{INR}/report/markdown"
    ).text


def test_unknown_fixture_and_repeated_carrier_lookups_do_not_invent_delivery(client):
    assert detail(client)
    sub = submit_tracking(client, UNKNOWN_TRACKING)
    assert sub.status_code == 200
    for _ in range(2):
        assert _verify_result(client).status_code == 200
    after = detail(client)
    obs = nodes(after["evidence_graph"], "OBSERVATION")
    assert len(obs) == 2
    assert len({o["id"] for o in obs}) == 2
    assert all(o["content"]["status"] == "NOT_FOUND" for o in obs)
    assert all(o["metadata"]["verification_scope"] == "SIMULATED_FIXTURE" for o in obs)
    assert all(o["verification_status"] == "UNVERIFIED" for o in obs)
    assert all(o["verified_at"] is None for o in obs)
    assert after["readiness"]["is_decision_ready"] is False
    assert report(client)["verified_facts"] == []


def test_combined_upload_and_tracking_does_not_verify_claims_or_mask_unknowns(client):
    assert detail(client)
    response = client.post(
        f"/api/v1/disputes/{INR}/upload-evidence",
        data={
            "submitter_role": "MERCHANT",
            "tracking_number": MATCHING_TRACKING,
            "carrier_name": "USPS",
            "verify_carrier_now": "true",
        },
        files={"file": ("shipping.pdf", io.BytesIO(DOCUMENT), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["nodes_created"]) == 3  # doc, shipment and carrier observation
    case = detail(client)
    assert len(nodes(case["evidence_graph"], "OBSERVATION")) == 1
    assert len(nodes(case["evidence_graph"], "SHIPMENT")) == 1
    assert len(nodes(case["evidence_graph"], "EVIDENCE_ITEM")) == 1
    assert all(n["verification_status"] == "UNVERIFIED"
               for n in nodes(case["evidence_graph"], "EVIDENCE_ITEM"))
    assert report(client)["verified_facts"] == []
