#!/usr/bin/env python3
"""Executable graph → hypotheses → action → new evidence → reassessment demo.

All observations below are EXPLICIT SYNTHETIC FIXTURES. This demonstration does
not query a real carrier, verify a real signature, or adjudicate a dispute.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.evidence_graph import EvidenceGraph
from app.services.evaluator import DecisionReadinessEvaluator
from app.services.nbe_adaptive import HypothesisDiscriminationPolicy
from packages.shared_schemas.models import (
    DisputeCategory, EdgeType, EvidenceOrigin, EvidenceVerificationStatus,
    NodeType,
)


def run_demo(verbose=True):
    category = DisputeCategory.ITEM_NOT_RECEIVED
    graph = EvidenceGraph("DEMO-INR")
    graph.add_node(
        NodeType.TRANSACTION, "Synthetic PayPal transaction",
        {"amount": 50, "currency": "USD"}, "SIMULATED_PAYPAL",
        node_id="tx_demo", origin=EvidenceOrigin.SYNTHETIC_FIXTURE,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    order = graph.add_node(
        NodeType.ORDER, "Synthetic order destination",
        {"destination_address": {"postal_code": "13579"}},
        "SIMULATED_MERCHANT", node_id="order_demo",
        origin=EvidenceOrigin.SYNTHETIC_FIXTURE,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    graph.add_node(
        NodeType.CLAIM, "Buyer denies receipt",
        {"party": "BUYER"}, "BUYER", node_id="claim_demo",
        origin=EvidenceOrigin.USER_SUBMITTED,
        verification_status=EvidenceVerificationStatus.UNVERIFIED,
    )
    policy = HypothesisDiscriminationPolicy()
    history = []

    def snapshot():
        readiness = DecisionReadinessEvaluator.evaluate(category, graph)
        decision = policy.evaluate_candidates(category, graph, readiness)
        action = decision.chosen_action.action_id if decision.chosen_action else None
        history.append((action, readiness.is_decision_ready))
        if verbose:
            print(f"Graph {graph.node_count} nodes: action={action}, ready={readiness.is_decision_ready}")
            print(" ", decision.selection_rationale)
        return action

    def record(action):
        graph.add_node(
            NodeType.QUESTION, f"Previously issued action {action}",
            {"action": {"action_id": action}}, "INVESTIGATION_ENGINE",
            node_id=f"q_{action}", origin=EvidenceOrigin.MODEL_INFERENCE,
        )

    assert snapshot() == "act_merchant_tracking"
    record("act_merchant_tracking")
    shipment = graph.add_node(
        NodeType.SHIPMENT, "Merchant submitted tracking",
        {"tracking_number": "SIM-98765", "carrier_name": "SIM_CARRIER"},
        "MERCHANT", node_id="shipment_demo",
        origin=EvidenceOrigin.USER_SUBMITTED,
    )
    graph.add_edge(order.id, shipment.id, EdgeType.RELATES_TO, "merchant submitted tracking")

    assert snapshot() == "act_carrier_lookup"
    record("act_carrier_lookup")
    observation = graph.add_node(
        NodeType.OBSERVATION, "Simulated carrier: delivered without signature",
        {"status": "DELIVERED", "delivered_to_address": {"postal_code": "13579"},
         "has_signature": False},
        "SIMULATED_CARRIER", node_id="scan_demo",
        origin=EvidenceOrigin.SYNTHETIC_FIXTURE,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    graph.add_edge(observation.id, shipment.id, EdgeType.DERIVED_FROM,
                   "simulated carrier observation")

    assert snapshot() == "act_request_signature_or_proof"
    record("act_request_signature_or_proof")
    handoff = graph.add_node(
        NodeType.EVIDENCE_ITEM, "Synthetic Signature Delivery Record",
        {"kind": "signature_record"},
        "SIMULATED_CARRIER", node_id="signature_demo",
        origin=EvidenceOrigin.SYNTHETIC_FIXTURE,
        verification_status=EvidenceVerificationStatus.VERIFIED,
    )
    graph.add_edge(handoff.id, shipment.id, EdgeType.RELATES_TO, "synthetic signed handoff")

    assert snapshot() is None
    assert history[-1][1] is True  # current evaluator's simulated handoff criteria
    assert [s[0] for s in history] == [
        "act_merchant_tracking",
        "act_carrier_lookup",
        "act_request_signature_or_proof",
        None,
    ]
    if verbose:
        print("Simulated case package is READY FOR HUMAN HANDOFF, not adjudicated.")
    return history


if __name__ == "__main__":
    run_demo()
