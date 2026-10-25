from typing import List
from packages.shared_schemas.models import (
    DisputeCategory,
    InvestigationState,
    NodeType,
    EdgeType,
    EvidenceVerificationStatus,
    DecisionReadinessEvaluation,
)
from app.services.evidence_graph import EvidenceGraph


class DecisionReadinessEvaluator:
    """
    Deterministic evaluation of dispute-readiness standards.
    Decision-ready means the case package satisfies documented handoff criteria
    for human or PayPal adjudicator review. It does not dictate who wins.
    """

    @classmethod
    def evaluate(cls, category: DisputeCategory, graph: EvidenceGraph) -> DecisionReadinessEvaluation:
        if category == DisputeCategory.ITEM_NOT_RECEIVED:
            return cls._evaluate_item_not_received(graph)
        elif category == DisputeCategory.SIGNIFICANTLY_NOT_AS_DESCRIBED:
            return cls._evaluate_snad(graph)
        elif category == DisputeCategory.DUPLICATE_TRANSACTION:
            return cls._evaluate_duplicate_transaction(graph)
        elif category == DisputeCategory.INCORRECT_AMOUNT:
            return cls._evaluate_incorrect_amount(graph)
        else:
            return cls._evaluate_generic(category, graph)

    @classmethod
    def _evaluate_item_not_received(cls, graph: EvidenceGraph) -> DecisionReadinessEvaluation:
        satisfied: List[str] = []
        missing: List[str] = []
        contradictions_desc: List[str] = []

        # 1. Transaction verification
        tx_nodes = [n for n in graph.get_nodes_by_type(NodeType.TRANSACTION) if n.verification_status == EvidenceVerificationStatus.VERIFIED]
        if tx_nodes:
            satisfied.append("Verified transaction record present.")
        else:
            missing.append("Verified transaction record from PayPal.")

        # 2. Merchant order & shipping address record
        order_nodes = graph.get_nodes_by_type(NodeType.ORDER)
        if order_nodes:
            satisfied.append("Merchant order record with destination address identified.")
        else:
            missing.append("Merchant order details with confirmed shipping address.")

        # 3. Shipment carrier & tracking details
        shipment_nodes = graph.get_nodes_by_type(NodeType.SHIPMENT)
        if shipment_nodes:
            satisfied.append("Carrier tracking identifier recorded.")
        else:
            missing.append("Carrier shipping identifier / tracking number.")

        # 4. Carrier delivery observation
        obs_nodes = graph.get_nodes_by_type(NodeType.OBSERVATION)
        delivery_obs = [
            obs for obs in obs_nodes
            if ("carrier" in obs.source.lower() or "tracking" in obs.label.lower())
        ]
        
        delivered_obs = None
        in_transit_obs = None
        unknown_carrier_obs = None

        for obs in delivery_obs:
            st = str(obs.content.get("status", "")).upper()
            if st == "DELIVERED":
                delivered_obs = obs
            elif st in ("IN_TRANSIT", "DELAYED", "EXCEPTION"):
                in_transit_obs = obs
            elif st in ("UNKNOWN", "NOT_FOUND"):
                unknown_carrier_obs = obs

        if delivered_obs and delivered_obs.verification_status == EvidenceVerificationStatus.VERIFIED:
            satisfied.append(f"Carrier verified delivery ({delivered_obs.label}).")
            has_signature = delivered_obs.content.get("has_signature", False)

            # Check for active buyer non-receipt claims
            buyer_claims = [
                n for n in graph.get_nodes_by_type(NodeType.CLAIM)
                if n.content.get("party") == "BUYER"
            ]
            buyer_disputes_receipt = bool(buyer_claims)

            # Check if signature / delivery proof evidence was submitted
            has_proof_of_delivery = any(
                n for n in graph.get_nodes_by_type(NodeType.EVIDENCE_ITEM)
                if ("signature" in n.label.lower() or "proof" in n.label.lower() or "gps" in str(n.content).lower())
                and n.verification_status == EvidenceVerificationStatus.VERIFIED
            )

            if not has_signature and buyer_disputes_receipt and not has_proof_of_delivery:
                # Scenario A: Delivery scan without signature, but buyer actively disputes receipt.
                # Do NOT dismiss the buyer's claim. Record unresolved delivery question.
                missing.append(
                    "Buyer reports non-receipt despite carrier delivery scan. "
                    "Unresolved: carrier signature record, GPS delivery coordinates, "
                    "or drop-photo confirmation required."
                )
            elif has_proof_of_delivery:
                satisfied.append("Carrier signature/drop photo verification provided resolving buyer non-receipt inquiry.")
            elif not has_signature:
                satisfied.append(
                    "Delivery completed without recipient signature (front-door drop); "
                    "no active buyer non-receipt claim."
                )
        elif in_transit_obs:
            missing.append(f"Proof of completed delivery (shipment is currently in-transit/exception: {in_transit_obs.content.get('status', 'IN_TRANSIT')}).")
        elif unknown_carrier_obs:
            missing.append("Independent carrier delivery verification (carrier lookup returned unverified/not found).")
        else:
            missing.append("Verified carrier tracking telemetry or proof of delivery.")

        # 5. Check active critical contradictions in graph (e.g. address or order discrepancies)
        contradictions = graph.get_contradictions()
        critical_contradictions = [
            (src, tgt, edge) for src, tgt, edge in contradictions
            if tgt.type in (NodeType.ORDER, NodeType.TRANSACTION, NodeType.SHIPMENT)
            or "mismatch" in edge.provenance.lower()
            or "different" in edge.provenance.lower()
        ]
        for src, tgt, edge in critical_contradictions:
            contradictions_desc.append(f"Critical discrepancy between {src.label} and {tgt.label}: {edge.provenance}")

        # Check if investigation has been explicitly escalated due to exhaustion
        escalation_flag = any(
            "escalate" in q.id.lower() or "insufficient" in q.label.lower()
            for q in graph.get_nodes_by_type(NodeType.QUESTION)
        )

        # Determine decision readiness & recommended state
        requires_escalation = False
        if critical_contradictions:
            # Critical discrepancy (e.g. delivery address mismatch)
            requires_escalation = True
            recommended_state = InvestigationState.REVIEW_REQUIRED
            rationale = (
                f"Investigation complete but requires human review due to {len(critical_contradictions)} "
                f"unresolved factual contradictions (e.g. delivery address mismatch)."
            )
            is_ready = False
        elif escalation_flag:
            requires_escalation = True
            recommended_state = InvestigationState.REVIEW_REQUIRED
            rationale = (
                f"Investigation halted and escalated to human review due to insufficient verifiable evidence. "
                f"Unresolved requirements: {', '.join(missing)}."
            )
            is_ready = False
        elif not missing:
            recommended_state = InvestigationState.DECISION_READY
            is_ready = True
            rationale = (
                "All mandatory evidence requirements for Item Not Received are verified. "
                "The case package is decision-ready for human or PayPal adjudication."
            )
        else:
            recommended_state = InvestigationState.INVESTIGATING
            is_ready = False
            rationale = f"Missing {len(missing)} required evidence components: {', '.join(missing)}."

        return DecisionReadinessEvaluation(
            is_decision_ready=is_ready,
            requires_escalation=requires_escalation,
            category=DisputeCategory.ITEM_NOT_RECEIVED,
            satisfied_requirements=satisfied,
            missing_requirements=missing,
            active_contradictions=contradictions_desc,
            recommended_state=recommended_state,
            rationale=rationale,
        )

    @classmethod
    def _evaluate_snad(cls, graph: EvidenceGraph) -> DecisionReadinessEvaluation:
        satisfied = []
        missing = []
        contradictions_desc = []

        # Required: Order details, Buyer condition proof, Merchant description/listing
        if graph.get_nodes_by_type(NodeType.ORDER):
            satisfied.append("Order invoice with item specification present.")
        else:
            missing.append("Order specification.")

        evidence_items = graph.get_nodes_by_type(NodeType.EVIDENCE_ITEM)
        photo_evidence = [e for e in evidence_items if "image" in str(e.content.get("mime_type", "")) or "photo" in e.label.lower()]
        if photo_evidence:
            satisfied.append("Condition photo or unboxing evidence submitted.")
        else:
            missing.append("Photographic evidence of item condition from buyer.")

        contradictions = graph.get_contradictions()
        for src, tgt, edge in contradictions:
            contradictions_desc.append(f"Contradiction: {src.label} vs {tgt.label}")

        is_ready = len(missing) == 0 and len(contradictions_desc) == 0
        state = InvestigationState.DECISION_READY if is_ready else (
            InvestigationState.REVIEW_REQUIRED if contradictions_desc else InvestigationState.INVESTIGATING
        )

        return DecisionReadinessEvaluation(
            is_decision_ready=is_ready,
            requires_escalation=bool(contradictions_desc),
            category=DisputeCategory.SIGNIFICANTLY_NOT_AS_DESCRIBED,
            satisfied_requirements=satisfied,
            missing_requirements=missing,
            active_contradictions=contradictions_desc,
            recommended_state=state,
            rationale="SNAD evaluation completed." if is_ready else f"Missing: {', '.join(missing)}"
        )

    @classmethod
    def _evaluate_duplicate_transaction(cls, graph: EvidenceGraph) -> DecisionReadinessEvaluation:
        tx_nodes = graph.get_nodes_by_type(NodeType.TRANSACTION)
        satisfied = []
        missing = []

        if len(tx_nodes) >= 2:
            satisfied.append("Dual transaction logs captured for cross-reference.")
            is_ready = True
            state = InvestigationState.DECISION_READY
            rationale = "Duplicate charge telemetry ready for human sign-off."
        else:
            missing.append("Secondary transaction reference.")
            is_ready = False
            state = InvestigationState.INVESTIGATING
            rationale = "Awaiting secondary transaction verification."

        return DecisionReadinessEvaluation(
            is_decision_ready=is_ready,
            requires_escalation=False,
            category=DisputeCategory.DUPLICATE_TRANSACTION,
            satisfied_requirements=satisfied,
            missing_requirements=missing,
            active_contradictions=[],
            recommended_state=state,
            rationale=rationale
        )

    @classmethod
    def _evaluate_incorrect_amount(cls, graph: EvidenceGraph) -> DecisionReadinessEvaluation:
        tx_nodes = graph.get_nodes_by_type(NodeType.TRANSACTION)
        order_nodes = graph.get_nodes_by_type(NodeType.ORDER)
        satisfied = []
        missing = []

        if tx_nodes and order_nodes:
            satisfied.append("Transaction charged amount and order invoice subtotal recorded.")
            is_ready = True
            state = InvestigationState.DECISION_READY
            rationale = "Amount discrepancy reconciliation ready."
        else:
            if not tx_nodes:
                missing.append("Transaction settlement record.")
            if not order_nodes:
                missing.append("Original merchant invoice/cart amount.")
            is_ready = False
            state = InvestigationState.INVESTIGATING
            rationale = f"Awaiting records: {', '.join(missing)}"

        return DecisionReadinessEvaluation(
            is_decision_ready=is_ready,
            requires_escalation=False,
            category=DisputeCategory.INCORRECT_AMOUNT,
            satisfied_requirements=satisfied,
            missing_requirements=missing,
            active_contradictions=[],
            recommended_state=state,
            rationale=rationale
        )

    @classmethod
    def _evaluate_generic(cls, category: DisputeCategory, graph: EvidenceGraph) -> DecisionReadinessEvaluation:
        tx_nodes = graph.get_nodes_by_type(NodeType.TRANSACTION)
        return DecisionReadinessEvaluation(
            is_decision_ready=bool(tx_nodes),
            requires_escalation=False,
            category=category,
            satisfied_requirements=["Transaction record ingested"] if tx_nodes else [],
            missing_requirements=[] if tx_nodes else ["Transaction record"],
            active_contradictions=[],
            recommended_state=InvestigationState.DECISION_READY if tx_nodes else InvestigationState.INVESTIGATING,
            rationale="Generic dispute evaluation standard applied."
        )
