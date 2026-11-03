"""Carrier fixture truth must not masquerade as independent verification."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.db_models import Base, engine, init_db, SessionLocal, DisputeCaseDB
from app.services.carrier_service import CarrierVerificationService
from packages.shared_schemas.models import DataSourceType, EvidenceOrigin


CASE_ID = "PP-D-INR-8841"
TRACKING = "940010009999"


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _submit_tracking(client, *, verify_now=False):
    return client.post(
        f"/api/v1/disputes/{CASE_ID}/evidence",
        json={
            "submitter_role": "MERCHANT",
            "carrier_name": "USPS",
            "tracking_number": TRACKING,
            "verify_carrier_now": verify_now,
        },
    )


def _nodes(client, node_type):
    response = client.get(f"/api/v1/disputes/{CASE_ID}")
    assert response.status_code == 200
    detail = response.json()
    return [n for n in detail["evidence_graph"]["nodes"] if n["type"] == node_type], detail


def test_carrier_adapter_identifies_local_fixture_and_unknown_lookup():
    known = CarrierVerificationService.verify_tracking(
        "USPS", TRACKING, DataSourceType.SYNTHETIC_FIXTURE
    )
    assert known.status == "DELIVERED"
    assert known.verification_outcome == "SIMULATED"
    assert known.origin == EvidenceOrigin.SYNTHETIC_FIXTURE
    assert known.is_synthetic and not known.independently_verified
    assert "no external carrier contacted" in known.audit_note.lower()

    missing = CarrierVerificationService.verify_tracking(
        "USPS", "not-in-fixtures", DataSourceType.SYNTHETIC_FIXTURE
    )
    assert missing.status == "NOT_FOUND"
    assert missing.verification_outcome == "SIMULATED"
    assert missing.is_synthetic and not missing.independently_verified
    assert "fixture dataset" in missing.audit_note.lower()


@pytest.mark.parametrize(
    "source",
    [
        DataSourceType.PAYPAL_SANDBOX,
        DataSourceType.MERCHANT_ERP,
        DataSourceType.BUYER_SUBMISSION,
        DataSourceType.CARRIER_API,
    ],
)
def test_nonfixture_case_never_queries_synthetic_carrier(source):
    result = CarrierVerificationService.verify_tracking("USPS", TRACKING, source)
    assert result.status == "UNKNOWN"
    assert result.origin == EvidenceOrigin.UNVERIFIED
    assert result.verification_outcome == "UNAVAILABLE"
    assert not result.is_synthetic
    assert not result.independently_verified
    assert "no carrier api was contacted" in result.audit_note.lower()
    assert "unconfigured" in result.verification_source.lower()
    assert "live" not in result.verification_source.lower()


def test_fixture_lookup_does_not_verify_original_shipment_or_appear_as_verified_fact(client):
    assert _submit_tracking(client).status_code == 200
    response = client.post(f"/api/v1/disputes/{CASE_ID}/verify-carrier")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "simulated" in response.json()["message"].lower()
    assert "no independent external carrier verification" in response.json()["message"].lower()

    observations, detail = _nodes(client, "OBSERVATION")
    assert len(observations) == 1
    obs = observations[0]
    assert obs["origin"] == "SYNTHETIC_FIXTURE"
    assert obs["content"]["verification_outcome"] == "SIMULATED"
    assert obs["content"]["independently_verified"] is False
    assert obs["metadata"]["verification_scope"] == "SIMULATED_FIXTURE"
    assert obs["metadata"]["independently_verified"] is False
    assert obs["verification_status"] == "VERIFIED"  # demo scenario semantics, not external
    assert obs["verified_at"] is None
    assert "simulated" in obs["label"].lower()
    assert "no external carrier contacted" in obs["metadata"]["audit"].lower()

    shipments = [n for n in detail["evidence_graph"]["nodes"] if n["type"] == "SHIPMENT"]
    assert len(shipments) == 1
    shipment = shipments[0]
    assert shipment["origin"] == "USER_SUBMITTED"
    assert shipment["verification_status"] == "UNVERIFIED"
    assert shipment["verified_at"] is None
    assert shipment["metadata"]["simulated_crosschecks"][0]["external_verification"] is False

    assert detail["timeline"][-1]["actor"] == "SYNTHETIC_CARRIER_FIXTURE"
    assert "simulated" in detail["timeline"][-1]["action"].lower()
    assert response.json()["new_state"] == "INVESTIGATING"

    report_response = client.get(f"/api/v1/disputes/{CASE_ID}/report")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["verified_facts"] == []
    assert any("SIMULATED" in fact for fact in report["simulated_facts"])
    assert "simulated" in report["executive_summary"].lower()
    provenance = next(
        row for row in report["evidence_provenance_trail"]
        if row["node_id"] == obs["id"]
    )
    assert provenance["origin"] == "SYNTHETIC_FIXTURE"
    assert provenance["verification_scope"] == "SIMULATED_FIXTURE"
    assert provenance["independently_verified"] is False

    md = client.get(f"/api/v1/disputes/{CASE_ID}/report/markdown")
    assert md.status_code == 200
    assert "Simulated Demo Observations (NOT Externally Verified)" in md.text
    assert "No independently verified observations" in md.text
    assert "SIMULATED_FIXTURE" in md.text


def test_immediate_fixture_lookup_message_is_explicitly_simulated(client):
    response = _submit_tracking(client, verify_now=True)
    assert response.status_code == 200
    assert "evidence ingested" in response.json()["message"].lower()
    assert "simulated carrier fixture" in response.json()["message"].lower()
    observations, _ = _nodes(client, "OBSERVATION")
    assert observations[0]["metadata"]["verification_scope"] == "SIMULATED_FIXTURE"


def test_unavailable_gateway_is_not_a_successful_carrier_verification(client):
    # Seed synthetic cases first, then change just the test case's source to
    # simulate a nonfixture dispute without calling any real PayPal endpoint.
    assert client.get(f"/api/v1/disputes/{CASE_ID}").status_code == 200
    with SessionLocal() as db:
        case = db.query(DisputeCaseDB).filter_by(dispute_id=CASE_ID).one()
        case.data_source = DataSourceType.PAYPAL_SANDBOX.value
        db.commit()

    assert _submit_tracking(client).status_code == 200
    response = client.post(f"/api/v1/disputes/{CASE_ID}/verify-carrier")
    assert response.status_code == 200
    assert response.json()["success"] is True  # operation recorded, NOT verification success
    assert "verification unavailable" in response.json()["message"].lower()
    assert "no external carrier gateway" in response.json()["message"].lower()

    observations, detail = _nodes(client, "OBSERVATION")
    assert len(observations) == 1
    obs = observations[0]
    assert obs["content"]["status"] == "UNKNOWN"
    assert obs["content"]["verification_outcome"] == "UNAVAILABLE"
    assert obs["origin"] == "UNVERIFIED"
    assert obs["verification_status"] == "UNVERIFIED"
    assert obs["verified_at"] is None
    assert obs["metadata"]["verification_scope"] == "EXTERNAL_UNAVAILABLE"
    assert obs["metadata"]["independently_verified"] is False
    assert "unconfigured" in obs["source"].lower()
    assert detail["timeline"][-1]["actor"] == "CARRIER_GATEWAY"
    assert "unavailable" in detail["timeline"][-1]["action"].lower()

    report_response = client.get(f"/api/v1/disputes/{CASE_ID}/report")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["verified_facts"] == []
    assert report["simulated_facts"] == []
