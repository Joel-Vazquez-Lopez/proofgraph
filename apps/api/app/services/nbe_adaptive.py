"""Evidence-dependent INR next-action selection without probabilistic claims.

The existing PolicyDecision/CandidateAction JSON contract remains unchanged.
"expected_information_gain" is always zero (not estimated); utility_score is
a deterministic *coverage-per-friction priority*, NOT expected information gain.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, FrozenSet, Mapping, Optional, Tuple

from packages.shared_schemas.models import (
    ActionType, CandidateAction, DecisionReadinessEvaluation, DisputeCategory,
    EdgeType, EvidenceOrigin, EvidenceVerificationStatus, NodeType, PolicyDecision,
)
from app.services.evidence_graph import EvidenceGraph
from app.services.hypothesis_engine import HypothesisReview, assess_inr_hypotheses
from app.services.nbe_policy import HeuristicNBEPolicy, NextBestEvidencePolicy


@dataclass(frozen=True)
class InvestigationNeed:
    key: str
    unresolved_question: str
    hypothesis_ids: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    importance: int  # ordinal engineering priority, not measured probability


@dataclass(frozen=True)
class ActionCapability:
    action_id: str
    action_type: ActionType
    title: str
    target_party: str
    required_inputs: Tuple[str, ...]
    discriminates: FrozenSet[str]
    friction: float  # policy-configured manual operational friction, not measured cost


# An intentionally small allowlist. All non-escalation actions have current
# supported routes: POST /evidence for tracking, documents or clarification,
# POST /verify-carrier for carrier lookup. No background polling is advertised.
_CAPABILITIES = (
    ActionCapability(
        "act_merchant_tracking", ActionType.REQUEST_MERCHANT_FULFILLMENT,
        "Request Merchant Carrier Tracking", "MERCHANT",
        ("carrier_name", "tracking_number"), frozenset({"tracking_identity"}), 0.5,
    ),
    ActionCapability(
        "act_carrier_lookup", ActionType.CARRIER_TRACKING_LOOKUP,
        "Query Carrier Tracking", "CARRIER",
        (), frozenset({"carrier_report", "carrier_destination", "updated_delivery"}), 0.1,
    ),
    ActionCapability(
        "act_resolve_contradiction", ActionType.REQUEST_BUYER_CLARIFICATION,
        "Clarify Conflicting Delivery Address or Scan", "BUYER",
        ("clarification_statement", "supporting_address_document"),
        frozenset({"delivery_discrepancy", "report_consistency"}), 0.2,
    ),
    ActionCapability(
        "act_request_carrier_receipt", ActionType.REQUEST_MERCHANT_FULFILLMENT,
        "Request Carrier Acceptance or Delivery Records", "MERCHANT",
        ("carrier_dropoff_receipt",),
        frozenset({"carrier_report", "carrier_destination", "delivery_discrepancy", "report_consistency"}), 0.7,
    ),
    ActionCapability(
        "act_request_signature_or_proof", ActionType.REQUEST_PROOF_OF_DELIVERY,
        "Request Signature, Delivery Photo, or Handoff Record", "MERCHANT",
        ("signature_record", "delivery_photo"),
        frozenset({"physical_handoff"}), 0.6,
    ),
)


def _attempted(graph: EvidenceGraph) -> FrozenSet[str]:
    attempted = set()
    for question in graph.get_nodes_by_type(NodeType.QUESTION):
        action = question.content.get("action")
        if isinstance(action, dict) and isinstance(action.get("action_id"), str):
            attempted.add(action["action_id"])
        elif question.id.startswith("q_act_"):
            attempted.add(question.id[2:])
    return frozenset(attempted)


def _report_evidence(review: HypothesisReview) -> Tuple[str, ...]:
    return tuple(sorted({
        node_id for assessment in review.assessments
        for node_id in (*assessment.supporting_evidence_ids, *assessment.contradicting_evidence_ids)
    }))


def _handoff_evidence(graph: EvidenceGraph, shipment_id: str) -> Tuple[str, ...]:
    """Do not count submitted uploads as verified physical receipt."""
    linked = {
        (e.source_id, e.target_id)
        for e in graph.to_data().edges
        if e.type == EdgeType.RELATES_TO
    }
    return tuple(sorted(
        item.id for item in graph.get_nodes_by_type(NodeType.EVIDENCE_ITEM)
        if item.verification_status == EvidenceVerificationStatus.VERIFIED
        and item.origin in (EvidenceOrigin.VERIFIED_EXTERNAL, EvidenceOrigin.SYNTHETIC_FIXTURE)
        and item.content.get("kind") in ("recipient_acknowledgement", "signature_record", "delivery_photo")
        and ((item.id, shipment_id) in linked or (shipment_id, item.id) in linked)
    ))


def _derive_needs(graph: EvidenceGraph, review: HypothesisReview) -> Tuple[InvestigationNeed, ...]:
    shipments = graph.get_nodes_by_type(NodeType.SHIPMENT)
    orders = graph.get_nodes_by_type(NodeType.ORDER)
    if len(orders) != 1:
        return ()
    if not shipments:
        return (InvestigationNeed(
            "tracking_identity", "Which carrier/tracking identifier, if any, belongs to this order?",
            ("carrier_delivered_to_order_postal_code", "carrier_delivered_to_other_postal_code",
             "carrier_reports_in_transit_or_exception"), tuple(o.id for o in orders), 3,
        ),)
    if len(shipments) != 1:
        return ()  # no supported safe shipment association
    ids = _report_evidence(review)
    statuses = {a.hypothesis_id: a.status for a in review.assessments}
    matched = statuses.get("carrier_delivered_to_order_postal_code") == "SUPPORTED"
    wrong = statuses.get("carrier_delivered_to_other_postal_code") == "SUPPORTED"
    conflicting = "CONFLICTED" in statuses.values() or (
        statuses.get("carrier_reports_in_transit_or_exception") == "SUPPORTED"
        and (matched or wrong)
    )
    if conflicting:
        return (InvestigationNeed(
            "report_consistency", "Which incompatible carrier report is current and authoritative?",
            ("carrier_delivered_to_order_postal_code", "carrier_delivered_to_other_postal_code",
             "carrier_reports_in_transit_or_exception"), ids, 4,
        ),)
    if wrong:
        return (InvestigationNeed(
            "delivery_discrepancy", "Was the package sent to the buyer's ordered destination?",
            ("carrier_delivered_to_other_postal_code", "carrier_delivered_to_order_postal_code"),
            ids + (orders[0].id,), 4,
        ),)
    transit = statuses.get("carrier_reports_in_transit_or_exception") == "SUPPORTED"
    if transit:
        return (InvestigationNeed(
            "updated_delivery", "Has the undelivered shipment's carrier status changed?",
            ("carrier_reports_in_transit_or_exception", "carrier_delivered_to_order_postal_code"),
            ids, 2,
        ),)
    if matched:
        has_claim = any(
            str(n.content.get("party", "")).upper() == "BUYER"
            for n in graph.get_nodes_by_type(NodeType.CLAIM)
        )
        if has_claim and not _handoff_evidence(graph, shipments[0].id):
            return (InvestigationNeed(
                "physical_handoff", "Did anyone actually receive the parcel, or could it have been lost, stolen, or misdelivered after the scan?",
                ("buyer_physically_received_item", "nonreceipt_due_to_loss_or_misdelivery"),
                ids + tuple(n.id for n in graph.get_nodes_by_type(NodeType.CLAIM) if n.content.get("party") == "BUYER"),
                3,
            ),)
        return ()
    if review.evidence_basis != "NONE":
        return (InvestigationNeed(
            "carrier_destination", "Where did the carrier report delivering the parcel? The recorded destination is incomplete.",
            ("carrier_delivered_to_order_postal_code", "carrier_delivered_to_other_postal_code"),
            ids + (orders[0].id,), 2,
        ),)
    return (InvestigationNeed(
        "carrier_report", "What independently verified carrier status, if any, is available?",
        ("carrier_delivered_to_order_postal_code", "carrier_delivered_to_other_postal_code",
         "carrier_reports_in_transit_or_exception"),
        tuple(s.id for s in shipments), 3,
    ),)


class HypothesisDiscriminationPolicy(NextBestEvidencePolicy):
    """Deterministic hypothesis-linked acquisition policy.

    Availability comes from the caller's adapter capability assessment;
    a supported endpoint is NOT proof that a real external integration exists.
    No automatic adjudication or claim-verification changes.
    """

    def __init__(
        self,
        availability: Optional[Mapping[str, bool]] = None,
        friction: Optional[Mapping[str, float]] = None,
    ):
        self.availability = dict(availability or {})
        self.friction = dict(friction or {})
        self.baseline = HeuristicNBEPolicy()

    def evaluate_candidates(
        self, category: DisputeCategory, graph: EvidenceGraph,
        readiness: DecisionReadinessEvaluation,
    ) -> PolicyDecision:
        if category != DisputeCategory.ITEM_NOT_RECEIVED:
            return self.baseline.evaluate_candidates(category, graph, readiness)

        review = assess_inr_hypotheses(graph)
        needs = _derive_needs(graph, review)
        attempted = _attempted(graph)
        candidates = []
        for cap in _CAPABILITIES:
            matching = tuple(need for need in needs if need.key in cap.discriminates)
            if not matching or cap.action_id in attempted or not self.availability.get(cap.action_id, True):
                continue
            friction = self.friction.get(cap.action_id, cap.friction)
            if friction < 0:
                continue
            # Explicit ambiguity-coverage objective. Importance is an ordinal
            # policy choice; this is neither a probability nor expected entropy reduction.
            coverage = sum(n.importance for n in matching)
            score = round(coverage / (1.0 + friction), 6)
            evidence_ids = sorted({i for n in matching for i in n.evidence_ids})
            hypotheses = sorted({h for n in matching for h in n.hypothesis_ids})
            questions = "; ".join(n.unresolved_question for n in matching)
            candidates.append(CandidateAction(
                action_id=cap.action_id,
                action_type=cap.action_type,
                title=cap.title,
                description=questions,
                target_party=cap.target_party,
                expected_information_gain=0.0,
                acquisition_friction=friction,
                utility_score=score,
                rationale=(
                    f"Addresses unresolved question(s): {questions} "
                    f"Competing hypotheses: {', '.join(hypotheses)}. "
                    f"Evidence IDs: {', '.join(evidence_ids) or 'none'}. "
                    f"Evidence basis: {review.evidence_basis}. "
                    f"Ordinal ambiguity coverage {coverage}/(1+friction {friction:g})={score:g}; "
                    "not an information-gain estimate or proof of receipt."
                ),
                required_inputs=list(cap.required_inputs),
            ))
        candidates.sort(key=lambda c: (-c.utility_score, c.acquisition_friction, c.action_id))
        if candidates and (needs or not readiness.is_decision_ready):
            chosen = candidates[0]
            explanation = (
                f"Selected {chosen.action_id}. {chosen.rationale} "
                f"Alternatives excluded if unavailable or previously attempted: {', '.join(sorted(attempted)) or 'none'}."
            )
        elif needs:
            chosen = CandidateAction(
                action_id="act_escalate_human_review",
                action_type=ActionType.ESCALATE_HUMAN_REVIEW,
                title="Escalate: No Available Discriminating Evidence Action",
                description="Human adjudicator must investigate unresolved questions and missing authority.",
                target_party="SYSTEM",
                expected_information_gain=0.0,
                acquisition_friction=0.0,
                utility_score=0.0,
                rationale=(
                    "ABSTAIN: all relevant acquisition actions are attempted, disabled, or unsupported. "
                    + " ".join(f"{n.unresolved_question} Evidence IDs: {', '.join(n.evidence_ids)}." for n in needs)
                    + f" {review.rationale}"
                ),
                required_inputs=[],
            )
            explanation = chosen.rationale
            candidates = [chosen]
        elif not readiness.is_decision_ready:
            # An unsupported / under-specified graph must not silently close.
            chosen = CandidateAction(
                action_id="act_escalate_human_review",
                action_type=ActionType.ESCALATE_HUMAN_REVIEW,
                title="Escalate: Investigation Cannot Safely Disambiguate",
                description="No safe discriminating action exists for the current graph.",
                target_party="SYSTEM",
                expected_information_gain=0.0, acquisition_friction=0.0,
                utility_score=0.0, required_inputs=[],
                rationale=f"ABSTAIN: {review.rationale} Unresolved readiness: {readiness.missing_requirements}",
            )
            explanation = chosen.rationale
            candidates = [chosen]
        else:
            chosen = None
            explanation = (
                f"No useful action remains under current hypothesis checks. {review.rationale} "
                "Readiness is evaluated separately; this policy does not decide who receives funds."
            )
        return PolicyDecision(
            chosen_action=chosen, all_candidates=candidates,
            policy_name="HypothesisDiscriminationPolicy",
            selection_rationale=explanation,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
