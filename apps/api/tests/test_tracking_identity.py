"""Evidence IDs must not collapse different carrier/tracking pairs."""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.db_models import Base, engine, init_db, SessionLocal, DisputeCaseDB


DISPUTE = "PP-D-INR-8841"
KNOWN_TRACKING = "940010009999"
OTHER_TRACKING = "222222229999"  # deliberately shares last 4 digits


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _submit(client, number, *, lookup=False, carrier="USPS"):
    return client.post(
        f"/api/v1/disputes/{DISPUTE}/evidence",
        json={
            "submitter_role": "MERCHANT",
            "carrier_name": carrier,
            "tracking_number": number,
            "verify_carrier_now": lookup,
        },
    )


def _nodes(client, kind):
    response = client.get(f"/api/v1/disputes/{DISPUTE}")
    assert response.status_code == 200
    return [
        node for node in response.json()["evidence_graph"]["nodes"]
        if node["type"] == kind
    ]


def test_different_tracking_numbers_with_same_suffix_create_distinct_shipments(client):
    assert _submit(client, KNOWN_TRACKING).status_code == 200
    assert _submit(client, OTHER_TRACKING).status_code == 200

    shipments = _nodes(client, "SHIPMENT")
    assert len(shipments) == 2
    assert len({node["id"] for node in shipments}) == 2
    assert {node["content"]["tracking_number"] for node in shipments} == {
        KNOWN_TRACKING, OTHER_TRACKING,
    }
    assert all(node["origin"] == "USER_SUBMITTED" for node in shipments)

    # Matching the same full carrier/tracking pair reuses its node.
    assert _submit(client, KNOWN_TRACKING, carrier="usps").status_code == 200
    assert len(_nodes(client, "SHIPMENT")) == 2


def test_observations_from_colliding_suffix_numbers_do_not_overwrite(client):
    assert _submit(client, KNOWN_TRACKING, lookup=True).status_code == 200
    assert _submit(client, OTHER_TRACKING, lookup=True).status_code == 200

    observations = _nodes(client, "OBSERVATION")
    assert len(observations) == 2
    assert len({n["id"] for n in observations}) == 2
    by_tracking = {n["content"]["tracking_number"]: n for n in observations}
    assert by_tracking[KNOWN_TRACKING]["content"]["status"] == "DELIVERED"
    assert by_tracking[OTHER_TRACKING]["content"]["status"] == "NOT_FOUND"

    # Another lookup of the SAME tracking number is a new auditable event.
    assert _submit(client, KNOWN_TRACKING, lookup=True).status_code == 200
    observations = _nodes(client, "OBSERVATION")
    assert len(observations) == 3
    assert len({n["id"] for n in observations}) == 3
    assert len([n for n in observations if n["content"]["tracking_number"] == KNOWN_TRACKING]) == 2


def test_legacy_shipment_id_is_reused_only_for_matching_full_tracking(client):
    assert client.get(f"/api/v1/disputes/{DISPUTE}").status_code == 200
    with SessionLocal() as db:
        case = db.query(DisputeCaseDB).filter_by(dispute_id=DISPUTE).one()
        graph = json.loads(case.graph_json)
        graph["nodes"].append({
            "id": "ship_usps_9999",  # old four-digit ID format
            "type": "SHIPMENT",
            "label": f"Legacy shipment {KNOWN_TRACKING}",
            "content": {"carrier_name": "USPS", "tracking_number": KNOWN_TRACKING},
            "source": "MERCHANT_SUBMISSION",
            "origin": "USER_SUBMITTED",
            "verification_status": "UNVERIFIED",
            "created_at": "2026-10-01T00:00:00+00:00",
        })
        graph["nodes"].append({
            "id": "obs_carrier_9999",  # old four-digit ID format
            "type": "OBSERVATION",
            "label": "Legacy carrier exception",
            "content": {
                "carrier_name": "USPS", "tracking_number": KNOWN_TRACKING,
                "status": "EXCEPTION",
            },
            "source": "SyntheticCarrierAdapter",
            "origin": "SYNTHETIC_FIXTURE",
            "verification_status": "VERIFIED",
            "created_at": "2026-10-01T00:00:00+00:00",
        })
        case.graph_json = json.dumps(graph)
        db.commit()

    assert _submit(client, KNOWN_TRACKING, lookup=True).status_code == 200
    ships = _nodes(client, "SHIPMENT")
    assert len(ships) == 1
    assert ships[0]["id"] == "ship_usps_9999"
    obs = _nodes(client, "OBSERVATION")
    assert len(obs) == 2
    assert {node["content"]["status"] for node in obs} == {"EXCEPTION", "DELIVERED"}
    assert any(node["id"] == "obs_carrier_9999" for node in obs)

    # Unrelated tracking with identical suffix must not reuse the old ID.
    assert _submit(client, OTHER_TRACKING).status_code == 200
    ships = _nodes(client, "SHIPMENT")
    assert len(ships) == 2
    assert len({node["id"] for node in ships}) == 2
    assert {node["content"]["tracking_number"] for node in ships} == {
        KNOWN_TRACKING, OTHER_TRACKING,
    }
