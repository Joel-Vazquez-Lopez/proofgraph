"""Contract-level tests for qualitative hypothesis assessment.

Independent cases vary provenance, contradictory observations, linking and missingness.
No probability calibration or dispute adjudication is asserted.
"""
import pytest

from app.services.evidence_graph import EvidenceGraph
from app.services.hypothesis_engine import assess_inr_hypotheses
from app.services.evaluator import DecisionReadinessEvaluator
from app.services.nbe_policy import HeuristicNBEPolicy
from packages.shared_schemas.models import (
    ActionType, DisputeCategory, EdgeType, EvidenceOrigin,
    EvidenceVerificationStatus, NodeType,
)


def _case(order_zip="02139", with_buyer=True):
    g = EvidenceGraph("HYP-TEST")
    o = g.add_node(NodeType.ORDER, "Order", {
        "destination_address": {"postal_code": order_zip}
    }, "MERCHANT", origin=EvidenceOrigin.USER_SUBMITTED)
    s = g.add_node(NodeType.SHIPMENT, "Tracking", {"tracking_number": "X1"},
                   "MERCHANT", origin=EvidenceOrigin.USER_SUBMITTED)
    if with_buyer:
        g.add_node(NodeType.CLAIM, "Buyer nonreceipt", {"party": "BUYER"},
                   "BUYER", origin=EvidenceOrigin.USER_SUBMITTED)
    return g, o, s


def _scan(g, shipment, status="DELIVERED", delivered_zip="02139",
          origin=EvidenceOrigin.VERIFIED_EXTERNAL,
          verification=EvidenceVerificationStatus.VERIFIED, linked=True):
    obs = g.add_node(
        NodeType.OBSERVATION, "Carrier scan",
        {"status": status, "delivered_to_address": {"postal_code": delivered_zip}},
        "CARRIER_GATEWAY", origin=origin, verification_status=verification,
    )
    if linked:
        g.add_edge(obs.id, shipment.id, EdgeType.DERIVED_FROM,
                   "Carrier observation for shipment")
    return obs


def _by_id(review):
    return {a.hypothesis_id: a for a in review.assessments}


def test_external_matching_scan_supports_delivery_report_but_not_buyer_receipt():
    g, _, shipment = _case()
    scan = _scan(g, shipment)
    review = assess_inr_hypotheses(g)
    h = _by_id(review)
    assert review.evidence_basis == "EXTERNAL"
    assert h["carrier_delivered_to_order_postal_code"].status == "SUPPORTED"
    assert h["carrier_delivered_to_order_postal_code"].supporting_evidence_ids == (scan.id,)
    assert h["carrier_delivered_to_other_postal_code"].status == "CONTRADICTED"
    assert review.suggested_action_id == "act_request_signature_or_proof"
    assert "does not establish receipt" in review.rationale


def test_wrong_address_changes_support_and_action():
    g, _, shipment = _case("60614")
    scan = _scan(g, shipment, delivered_zip="94110")
    review = assess_inr_hypotheses(g)
    h = _by_id(review)
    assert h["carrier_delivered_to_other_postal_code"].status == "SUPPORTED"
    assert h["carrier_delivered_to_other_postal_code"].supporting_evidence_ids == (scan.id,)
    assert h["carrier_delivered_to_order_postal_code"].status == "CONTRADICTED"
    assert review.suggested_action_id == "act_resolve_contradiction"


def test_simulated_verified_scan_is_not_presented_as_independent():
    g, _, shipment = _case()
    _scan(g, shipment, origin=EvidenceOrigin.SYNTHETIC_FIXTURE)
    review = assess_inr_hypotheses(g)
    assert review.evidence_basis == "SIMULATED"
    assert _by_id(review)["carrier_delivered_to_order_postal_code"].status == "SUPPORTED"
    assert "synthetic fixtures" in review.rationale


@pytest.mark.parametrize("origin,verification,linked", [
    (EvidenceOrigin.USER_SUBMITTED, EvidenceVerificationStatus.VERIFIED, True),
    (EvidenceOrigin.MODEL_INFERENCE, EvidenceVerificationStatus.VERIFIED, True),
    (EvidenceOrigin.VERIFIED_EXTERNAL, EvidenceVerificationStatus.UNVERIFIED, True),
    (EvidenceOrigin.VERIFIED_EXTERNAL, EvidenceVerificationStatus.VERIFIED, False),
])
def test_ineligible_scan_does_not_support_hypothesis(origin, verification, linked):
    g, _, shipment = _case()
    _scan(g, shipment, origin=origin, verification=verification, linked=linked)
    review = assess_inr_hypotheses(g)
    assert review.evidence_basis == "NONE"
    assert all(a.status == "UNRESOLVED" for a in review.assessments)
    assert review.suggested_action_id == "act_carrier_lookup"


def test_external_evidence_is_not_blended_with_conflicting_simulation():
    g, _, shipment = _case()
    real = _scan(g, shipment, delivered_zip="02139")
    _scan(g, shipment, delivered_zip="94110", origin=EvidenceOrigin.SYNTHETIC_FIXTURE)
    review = assess_inr_hypotheses(g)
    h = _by_id(review)
    assert review.evidence_basis == "EXTERNAL"
    assert h["carrier_delivered_to_order_postal_code"].supporting_evidence_ids == (real.id,)
    assert h["carrier_delivered_to_order_postal_code"].status == "SUPPORTED"


def test_conflicting_external_scans_abstain_and_keep_both_evidence_ids():
    g, _, shipment = _case()
    right = _scan(g, shipment, delivered_zip="02139")
    wrong = _scan(g, shipment, delivered_zip="94110")
    review = assess_inr_hypotheses(g)
    h = _by_id(review)["carrier_delivered_to_order_postal_code"]
    assert h.status == "CONFLICTED"
    assert h.supporting_evidence_ids == (right.id,)
    assert h.contradicting_evidence_ids == (wrong.id,)
    assert review.suggested_action_id == "act_resolve_contradiction"
    assert review.rationale.startswith("ABSTAIN")


def test_transit_report_is_not_asserted_to_be_delivery():
    g, _, shipment = _case()
    _scan(g, shipment, status="IN_TRANSIT")
    review = assess_inr_hypotheses(g)
    assert _by_id(review)["carrier_reports_in_transit_or_exception"].status == "SUPPORTED"
    assert _by_id(review)["carrier_delivered_to_order_postal_code"].status == "UNRESOLVED"
    assert review.suggested_action_id == "act_carrier_transit_monitor"


def test_incomplete_zip_abstains_from_address_claims():
    g, _, shipment = _case(order_zip="")
    _scan(g, shipment)
    review = assess_inr_hypotheses(g)
    assert _by_id(review)["carrier_delivered_to_order_postal_code"].status == "UNRESOLVED"
    assert _by_id(review)["carrier_delivered_to_other_postal_code"].status == "UNRESOLVED"


def test_multiple_shipments_abstain_instead_of_misattributing_scan():
    g, _, shipment = _case()
    _scan(g, shipment)
    g.add_node(NodeType.SHIPMENT, "Other shipment", {}, "MERCHANT")
    review = assess_inr_hypotheses(g)
    assert review.evidence_basis == "NONE"
    assert review.suggested_action_id is None
    assert "ABSTAIN" in review.rationale


def test_roundtrip_graph_preserves_hypothesis_support():
    g, _, shipment = _case()
    scan = _scan(g, shipment, delivered_zip="60614")
    restored = EvidenceGraph.from_data(g.dispute_id, g.to_data().model_dump())
    review = assess_inr_hypotheses(restored)
    assert _by_id(review)["carrier_delivered_to_other_postal_code"].supporting_evidence_ids == (scan.id,)


def test_attempted_contradiction_clarification_escalates_once():
    """Regression: do not re-add the same clarification after it was attempted."""
    g, order, shipment = _case()
    obs = _scan(g, shipment, delivered_zip="60614")
    g.add_edge(obs.id, order.id, EdgeType.CONTRADICTS, "Destination mismatch")
    g.add_node(NodeType.QUESTION, "Prior address clarification",
               {"action": {"action_id": "act_resolve_contradiction"}},
               "INVESTIGATION_ENGINE")
    readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory.ITEM_NOT_RECEIVED, g)
    decision = HeuristicNBEPolicy().evaluate_candidates(
        DisputeCategory.ITEM_NOT_RECEIVED, g, readiness
    )
    assert decision.chosen_action is not None
    assert decision.chosen_action.action_type == ActionType.ESCALATE_HUMAN_REVIEW
    assert not any(c.action_id == "act_resolve_contradiction" for c in decision.all_candidates)
