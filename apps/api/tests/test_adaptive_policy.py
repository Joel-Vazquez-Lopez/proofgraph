"""Adaptive policy contract, provenance and graph-update regression tests."""
import pytest

from app.services.evidence_graph import EvidenceGraph
from app.services.evaluator import DecisionReadinessEvaluator
from app.services.nbe_adaptive import HypothesisDiscriminationPolicy
from app.services.nbe_policy import HeuristicNBEPolicy
from packages.shared_schemas.models import (
    DisputeCategory, EdgeType, EvidenceOrigin, EvidenceVerificationStatus,
    NodeType, ActionType,
)

INR = DisputeCategory.ITEM_NOT_RECEIVED


def case(shipment=True, buyer=True, zip_code="10001"):
    graph = EvidenceGraph("DYNAMIC-INR")
    order = graph.add_node(NodeType.ORDER, "Purchased destination",
                           {"destination_address": {"postal_code": zip_code}},
                           "MERCHANT", node_id="order_case")
    ship = None
    if shipment:
        ship = graph.add_node(NodeType.SHIPMENT, "Tracking",
                              {"tracking_number": "Q123", "carrier_name": "USPS"},
                              "MERCHANT", node_id="shipment_case")
        graph.add_edge(order.id, ship.id, EdgeType.RELATES_TO, "order shipped")
    if buyer:
        graph.add_node(NodeType.CLAIM, "Buyer reports nonreceipt",
                       {"party": "BUYER"}, "BUYER", node_id="buyer_claim")
    return graph, order, ship


def scan(graph, shipment, name, status="DELIVERED", zip_code="10001",
         origin=EvidenceOrigin.VERIFIED_EXTERNAL, verified=True):
    observation = graph.add_node(
        NodeType.OBSERVATION, name,
        {"status": status, "delivered_to_address": {"postal_code": zip_code}},
        "CARRIER_GATEWAY", node_id=name, origin=origin,
        verification_status=(EvidenceVerificationStatus.VERIFIED if verified
                             else EvidenceVerificationStatus.UNVERIFIED),
    )
    graph.add_edge(observation.id, shipment.id, EdgeType.DERIVED_FROM, "tracking observation")
    return observation


def attempted(graph, action_id):
    graph.add_node(NodeType.QUESTION, "Previous attempt",
                   {"action": {"action_id": action_id}, "attempt_status": "COMPLETED"},
                   "INVESTIGATOR", node_id="q_" + action_id)


def recommendation(graph, availability=None, policy=None):
    ready = DecisionReadinessEvaluator.evaluate(INR, graph)
    engine = policy or HypothesisDiscriminationPolicy(availability=availability)
    return engine.evaluate_candidates(INR, graph, ready)


@pytest.mark.parametrize("postal,expected", [
    ("10001", "act_request_signature_or_proof"),
    ("94105", "act_resolve_contradiction"),
])
def test_delivery_location_changes_recommendation(postal, expected):
    graph, order, shipment = case()
    record = scan(graph, shipment, "carrier_report_1", zip_code=postal)
    decision = recommendation(graph)
    assert decision.chosen_action.action_id == expected
    assert record.id in decision.chosen_action.rationale
    assert order.id in decision.chosen_action.rationale or postal == "10001"
    assert "carrier_delivered" in decision.chosen_action.rationale
    assert decision.chosen_action.expected_information_gain == 0.0


def test_conflicting_scans_without_explicit_contradiction_edge_are_caught():
    graph, _, shipment = case()
    scan(graph, shipment, "report_right", zip_code="10001")
    scan(graph, shipment, "report_wrong", zip_code="94105")
    decision = recommendation(graph)
    assert decision.chosen_action.action_id == "act_resolve_contradiction"
    assert "report_right" in decision.chosen_action.rationale
    assert "report_wrong" in decision.chosen_action.rationale
    assert recommendation(graph, policy=HeuristicNBEPolicy()).chosen_action.action_id != "act_resolve_contradiction"


def test_submitted_verified_scan_does_not_count_as_carrier_proof():
    graph, _, shipment = case()
    scan(graph, shipment, "seller_says_delivered", origin=EvidenceOrigin.USER_SUBMITTED)
    decision = recommendation(graph)
    assert decision.chosen_action.action_id == "act_carrier_lookup"
    assert "Evidence basis: NONE" in decision.chosen_action.rationale
    assert recommendation(graph, policy=HeuristicNBEPolicy()).chosen_action.action_id != "act_carrier_lookup"


def test_unavailable_lookup_falls_back_to_merchant_document():
    graph, _, shipment = case()
    decision = recommendation(graph, availability={"act_carrier_lookup": False})
    assert decision.chosen_action.action_id == "act_request_carrier_receipt"
    assert all(c.action_id != "act_carrier_lookup" for c in decision.all_candidates)


def test_escalation_after_exhaustion_no_repeat():
    graph, _, shipment = case()
    attempted(graph, "act_carrier_lookup")
    attempted(graph, "act_request_carrier_receipt")
    decision = recommendation(graph)
    assert decision.chosen_action.action_type == ActionType.ESCALATE_HUMAN_REVIEW
    assert len(decision.all_candidates) == 1
    assert "ABSTAIN" in decision.selection_rationale


def test_conflict_chooses_alternative_after_previous_clarification():
    graph, _, shipment = case()
    scan(graph, shipment, "r1", zip_code="10001")
    scan(graph, shipment, "r2", zip_code="94105")
    attempted(graph, "act_resolve_contradiction")
    decision = recommendation(graph)
    assert decision.chosen_action.action_id == "act_request_carrier_receipt"
    attempted(graph, "act_request_carrier_receipt")
    assert recommendation(graph).chosen_action.action_type == ActionType.ESCALATE_HUMAN_REVIEW


def test_new_evidence_recomputes_different_steps_and_preserves_trace():
    graph, order, shipment = case(shipment=False)
    sequence = []
    first = recommendation(graph)
    sequence.append(first.chosen_action.action_id)
    assert sequence[-1] == "act_merchant_tracking"

    shipment = graph.add_node(NodeType.SHIPMENT, "Merchant submitted tracking",
                              {"tracking_number": "Q123"}, "MERCHANT",
                              origin=EvidenceOrigin.USER_SUBMITTED)
    graph.add_edge(order.id, shipment.id, EdgeType.RELATES_TO, "fulfillment")
    attempted(graph, "act_merchant_tracking")
    second = recommendation(graph)
    sequence.append(second.chosen_action.action_id)
    assert sequence[-1] == "act_carrier_lookup"

    delivered = scan(graph, shipment, "carrier_report", zip_code="10001")
    attempted(graph, "act_carrier_lookup")
    third = recommendation(graph)
    sequence.append(third.chosen_action.action_id)
    assert sequence[-1] == "act_request_signature_or_proof"
    assert delivered.id in third.chosen_action.rationale
    assert sequence == [
        "act_merchant_tracking", "act_carrier_lookup",
        "act_request_signature_or_proof"
    ]


def test_qualifying_handoff_record_only_when_linked_and_verified():
    graph, _, shipment = case()
    scan(graph, shipment, "carrier_report")
    upload = graph.add_node(
        NodeType.EVIDENCE_ITEM, "A random image", {"kind": "delivery_photo"},
        "BUYER", origin=EvidenceOrigin.USER_SUBMITTED,
        verification_status=EvidenceVerificationStatus.VERIFIED
    )
    graph.add_edge(upload.id, shipment.id, EdgeType.RELATES_TO, "submitted file")
    assert recommendation(graph).chosen_action.action_id == "act_request_signature_or_proof"

    trusted = graph.add_node(
        NodeType.EVIDENCE_ITEM, "Carrier signed handoff", {"kind": "signature_record"},
        "CARRIER", origin=EvidenceOrigin.VERIFIED_EXTERNAL,
        verification_status=EvidenceVerificationStatus.VERIFIED
    )
    graph.add_edge(trusted.id, shipment.id, EdgeType.RELATES_TO, "linked carrier handoff")
    # Existing readiness evaluator may still be missing other requirements.
    # The new policy does NOT treat the uploaded image as proof.
    assert recommendation(graph).chosen_action.action_id != "act_request_signature_or_proof"


def test_multiple_shipments_abstains():
    graph, _, shipment = case()
    scan(graph, shipment, "carrier_report")
    graph.add_node(NodeType.SHIPMENT, "Another shipment", {}, "MERCHANT")
    assert recommendation(graph).chosen_action.action_type == ActionType.ESCALATE_HUMAN_REVIEW


def test_transit_status_prefers_supported_explicit_carrier_recheck():
    graph, _, shipment = case()
    scan(graph, shipment, "transit_report", status="IN_TRANSIT")
    assert recommendation(graph).chosen_action.action_id == "act_carrier_lookup"
    attempted(graph, "act_carrier_lookup")
    assert recommendation(graph).chosen_action.action_type == ActionType.ESCALATE_HUMAN_REVIEW


def test_readiness_flag_cannot_hide_unlinked_report_conflict_from_policy():
    graph, _, shipment = case()
    scan(graph, shipment, "first", zip_code="10001")
    scan(graph, shipment, "second", zip_code="94105")
    readiness = DecisionReadinessEvaluator.evaluate(INR, graph)
    readiness.is_decision_ready = True  # read-only policy must still detect conflict
    decision = HypothesisDiscriminationPolicy().evaluate_candidates(INR, graph, readiness)
    assert decision.chosen_action.action_id == "act_resolve_contradiction"


def test_unsupported_category_delegates_to_baseline():
    graph, _, _ = case()
    ready = DecisionReadinessEvaluator.evaluate(DisputeCategory.DUPLICATE_TRANSACTION, graph)
    actual = HypothesisDiscriminationPolicy().evaluate_candidates(
        DisputeCategory.DUPLICATE_TRANSACTION, graph, ready
    )
    assert actual.policy_name == "HeuristicNBEPolicy"
