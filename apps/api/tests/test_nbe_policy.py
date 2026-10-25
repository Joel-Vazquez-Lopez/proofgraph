import pytest
from packages.shared_schemas.models import (
    DisputeCategory,
    NodeType,
    EdgeType,
    ActionType,
    EvidenceVerificationStatus,
)
from app.services.evidence_graph import EvidenceGraph
from app.services.evaluator import DecisionReadinessEvaluator
from app.services.nbe_policy import HeuristicNBEPolicy


def test_nbe_selects_tracking_when_missing():
    policy = HeuristicNBEPolicy()
    graph = EvidenceGraph("NBE-TEST-1")

    # Add transaction and order, but no shipment
    graph.add_node(NodeType.TRANSACTION, "TX", {}, "PAYPAL", verification_status=EvidenceVerificationStatus.VERIFIED)
    graph.add_node(NodeType.ORDER, "Order", {}, "MERCHANT", verification_status=EvidenceVerificationStatus.VERIFIED)

    readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    decision = policy.evaluate_candidates(DisputeCategory.ITEM_NOT_RECEIVED, graph, readiness)

    assert decision.chosen_action is not None
    assert decision.chosen_action.action_type == ActionType.REQUEST_MERCHANT_FULFILLMENT
    assert "Tracking" in decision.chosen_action.title
    assert decision.chosen_action.utility_score > 0.5


def test_nbe_prioritizes_automated_carrier_lookup_over_manual_outreach():
    policy = HeuristicNBEPolicy()
    graph = EvidenceGraph("NBE-TEST-2")

    # Has tracking number recorded, but no carrier delivery observation
    graph.add_node(NodeType.TRANSACTION, "TX", {}, "PAYPAL", verification_status=EvidenceVerificationStatus.VERIFIED)
    graph.add_node(NodeType.ORDER, "Order", {}, "MERCHANT", verification_status=EvidenceVerificationStatus.VERIFIED)
    graph.add_node(
        NodeType.SHIPMENT,
        "USPS Tracking #94001234",
        {"carrier_name": "USPS", "tracking_number": "94001234"},
        "MERCHANT",
        verification_status=EvidenceVerificationStatus.VERIFIED
    )

    readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    decision = policy.evaluate_candidates(DisputeCategory.ITEM_NOT_RECEIVED, graph, readiness)

    assert decision.chosen_action is not None
    # Because automated API lookup has lower friction than asking human, utility is higher
    assert decision.chosen_action.action_type == ActionType.CARRIER_TRACKING_LOOKUP
    assert decision.chosen_action.acquisition_friction < 0.5


def test_nbe_prioritizes_resolving_contradiction():
    policy = HeuristicNBEPolicy()
    graph = EvidenceGraph("NBE-TEST-3")

    o = graph.add_node(NodeType.ORDER, "Order (Portland, 97201)", {}, "MERCHANT")
    obs = graph.add_node(NodeType.OBSERVATION, "Delivered (Seattle, 98101)", {}, "CARRIER")
    graph.add_edge(obs.id, o.id, EdgeType.CONTRADICTS, "Destination mismatch")

    readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    decision = policy.evaluate_candidates(DisputeCategory.ITEM_NOT_RECEIVED, graph, readiness)

    assert decision.chosen_action is not None
    assert "Discrepancy" in decision.chosen_action.title or "Contradiction" in decision.chosen_action.rationale
