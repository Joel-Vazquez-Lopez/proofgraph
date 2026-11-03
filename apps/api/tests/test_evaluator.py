import pytest
from packages.shared_schemas.models import (
    DisputeCategory,
    InvestigationState,
    NodeType,
    EdgeType,
    EvidenceVerificationStatus,
    EvidenceOrigin,
)
from app.services.evidence_graph import EvidenceGraph
from app.services.evaluator import DecisionReadinessEvaluator


def test_inr_missing_tracking_not_ready():
    graph = EvidenceGraph("INR-TEST-1")

    # Only transaction present
    graph.add_node(
        node_type=NodeType.TRANSACTION,
        label="TX-123",
        content={},
        source="PAYPAL",
        verification_status=EvidenceVerificationStatus.VERIFIED
    )
    graph.add_node(
        node_type=NodeType.ORDER,
        label="ORD-123",
        content={},
        source="MERCHANT",
        verification_status=EvidenceVerificationStatus.VERIFIED
    )

    eval_result = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    assert not eval_result.is_decision_ready
    assert eval_result.recommended_state == InvestigationState.INVESTIGATING
    assert any("Carrier" in m for m in eval_result.missing_requirements)


def test_inr_fulfilled_and_delivered_is_ready():
    """A linked, authoritative report can complete a no-buyer-claim handoff package."""
    graph = EvidenceGraph("INR-TEST-2")
    graph.add_node(
        NodeType.TRANSACTION, "TX-123",
        {"transaction_id": "TX-123"}, "PAYPAL",
        origin=EvidenceOrigin.VERIFIED_EXTERNAL,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    order = graph.add_node(
        NodeType.ORDER, "ORD-123",
        {"destination_address": {"postal_code": "97477"}},
        "MERCHANT", origin=EvidenceOrigin.USER_SUBMITTED,
    )
    shipment = graph.add_node(
        NodeType.SHIPMENT, "USPS #94001000",
        {"tracking_number": "94001000"}, "MERCHANT",
        origin=EvidenceOrigin.USER_SUBMITTED,
    )
    report = graph.add_node(
        NodeType.OBSERVATION, "Carrier Delivery Telemetry",
        {"status": "DELIVERED", "delivered_to_address": {"postal_code": "97477"}},
        "CARRIER_API_TELEMETRY", origin=EvidenceOrigin.VERIFIED_EXTERNAL,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    graph.add_edge(order.id, shipment.id, EdgeType.RELATES_TO, "order fulfillment")
    graph.add_edge(report.id, shipment.id, EdgeType.DERIVED_FROM, "linked carrier report")

    eval_result = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    assert eval_result.is_decision_ready
    assert eval_result.recommended_state == InvestigationState.DECISION_READY
    assert len(eval_result.missing_requirements) == 0


def test_unlinked_verified_label_alone_cannot_make_inr_ready():
    graph = EvidenceGraph("INR-OLD-ASSUMPTION")
    graph.add_node(NodeType.TRANSACTION, "TX", {}, "PAYPAL",
                   verification_status=EvidenceVerificationStatus.VERIFIED)
    graph.add_node(NodeType.ORDER, "order", {"destination_address": {"postal_code": "97477"}}, "MERCHANT")
    graph.add_node(NodeType.SHIPMENT, "shipment", {"tracking_number": "X"}, "MERCHANT")
    graph.add_node(NodeType.OBSERVATION, "Carrier says delivered",
                   {"status": "DELIVERED", "delivered_to_address": {"postal_code": "97477"}},
                   "CARRIER_GATEWAY", verification_status=EvidenceVerificationStatus.VERIFIED)
    assert not DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph).is_decision_ready


def test_inr_with_contradiction_escalates():
    graph = EvidenceGraph("INR-TEST-3")

    o = graph.add_node(NodeType.ORDER, "Order (ZIP 97201)", {"postal_code": "97201"}, "MERCHANT")
    s = graph.add_node(NodeType.SHIPMENT, "Shipment", {}, "MERCHANT")
    obs = graph.add_node(NodeType.OBSERVATION, "Delivered to ZIP 98101", {}, "CARRIER")
    tx = graph.add_node(NodeType.TRANSACTION, "TX", {}, "PAYPAL", verification_status=EvidenceVerificationStatus.VERIFIED)

    # Add contradiction edge
    graph.add_edge(obs.id, o.id, EdgeType.CONTRADICTS, "Destination ZIP mismatch")

    eval_result = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    assert not eval_result.is_decision_ready
    assert eval_result.requires_escalation
    assert eval_result.recommended_state == InvestigationState.REVIEW_REQUIRED
