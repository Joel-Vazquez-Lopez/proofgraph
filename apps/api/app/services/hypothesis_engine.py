"""Qualitative, provenance-aware competing hypotheses for one INR shipment.

This is a read-only research component. It does not change adjudication/readiness,
claim verified receipt, or assign uncalibrated likelihoods to explanations.
"""
from dataclasses import dataclass
from typing import Optional, Tuple

from packages.shared_schemas.models import (
    EdgeType,
    EvidenceOrigin,
    EvidenceVerificationStatus,
    NodeType,
)
from app.services.evidence_graph import EvidenceGraph


@dataclass(frozen=True)
class HypothesisAssessment:
    hypothesis_id: str
    status: str  # SUPPORTED | CONTRADICTED | CONFLICTED | UNRESOLVED
    supporting_evidence_ids: Tuple[str, ...] = ()
    contradicting_evidence_ids: Tuple[str, ...] = ()
    explanation: str = ""


@dataclass(frozen=True)
class HypothesisReview:
    assessments: Tuple[HypothesisAssessment, ...]
    evidence_basis: str  # EXTERNAL | SIMULATED | NONE
    suggested_action_id: Optional[str]
    rationale: str


_HYPOTHESES = (
    "carrier_delivered_to_order_postal_code",
    "carrier_delivered_to_other_postal_code",
    "carrier_reports_in_transit_or_exception",
)


def _assessment(name: str, supporting: Tuple[str, ...], opposing: Tuple[str, ...]) -> HypothesisAssessment:
    if supporting and opposing:
        state = "CONFLICTED"
        explanation = "Eligible observations support incompatible carrier reports; ordering or correction is needed."
    elif supporting:
        state = "SUPPORTED"
        explanation = "Eligible carrier observation supports this report, not proof of physical receipt."
    elif opposing:
        state = "CONTRADICTED"
        explanation = "Eligible carrier observation supports an incompatible report."
    else:
        state = "UNRESOLVED"
        explanation = "Available eligible evidence does not distinguish this explanation."
    return HypothesisAssessment(name, state, supporting, opposing, explanation)


def assess_inr_hypotheses(graph: EvidenceGraph) -> HypothesisReview:
    """Assess *carrier-reported states*; never infer buyer receipt or dispute outcome.

    Only verified EXTERNAL or SYNTHETIC observations linked via DERIVED_FROM to the
    *single* shipment participate. User submissions and model inferences are not
    carrier corroboration, regardless of their verification_status.
    """
    shipments = graph.get_nodes_by_type(NodeType.SHIPMENT)
    orders = graph.get_nodes_by_type(NodeType.ORDER)
    if len(shipments) != 1 or len(orders) != 1:
        return HypothesisReview(
            tuple(_assessment(h, (), ()) for h in _HYPOTHESES),
            "NONE", None,
            "ABSTAIN: exactly one order and one shipment are required to associate carrier reports safely.",
        )

    destination = orders[0].content.get("destination_address", {})
    order_zip = (
        str(destination.get("postal_code", "")).strip()
        if isinstance(destination, dict) else ""
    )
    linked_ids = {
        edge.source_id
        for edge in graph.to_data().edges
        if edge.type == EdgeType.DERIVED_FROM and edge.target_id == shipments[0].id
    }
    eligible = [
        obs for obs in graph.get_nodes_by_type(NodeType.OBSERVATION)
        if obs.id in linked_ids
        and obs.verification_status == EvidenceVerificationStatus.VERIFIED
        and obs.origin in (EvidenceOrigin.VERIFIED_EXTERNAL, EvidenceOrigin.SYNTHETIC_FIXTURE)
    ]
    external = [obs for obs in eligible if obs.origin == EvidenceOrigin.VERIFIED_EXTERNAL]
    simulated = [obs for obs in eligible if obs.origin == EvidenceOrigin.SYNTHETIC_FIXTURE]
    # Do not combine fixture and independent reports into a fictitious consensus.
    selected = external if external else simulated
    basis = "EXTERNAL" if external else "SIMULATED" if simulated else "NONE"

    matching, different, transit, delivered = [], [], [], []
    for obs in selected:
        status = str(obs.content.get("status", "")).strip().upper()
        if status == "DELIVERED":
            delivered.append(obs.id)
            reported = obs.content.get("delivered_to_address", {})
            delivered_zip = (
                str(reported.get("postal_code", "")).strip()
                if isinstance(reported, dict) else ""
            )
            if order_zip and delivered_zip:
                (matching if order_zip == delivered_zip else different).append(obs.id)
        elif status in ("IN_TRANSIT", "DELAYED", "EXCEPTION"):
            transit.append(obs.id)

    result = (
        _assessment(_HYPOTHESES[0], tuple(matching), tuple(different)),
        _assessment(_HYPOTHESES[1], tuple(different), tuple(matching)),
        _assessment(_HYPOTHESES[2], tuple(transit), tuple(delivered)),
        # Carrier location reports cannot distinguish actual receipt from later
        # loss, theft, same-ZIP misdelivery, or an incorrect delivery report.
        # These physical alternatives remain explicitly unresolved; no
        # posterior probabilities or receipt claims are inferred.
        HypothesisAssessment(
            "buyer_physically_received_item", "UNRESOLVED",
            explanation="A carrier scan or postal-code match does not prove actual buyer possession.",
        ),
        HypothesisAssessment(
            "nonreceipt_due_to_loss_or_misdelivery", "UNRESOLVED",
            explanation="No independently corroborated chain of custody distinguishes loss, theft, or misdelivery.",
        ),
    )
    if any(a.status == "CONFLICTED" for a in result) or (transit and delivered):
        next_action = "act_resolve_contradiction"
        reason = "ABSTAIN: incompatible carrier reports require a dated reconciliation."
    elif different:
        next_action = "act_resolve_contradiction"
        reason = "Carrier reports delivery to a different postal code; request address reconciliation."
    elif matching:
        buyer_claim = any(
            str(claim.content.get("party", "")).upper() == "BUYER"
            for claim in graph.get_nodes_by_type(NodeType.CLAIM)
        )
        next_action = "act_request_signature_or_proof" if buyer_claim else None
        reason = (
            "Matching carrier postal code does not establish receipt; request proof of handoff."
            if buyer_claim else "Carrier report aligns by postal code, but physical receipt is not established."
        )
    elif transit:
        next_action = "act_carrier_transit_monitor"
        reason = "Carrier reports transit or exception; no verified delivery event selected."
    else:
        next_action = "act_carrier_lookup"
        reason = "ABSTAIN: missing eligible carrier telemetry or decisive destination information."

    if basis == "SIMULATED":
        reason += " All selected observations are synthetic fixtures, not independent verification."
    elif basis == "NONE":
        reason += " Neither independently corroborated nor simulated eligible observations were found."
    return HypothesisReview(result, basis, next_action, reason)
