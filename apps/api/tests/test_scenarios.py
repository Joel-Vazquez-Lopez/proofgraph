import pytest
from app.services.evidence_graph import EvidenceGraph
from app.services.evaluator import DecisionReadinessEvaluator
from app.services.nbe_policy import HeuristicNBEPolicy
from packages.shared_schemas.models import (
    DisputeCategory,
    InvestigationState,
    NodeType,
    EdgeType,
    ActionType,
    EvidenceOrigin,
    EvidenceVerificationStatus,
)


def _build_base_inr_graph(dispute_id: str = "CASE-TEST"):
    """Build a base ITEM_NOT_RECEIVED evidence graph with dispute, transaction, order, and buyer claim."""
    graph = EvidenceGraph(dispute_id=dispute_id)

    root = graph.add_node(
        node_type=NodeType.DISPUTE,
        label=f"Dispute {dispute_id}",
        content={"dispute_id": dispute_id, "amount": 200.0, "currency": "USD"},
        source="PAYPAL_API",
        origin=EvidenceOrigin.VERIFIED_EXTERNAL,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    tx = graph.add_node(
        node_type=NodeType.TRANSACTION,
        label="Transaction 12345",
        content={"transaction_id": "TX-12345", "amount": 200.0, "currency": "USD"},
        source="PAYPAL_PAYMENTS",
        origin=EvidenceOrigin.VERIFIED_EXTERNAL,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    order = graph.add_node(
        node_type=NodeType.ORDER,
        label="Order ORD-99",
        content={
            "order_id": "ORD-99",
            "destination_address": {"city": "Springfield", "state": "OR", "postal_code": "97477"}
        },
        source="MERCHANT_ERP",
        origin=EvidenceOrigin.USER_SUBMITTED,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    claim = graph.add_node(
        node_type=NodeType.CLAIM,
        label="Buyer Claim: Item Not Received",
        content={"text": "I never received my package at my home.", "party": "BUYER"},
        source="BUYER_CLAIM",
        origin=EvidenceOrigin.USER_SUBMITTED,
        verification_status=EvidenceVerificationStatus.UNVERIFIED,
    )

    graph.add_edge(root.id, tx.id, EdgeType.REFERENCES, "Dispute references transaction.")
    graph.add_edge(tx.id, order.id, EdgeType.REFERENCES, "Payment settled for order.")
    graph.add_edge(root.id, claim.id, EdgeType.RELATES_TO, "Dispute contains buyer claim.")

    return graph, root, tx, order, claim


def test_scenario_a_confirmed_delivery_preserves_unresolved_claim():
    """
    Scenario A: Carrier indicates delivery to correct ZIP, buyer reports non-receipt.
    Invariant: The investigator identifies an unresolved delivery question (e.g. signature/photo),
    rather than automatically dismissing the buyer's claim.
    """
    graph, root, tx, order, claim = _build_base_inr_graph("CASE-SCENARIO-A")

    ship = graph.add_node(
        node_type=NodeType.SHIPMENT,
        label="USPS #940010009999",
        content={"carrier_name": "USPS", "tracking_number": "940010009999"},
        source="MERCHANT_FULFILLMENT",
        origin=EvidenceOrigin.USER_SUBMITTED,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    graph.add_edge(order.id, ship.id, EdgeType.RELATES_TO, "Order fulfilled via shipment.")

    # Carrier reports DELIVERED to correct ZIP — but no signature obtained
    obs = graph.add_node(
        node_type=NodeType.OBSERVATION,
        label="USPS Delivered to 97477",
        content={
            "status": "DELIVERED",
            "has_signature": False,
            "delivered_to_address": {"city": "Springfield", "state": "OR", "postal_code": "97477"}
        },
        source="USPS_CARRIER_GATEWAY",
        origin=EvidenceOrigin.VERIFIED_EXTERNAL,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    graph.add_edge(obs.id, ship.id, EdgeType.DERIVED_FROM, "Carrier telemetry derived from tracking.")

    readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    policy = HeuristicNBEPolicy()
    decision = policy.evaluate_candidates(DisputeCategory.ITEM_NOT_RECEIVED, graph, readiness)

    # The case satisfies delivery check, but buyer non-receipt means there's an open delivery question
    # Evaluator notes no signature as acknowledged — satisfies delivery record
    assert "front-door drop" in " ".join(readiness.satisfied_requirements).lower() or \
           "verified delivery" in " ".join(readiness.satisfied_requirements).lower()

    # Policy recommends requesting signature/proof of delivery — not blindly closing the case
    assert decision.chosen_action is not None
    assert decision.chosen_action.action_type == ActionType.REQUEST_PROOF_OF_DELIVERY
    assert "signature" in decision.chosen_action.title.lower() or \
           "proof" in decision.chosen_action.title.lower()


def test_scenario_b_no_delivery_in_transit():
    """
    Scenario B: Carrier indicates shipment is in-transit / undelivered.
    Invariant: Case is not decision-ready; policy recommends monitoring carrier telemetry.
    """
    graph, root, tx, order, claim = _build_base_inr_graph("CASE-SCENARIO-B")

    ship = graph.add_node(
        node_type=NodeType.SHIPMENT,
        label="UPS #1Z9999999988776655",
        content={"carrier_name": "UPS", "tracking_number": "1Z9999999988776655"},
        source="MERCHANT_FULFILLMENT",
        origin=EvidenceOrigin.USER_SUBMITTED,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    graph.add_edge(order.id, ship.id, EdgeType.RELATES_TO, "Order fulfilled via shipment.")

    # Carrier scan shows IN_TRANSIT
    obs = graph.add_node(
        node_type=NodeType.OBSERVATION,
        label="UPS Status: In Transit",
        content={"status": "IN_TRANSIT", "location": "Chicago IL"},
        source="UPS_CARRIER_GATEWAY",
        origin=EvidenceOrigin.VERIFIED_EXTERNAL,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    graph.add_edge(obs.id, ship.id, EdgeType.DERIVED_FROM, "Carrier telemetry derived from tracking.")

    readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    policy = HeuristicNBEPolicy()
    decision = policy.evaluate_candidates(DisputeCategory.ITEM_NOT_RECEIVED, graph, readiness)

    # Invariant: Not decision-ready because delivery has not been completed
    assert readiness.is_decision_ready is False
    assert readiness.recommended_state == InvestigationState.INVESTIGATING
    assert any("in-transit" in req.lower() or "in_transit" in req.lower() for req in readiness.missing_requirements)

    # Policy recommends monitoring carrier telemetry for this in-transit shipment
    assert decision.chosen_action is not None
    assert decision.chosen_action.action_type == ActionType.CARRIER_STATUS_MONITOR


def test_scenario_c_unknown_delivery_unverified_tracking():
    """
    Scenario C: Tracking number submitted, but no independent carrier info available.
    Invariant: Investigator preserves uncertainty and requests carrier lookup or drop-off receipt.
    """
    graph, root, tx, order, claim = _build_base_inr_graph("CASE-SCENARIO-C")

    # Unverified shipment — no carrier observation
    ship = graph.add_node(
        node_type=NodeType.SHIPMENT,
        label="FedEx #999999999999",
        content={"carrier_name": "FedEx", "tracking_number": "999999999999"},
        source="MERCHANT_SUBMISSION",
        origin=EvidenceOrigin.USER_SUBMITTED,
        verification_status=EvidenceVerificationStatus.UNVERIFIED,
    )
    graph.add_edge(order.id, ship.id, EdgeType.RELATES_TO, "Order fulfilled via shipment.")

    readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    policy = HeuristicNBEPolicy()
    decision = policy.evaluate_candidates(DisputeCategory.ITEM_NOT_RECEIVED, graph, readiness)

    # Invariant: Preserves uncertainty; case is not decision-ready
    assert readiness.is_decision_ready is False
    assert any("carrier" in req.lower() or "telemetry" in req.lower() for req in readiness.missing_requirements)

    # Policy recommends carrier lookup to verify tracking
    assert decision.chosen_action is not None
    assert decision.chosen_action.action_type in (
        ActionType.CARRIER_TRACKING_LOOKUP,
        ActionType.REQUEST_PROOF_OF_DELIVERY,
    )


def test_scenario_d_contradictory_evidence_address_mismatch():
    """
    Scenario D: Carrier delivered to Seattle 98101, buyer order specifies Portland 97201.
    Invariant: Contradiction prevents DECISION_READY; policy targets resolving the discrepancy.
    """
    graph, root, tx, order, claim = _build_base_inr_graph("CASE-SCENARIO-D")

    # Update the order to reflect Portland destination
    order.content["destination_address"]["city"] = "Portland"
    order.content["destination_address"]["state"] = "OR"
    order.content["destination_address"]["postal_code"] = "97201"

    ship = graph.add_node(
        node_type=NodeType.SHIPMENT,
        label="UPS #1Z9999999912345678",
        content={"carrier_name": "UPS", "tracking_number": "1Z9999999912345678"},
        source="MERCHANT_FULFILLMENT",
        origin=EvidenceOrigin.USER_SUBMITTED,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    graph.add_edge(order.id, ship.id, EdgeType.RELATES_TO, "Order fulfilled via shipment.")

    obs = graph.add_node(
        node_type=NodeType.OBSERVATION,
        label="UPS Delivered to Seattle 98101",
        content={
            "status": "DELIVERED",
            "delivered_to_address": {"city": "Seattle", "state": "WA", "postal_code": "98101"}
        },
        source="UPS_CARRIER_GATEWAY",
        origin=EvidenceOrigin.VERIFIED_EXTERNAL,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    graph.add_edge(obs.id, ship.id, EdgeType.DERIVED_FROM, "Carrier telemetry derived from tracking.")

    # Contradiction edge: carrier delivered to wrong ZIP
    graph.add_edge(
        obs.id,
        order.id,
        EdgeType.CONTRADICTS,
        "Carrier delivered to ZIP 98101, but buyer order specified ZIP 97201."
    )

    readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    policy = HeuristicNBEPolicy()
    decision = policy.evaluate_candidates(DisputeCategory.ITEM_NOT_RECEIVED, graph, readiness)

    # Invariant: Contradiction drives REVIEW_REQUIRED and blocks DECISION_READY
    assert readiness.is_decision_ready is False
    assert len(readiness.active_contradictions) > 0
    assert readiness.recommended_state == InvestigationState.REVIEW_REQUIRED

    # Policy targets contradiction resolution
    assert decision.chosen_action is not None
    assert decision.chosen_action.action_type == ActionType.REQUEST_BUYER_CLARIFICATION
    assert "discrepancy" in decision.chosen_action.title.lower() or \
           "contradict" in decision.chosen_action.title.lower() or \
           "resolve" in decision.chosen_action.title.lower()


def test_scenario_e_insufficient_evidence_loop_prevention():
    """
    Scenario E: Necessary information unavailable.
    Invariant: After exhausting actionable paths, investigator escalates to human review
    and does not loop on repeated identical evidence requests.
    """
    graph, root, tx, order, claim = _build_base_inr_graph("CASE-SCENARIO-E")

    # No shipment node — merchant hasn't provided tracking
    # Simulate that act_merchant_tracking was already requested via QUESTION node in graph
    graph.add_node(
        node_type=NodeType.QUESTION,
        label="Request Carrier Tracking Number",
        content={"action": {"action_id": "act_merchant_tracking"}},
        source="INVESTIGATION_ENGINE",
        origin=EvidenceOrigin.MODEL_INFERENCE,
        verification_status=EvidenceVerificationStatus.UNVERIFIED,
        node_id="q_act_merchant_tracking",
    )

    readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, graph)
    policy = HeuristicNBEPolicy()
    decision = policy.evaluate_candidates(DisputeCategory.ITEM_NOT_RECEIVED, graph, readiness)

    # Invariant: Does not loop by repeating act_merchant_tracking — instead escalates to human review
    assert decision.chosen_action is not None
    assert decision.chosen_action.action_type == ActionType.ESCALATE_HUMAN_REVIEW
    assert "human" in decision.chosen_action.title.lower()
