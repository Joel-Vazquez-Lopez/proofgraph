import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

from packages.shared_schemas.models import (
    DisputeCategory,
    NodeType,
    EdgeType,
    ActionType,
    CandidateAction,
    PolicyDecision,
    DecisionReadinessEvaluation,
)
from app.services.evidence_graph import EvidenceGraph


class NextBestEvidencePolicy(ABC):
    @abstractmethod
    def evaluate_candidates(
        self,
        category: DisputeCategory,
        graph: EvidenceGraph,
        readiness: DecisionReadinessEvaluation,
    ) -> PolicyDecision:
        pass


class HeuristicNBEPolicy(NextBestEvidencePolicy):
    """
    Deterministic, interpretable Next-Best-Evidence selection policy.
    Scores each possible acquisition action by:
      Utility = (w_r * Relevance + w_u * UncertaintyReduction + w_c * ContradictionWeight) / (1.0 + Friction)
    """

    def evaluate_candidates(
        self,
        category: DisputeCategory,
        graph: EvidenceGraph,
        readiness: DecisionReadinessEvaluation,
    ) -> PolicyDecision:
        candidates: List[CandidateAction] = []

        if readiness.is_decision_ready:
            return PolicyDecision(
                chosen_action=None,
                all_candidates=[],
                policy_name="HeuristicNBEPolicy",
                selection_rationale="Case is already decision-ready. No further evidence acquisition required.",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # 1. Check for Active Contradictions first (highest priority)
        contradictions = graph.get_contradictions()
        if contradictions:
            src, tgt, edge = contradictions[0]
            action = CandidateAction(
                action_id="act_resolve_contradiction",
                action_type=ActionType.REQUEST_BUYER_CLARIFICATION,
                title=f"Resolve Discrepancy: {src.label} vs {tgt.label}",
                description=(
                    f"A factual discrepancy was identified between {src.label} and {tgt.label}. "
                    "Request targeted clarification regarding destination address or receipt confirmation."
                ),
                target_party="BUYER",
                expected_information_gain=0.98,
                acquisition_friction=0.2,
                utility_score=0.95,
                rationale="Factual contradiction directly blocks decision-readiness. Resolving it has primary utility.",
                required_inputs=["clarification_statement", "supporting_address_document"]
            )
            candidates.append(action)

        # Collect already attempted action IDs to prevent infinite loops
        attempted_actions = set()
        for q in graph.get_nodes_by_type(NodeType.QUESTION):
            action_data = q.content.get("action")
            if isinstance(action_data, dict) and "action_id" in action_data:
                attempted_actions.add(action_data["action_id"])
            elif q.id.startswith("q_"):
                attempted_actions.add(q.id[2:])

        # 1. Scenario D — Check for Active Critical Contradictions first (highest priority)
        contradictions = graph.get_contradictions()
        critical_contradictions = [
            (src, tgt, edge) for src, tgt, edge in contradictions
            if tgt.type in (NodeType.ORDER, NodeType.TRANSACTION, NodeType.SHIPMENT)
            or "mismatch" in edge.provenance.lower()
            or "different" in edge.provenance.lower()
        ]
        if critical_contradictions:
            if "act_resolve_contradiction" not in attempted_actions:
                src, tgt, edge = critical_contradictions[0]
                action = CandidateAction(
                    action_id="act_resolve_contradiction",
                    action_type=ActionType.REQUEST_BUYER_CLARIFICATION,
                    title=f"Resolve Discrepancy: {src.label} vs {tgt.label}",
                    description=(
                        f"A factual discrepancy was identified between {src.label} and {tgt.label}. "
                        "Request targeted clarification regarding destination address or receipt confirmation."
                    ),
                    target_party="BUYER",
                    expected_information_gain=0.98,
                    acquisition_friction=0.2,
                    utility_score=0.95,
                    rationale="Factual contradiction directly blocks decision-readiness. Resolving it has primary utility.",
                    required_inputs=["clarification_statement", "supporting_address_document"]
                )
                candidates.append(action)
            else:
                candidates.append(CandidateAction(
                    action_id="act_escalate_human_review",
                    action_type=ActionType.ESCALATE_HUMAN_REVIEW,
                    title="Escalate Case for Human Adjudication (Unresolved Contradiction)",
                    description="Factual contradiction persists after party inquiry. Requires human review.",
                    target_party="SYSTEM",
                    expected_information_gain=0.1,
                    acquisition_friction=0.0,
                    utility_score=0.99,
                    rationale="Autonomous investigation cannot reconcile destination mismatch.",
                    required_inputs=[]
                ))

        # 2. Category-Specific Candidate Generation
        if category == DisputeCategory.ITEM_NOT_RECEIVED:
            shipment_nodes = graph.get_nodes_by_type(NodeType.SHIPMENT)
            obs_nodes = graph.get_nodes_by_type(NodeType.OBSERVATION)
            carrier_obs = [
                o for o in obs_nodes
                if ("carrier" in o.source.lower() or "tracking" in o.label.lower())
            ]

            has_tracking = len(shipment_nodes) > 0
            
            # Sub-case: Missing tracking number entirely
            if not has_tracking:
                if "act_merchant_tracking" not in attempted_actions:
                    action = CandidateAction(
                        action_id="act_merchant_tracking",
                        action_type=ActionType.REQUEST_MERCHANT_FULFILLMENT,
                        title="Request Carrier Tracking Number",
                        description="Request carrier shipping name and tracking number from merchant.",
                        target_party="MERCHANT",
                        expected_information_gain=0.90,
                        acquisition_friction=0.5,
                        utility_score=0.90 / (1.0 + 0.5),  # 0.60
                        rationale="Essential proof of fulfillment needed to determine package transit and delivery status.",
                        required_inputs=["carrier_name", "tracking_number"]
                    )
                    candidates.append(action)
                else:
                    # Scenario E: Merchant failed to provide tracking after inquiry -> escalate
                    candidates.append(CandidateAction(
                        action_id="act_escalate_human_review",
                        action_type=ActionType.ESCALATE_HUMAN_REVIEW,
                        title="Escalate Case for Human Adjudication (Tracking Missing)",
                        description="Merchant has not provided carrier tracking details after inquiry. Escalate for default adjudication.",
                        target_party="SYSTEM",
                        expected_information_gain=0.1,
                        acquisition_friction=0.0,
                        utility_score=0.99,
                        rationale="Information acquisition path exhausted without fulfillment proof.",
                        required_inputs=[]
                    ))

            # Sub-case: Tracking number provided, but carrier verification status
            elif not carrier_obs:
                # Scenario C — Unknown delivery (unverified tracking)
                shipment = shipment_nodes[0]
                tracking_no = shipment.content.get("tracking_number", "UNKNOWN")
                carrier = shipment.content.get("carrier_name", "Carrier")
                
                if "act_carrier_lookup" not in attempted_actions:
                    action = CandidateAction(
                        action_id="act_carrier_lookup",
                        action_type=ActionType.CARRIER_TRACKING_LOOKUP,
                        title=f"Query {carrier} Tracking Telemetry",
                        description=f"Automated query to carrier API for tracking number {tracking_no}.",
                        target_party="CARRIER",
                        expected_information_gain=0.95,
                        acquisition_friction=0.1,
                        utility_score=0.95 / (1.0 + 0.1),  # 0.86
                        rationale="Zero-friction automated lookup that directly satisfies delivery verification requirement.",
                        required_inputs=[]
                    )
                    candidates.append(action)
                elif "act_request_carrier_receipt" not in attempted_actions:
                    # Carrier API had no record; ask merchant for official drop-off receipt
                    candidates.append(CandidateAction(
                        action_id="act_request_carrier_receipt",
                        action_type=ActionType.REQUEST_MERCHANT_FULFILLMENT,
                        title="Request Physical Carrier Acceptance Receipt",
                        description=f"Carrier API returned no active tracking for {tracking_no}. Request merchant drop-off receipt.",
                        target_party="MERCHANT",
                        expected_information_gain=0.80,
                        acquisition_friction=0.7,
                        utility_score=0.80 / (1.0 + 0.7),
                        rationale="Carrier tracking is unverified. Physical drop-off documentation needed.",
                        required_inputs=["carrier_dropoff_receipt"]
                    ))
                else:
                    # Scenario E: Both carrier query and receipt inquiry exhausted
                    candidates.append(CandidateAction(
                        action_id="act_escalate_human_review",
                        action_type=ActionType.ESCALATE_HUMAN_REVIEW,
                        title="Escalate Case for Human Adjudication (Unverified Shipment)",
                        description="Carrier telemetry unavailable and drop-off documentation exhausted.",
                        target_party="SYSTEM",
                        expected_information_gain=0.1,
                        acquisition_friction=0.0,
                        utility_score=0.99,
                        rationale="Cannot establish verified delivery status autonomously.",
                        required_inputs=[]
                    ))

            else:
                # Carrier observation is present
                primary_carrier_obs = carrier_obs[0]
                st = str(primary_carrier_obs.content.get("status", "")).upper()

                if st == "DELIVERED":
                    # Scenario A — Confirmed delivery scan, but buyer claims non-receipt
                    has_signature = primary_carrier_obs.content.get("has_signature", False)
                    if not has_signature and "act_request_signature_or_proof" not in attempted_actions:
                        # Identify unresolved delivery questions instead of blindly dismissing buyer claim!
                        candidates.append(CandidateAction(
                            action_id="act_request_signature_or_proof",
                            action_type=ActionType.REQUEST_PROOF_OF_DELIVERY,
                            title="Request Carrier Signature or Delivery Photo Confirmation",
                            description=(
                                "Carrier reports residence delivery without signature. Buyer disputes receipt. "
                                "Request signature scan, GPS delivery coordinates, or carrier drop photo."
                            ),
                            target_party="MERCHANT",
                            expected_information_gain=0.85,
                            acquisition_friction=0.6,
                            utility_score=0.85 / (1.0 + 0.6),  # 0.53
                            rationale="Resolves tension between carrier front-door scan and buyer non-receipt report.",
                            required_inputs=["signature_record", "delivery_photo"]
                        ))

                elif st in ("IN_TRANSIT", "DELAYED", "EXCEPTION"):
                    # Scenario B — No delivery / in transit
                    if "act_carrier_transit_monitor" not in attempted_actions:
                        candidates.append(CandidateAction(
                            action_id="act_carrier_transit_monitor",
                            action_type=ActionType.CARRIER_STATUS_MONITOR,
                            title="Monitor In-Transit Carrier Telemetry",
                            description=f"Shipment is currently {st}. Check carrier updates for scheduled delivery window.",
                            target_party="CARRIER",
                            expected_information_gain=0.88,
                            acquisition_friction=0.2,
                            utility_score=0.88 / (1.0 + 0.2),  # 0.73
                            rationale="Shipment has not been completed. Polling updates avoids premature closure.",
                            required_inputs=[]
                        ))
                    else:
                        # In transit for prolonged period -> escalate
                        candidates.append(CandidateAction(
                            action_id="act_escalate_human_review",
                            action_type=ActionType.ESCALATE_HUMAN_REVIEW,
                            title="Escalate Case for Human Review (Prolonged Transit Exception)",
                            description="Carrier status remains in-transit or delayed beyond expected window.",
                            target_party="SYSTEM",
                            expected_information_gain=0.1,
                            acquisition_friction=0.0,
                            utility_score=0.99,
                            rationale="Package appears delayed or lost in transit.",
                            required_inputs=[]
                        ))

                elif st in ("UNKNOWN", "NOT_FOUND"):
                    # Scenario C & E: Carrier confirmed tracking unknown
                    if "act_request_carrier_receipt" not in attempted_actions:
                        candidates.append(CandidateAction(
                            action_id="act_request_carrier_receipt",
                            action_type=ActionType.REQUEST_MERCHANT_FULFILLMENT,
                            title="Request Physical Carrier Drop-Off Receipt",
                            description="Carrier returned no record for provided tracking. Request merchant receipt.",
                            target_party="MERCHANT",
                            expected_information_gain=0.80,
                            acquisition_friction=0.7,
                            utility_score=0.80 / (1.0 + 0.7),
                            rationale="Carrier tracking is unverified.",
                            required_inputs=["carrier_dropoff_receipt"]
                        ))
                    else:
                        candidates.append(CandidateAction(
                            action_id="act_escalate_human_review",
                            action_type=ActionType.ESCALATE_HUMAN_REVIEW,
                            title="Escalate Case for Human Adjudication (Untracked Shipment)",
                            description="Carrier confirmed tracking is not found, and merchant receipt not provided.",
                            target_party="SYSTEM",
                            expected_information_gain=0.1,
                            acquisition_friction=0.0,
                            utility_score=0.99,
                            rationale="Cannot verify shipment.",
                            required_inputs=[]
                        ))

        elif category == DisputeCategory.SIGNIFICANTLY_NOT_AS_DESCRIBED:
            # Need photo or condition evidence from buyer
            action = CandidateAction(
                action_id="act_buyer_condition_photo",
                action_type=ActionType.REQUEST_IMAGE_VERIFICATION,
                title="Request Item Condition Photograph",
                description="Request clear photo of received item, serial/barcode, and shipping packaging.",
                target_party="BUYER",
                expected_information_gain=0.85,
                acquisition_friction=0.8,
                utility_score=0.85 / (1.0 + 0.8),  # ~0.47
                rationale="Essential to verify buyer's claim regarding condition discrepancy.",
                required_inputs=["condition_photo", "unboxing_notes"]
            )
            candidates.append(action)

        elif category == DisputeCategory.DUPLICATE_TRANSACTION:
            action = CandidateAction(
                action_id="act_cross_ref_tx",
                action_type=ActionType.CROSS_REFERENCE_TRANSACTION,
                title="Correlate Secondary Settlement Log",
                description="Query PayPal account transactions within 15 minutes of primary timestamp.",
                target_party="SYSTEM",
                expected_information_gain=0.95,
                acquisition_friction=0.05,
                utility_score=0.95 / (1.0 + 0.05),
                rationale="Instant automated verification of duplicate charge idempotency key.",
                required_inputs=[]
            )
            candidates.append(action)

        # Sort candidates by utility_score descending
        candidates.sort(key=lambda c: c.utility_score, reverse=True)
        chosen = candidates[0] if candidates else None

        rationale = (
            f"Selected action '{chosen.title}' with highest net utility score ({chosen.utility_score:.2f}) "
            f"balancing high information gain ({chosen.expected_information_gain:.2f}) "
            f"and minimal friction ({chosen.acquisition_friction:.2f})."
            if chosen else "No actionable candidates identified."
        )

        return PolicyDecision(
            chosen_action=chosen,
            all_candidates=candidates,
            policy_name="HeuristicNBEPolicy",
            selection_rationale=rationale,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


class FixedChecklistPolicy(NextBestEvidencePolicy):
    """
    Baseline A: Fixed Checklist Policy.
    Asks a fixed, exhaustive checklist of questions regardless of state.
    """
    def evaluate_candidates(
        self,
        category: DisputeCategory,
        graph: EvidenceGraph,
        readiness: DecisionReadinessEvaluation,
    ) -> PolicyDecision:
        checklist = [
            CandidateAction(
                action_id="chk_1",
                action_type=ActionType.REQUEST_MERCHANT_FULFILLMENT,
                title="Submit Invoices and Receipts",
                description="Submit all order invoices, line-item receipts, and customer messages.",
                target_party="MERCHANT",
                expected_information_gain=0.5,
                acquisition_friction=1.5,
                utility_score=0.2,
                rationale="Checklist Step 1",
            ),
            CandidateAction(
                action_id="chk_2",
                action_type=ActionType.REQUEST_MERCHANT_FULFILLMENT,
                title="Submit Shipping Labels",
                description="Submit physical scans of all shipping labels.",
                target_party="MERCHANT",
                expected_information_gain=0.5,
                acquisition_friction=1.2,
                utility_score=0.2,
                rationale="Checklist Step 2",
            ),
            CandidateAction(
                action_id="chk_3",
                action_type=ActionType.REQUEST_BUYER_CLARIFICATION,
                title="Confirm Buyer Identity",
                description="Request buyer to submit proof of residence.",
                target_party="BUYER",
                expected_information_gain=0.2,
                acquisition_friction=2.0,
                utility_score=0.06,
                rationale="Checklist Step 3",
            ),
        ]
        return PolicyDecision(
            chosen_action=checklist[0],
            all_candidates=checklist,
            policy_name="FixedChecklistPolicy",
            selection_rationale="Static checklist item 1 chosen unconditionally.",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
