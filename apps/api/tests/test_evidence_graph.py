import pytest
from packages.shared_schemas.models import (
    NodeType,
    EdgeType,
    EvidenceVerificationStatus,
)
from app.services.evidence_graph import EvidenceGraph


def test_evidence_graph_nodes_and_edges():
    graph = EvidenceGraph(dispute_id="TEST-001")

    # Add transaction node
    tx_node = graph.add_node(
        node_type=NodeType.TRANSACTION,
        label="Transaction TX-123",
        content={"amount": 100.0, "currency": "USD"},
        source="PAYPAL_PAYMENTS",
        verification_status=EvidenceVerificationStatus.VERIFIED
    )
    assert graph.node_count == 1
    assert tx_node.type == NodeType.TRANSACTION

    # Add buyer claim node
    claim_node = graph.add_node(
        node_type=NodeType.CLAIM,
        label="Buyer Claim: Item Not Received",
        content={"party": "BUYER"},
        source="BUYER_CLAIM",
        verification_status=EvidenceVerificationStatus.UNVERIFIED
    )
    assert graph.node_count == 2

    # Add edge
    edge = graph.add_edge(
        source_id=claim_node.id,
        target_id=tx_node.id,
        edge_type=EdgeType.RELATES_TO,
        provenance="Claim relates to payment"
    )
    assert graph.edge_count == 1
    assert edge.type == EdgeType.RELATES_TO


def test_contradiction_detection():
    graph = EvidenceGraph(dispute_id="TEST-002")

    order_node = graph.add_node(
        node_type=NodeType.ORDER,
        label="Order ORD-1 (Portland, 97201)",
        content={"postal_code": "97201"},
        source="MERCHANT_ERP",
    )
    delivery_obs = graph.add_node(
        node_type=NodeType.OBSERVATION,
        label="Carrier Delivery (Seattle, 98101)",
        content={"postal_code": "98101"},
        source="CARRIER_API",
    )

    # Add contradiction edge
    graph.add_edge(
        source_id=delivery_obs.id,
        target_id=order_node.id,
        edge_type=EdgeType.CONTRADICTS,
        provenance="Delivered to different postal code"
    )

    contradictions = graph.get_contradictions()
    assert len(contradictions) == 1
    src, tgt, edge = contradictions[0]
    assert src.id == delivery_obs.id
    assert tgt.id == order_node.id


def test_open_questions_and_answering():
    graph = EvidenceGraph(dispute_id="TEST-003")

    q_node = graph.add_node(
        node_type=NodeType.QUESTION,
        label="Where is the carrier tracking number?",
        content={},
        source="INVESTIGATION_ENGINE",
    )

    assert len(graph.get_open_questions()) == 1

    # Answer the question with an evidence item
    ev_node = graph.add_node(
        node_type=NodeType.EVIDENCE_ITEM,
        label="USPS Tracking #94001000",
        content={},
        source="MERCHANT_UPLOAD",
    )
    graph.add_edge(
        source_id=ev_node.id,
        target_id=q_node.id,
        edge_type=EdgeType.ANSWERS,
        provenance="Merchant provided tracking number"
    )

    assert len(graph.get_open_questions()) == 0
