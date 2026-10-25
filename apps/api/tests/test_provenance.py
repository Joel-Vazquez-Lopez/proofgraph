import pytest
from app.services.evidence_graph import EvidenceGraph
from app.services.carrier_service import CarrierVerificationService
from packages.shared_schemas.models import (
    NodeType,
    EdgeType,
    EvidenceOrigin,
    EvidenceVerificationStatus,
    DataSourceType,
)


def test_origin_and_verification_status_separation():
    """
    Proves that evidence origin is separate from verification status.
    A user-submitted document starts as USER_SUBMITTED and UNVERIFIED,
    and transitions to VERIFIED while preserving its original USER_SUBMITTED origin.
    """
    graph = EvidenceGraph(dispute_id="TEST-DISP-001")

    node = graph.add_node(
        node_type=NodeType.EVIDENCE_ITEM,
        label="Store Receipt",
        content={"amount": 45.00, "merchant": "Local Store"},
        source="BUYER_UPLOAD",
        origin=EvidenceOrigin.USER_SUBMITTED,
        verification_status=EvidenceVerificationStatus.UNVERIFIED,
    )
    assert node.origin == EvidenceOrigin.USER_SUBMITTED
    assert node.verification_status == EvidenceVerificationStatus.UNVERIFIED
    assert node.verified_at is None

    # Explicit verification transition event
    note = "Adjudicator confirmed store invoice matches transaction timestamp."
    verified_node = graph.verify_node(
        node_id=node.id,
        verifier_source="HUMAN_ADJUDICATOR_AUDIT",
        origin=EvidenceOrigin.USER_SUBMITTED,
        audit_note=note,
    )
    assert verified_node.origin == EvidenceOrigin.USER_SUBMITTED
    assert verified_node.verification_status == EvidenceVerificationStatus.VERIFIED
    assert verified_node.verified_at is not None

    # Audit trail is stored in verification_audit list
    audit_trail = verified_node.metadata.get("verification_audit", [])
    assert len(audit_trail) == 1
    assert audit_trail[0]["verifier_source"] == "HUMAN_ADJUDICATOR_AUDIT"
    assert note in audit_trail[0]["note"]


def test_tracking_alone_cannot_establish_verified_delivery():
    """
    Proves that a tracking number submitted by a party cannot establish delivery
    without an explicit, independent carrier verification event.
    """
    graph = EvidenceGraph(dispute_id="TEST-DISP-002")

    # Merchant submits tracking number — stays UNVERIFIED
    shipment_node = graph.add_node(
        node_type=NodeType.SHIPMENT,
        label="USPS #940010009999",
        content={"carrier_name": "USPS", "tracking_number": "940010009999"},
        source="MERCHANT_FULFILLMENT",
        origin=EvidenceOrigin.USER_SUBMITTED,
        verification_status=EvidenceVerificationStatus.UNVERIFIED,
    )

    # Invariant: No observation node exists yet; shipment is UNVERIFIED
    observations = graph.get_nodes_by_type(NodeType.OBSERVATION)
    assert len(observations) == 0
    assert shipment_node.verification_status == EvidenceVerificationStatus.UNVERIFIED

    # Independent carrier verification occurs (explicit event)
    carrier_result = CarrierVerificationService.verify_tracking(
        carrier_name="USPS",
        tracking_number="940010009999",
        case_data_source=DataSourceType.SYNTHETIC_FIXTURE,
    )
    # CarrierVerificationResult uses status field (not is_verified)
    assert carrier_result.status == "DELIVERED"
    assert carrier_result.is_synthetic is True
    assert carrier_result.origin == EvidenceOrigin.SYNTHETIC_FIXTURE

    # Observation added ONLY upon carrier verification event
    obs_node = graph.add_node(
        node_type=NodeType.OBSERVATION,
        label="Carrier Delivery Telemetry",
        content=carrier_result.model_dump(),
        source=carrier_result.verification_source,
        origin=carrier_result.origin,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    assert obs_node.verification_status == EvidenceVerificationStatus.VERIFIED
    assert obs_node.origin == EvidenceOrigin.SYNTHETIC_FIXTURE

    # Original shipment node origin unchanged
    assert shipment_node.origin == EvidenceOrigin.USER_SUBMITTED


def test_paypal_sandbox_cannot_silently_ingest_synthetic_carrier_fixtures():
    """
    Proves cross-environment safety: A dispute marked as PAYPAL_SANDBOX
    is prohibited from using synthetic demonstration fixtures.
    """
    carrier_result = CarrierVerificationService.verify_tracking(
        carrier_name="USPS",
        tracking_number="940010009999",
        case_data_source=DataSourceType.PAYPAL_SANDBOX,
    )
    # Must NOT claim a synthetic delivered status
    assert carrier_result.status == "UNKNOWN"
    assert carrier_result.is_synthetic is False
    assert carrier_result.origin == EvidenceOrigin.UNVERIFIED
    # Audit note documents the unconfigured carrier gateway
    assert "unconfigured" in carrier_result.audit_note.lower()
    assert "UNVERIFIED" in carrier_result.audit_note
