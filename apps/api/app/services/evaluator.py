"""Conservative evidence-package readiness: never an adjudication outcome.

A fixture can establish the state of a *simulated case*, not external truth.
Submitted records can populate a review package but their content is not verified
simply because a file was accepted. Conflicts block an unjustified handoff.
"""
from packages.shared_schemas.models import (
    DisputeCategory, InvestigationState, NodeType, EdgeType,
    EvidenceOrigin, EvidenceVerificationStatus, DecisionReadinessEvaluation,
)
from app.services.evidence_graph import EvidenceGraph
from app.services.hypothesis_engine import assess_inr_hypotheses


def _corroborated(node):
    return (
        node.verification_status == EvidenceVerificationStatus.VERIFIED
        and node.origin in (EvidenceOrigin.VERIFIED_EXTERNAL, EvidenceOrigin.SYNTHETIC_FIXTURE)
        and node.metadata.get("verification_scope") != "EXTERNAL_UNAVAILABLE"
    )


def _contradictions(graph):
    return [
        f"{src.id} conflicts with {tgt.id}: {edge.provenance}"
        for src, tgt, edge in graph.get_contradictions()
    ]


def _result(category, satisfied, missing, conflicts, explanation="", escalation=False):
    # A contradiction is never silently made "decision ready" by document count.
    review = bool(conflicts) or escalation
    state = (InvestigationState.REVIEW_REQUIRED if review else
             InvestigationState.INVESTIGATING if missing else InvestigationState.DECISION_READY)
    ready = not review and not missing
    return DecisionReadinessEvaluation(
        is_decision_ready=ready,
        requires_escalation=review,
        category=category,
        satisfied_requirements=satisfied,
        missing_requirements=missing,
        active_contradictions=conflicts,
        recommended_state=state,
        rationale=(
            ("Human review required: " if review else
             "Incomplete evidence package: " if missing else
             "Evidence package available for human adjudication review; no outcome decided. ")
            + explanation
            + (" Unresolved: " + "; ".join(missing) if missing else "")
            + (" Contradictions: " + "; ".join(conflicts) if conflicts else "")
        ),
    )


class DecisionReadinessEvaluator:
    @classmethod
    def evaluate(cls, category: DisputeCategory, graph: EvidenceGraph) -> DecisionReadinessEvaluation:
        if category == DisputeCategory.ITEM_NOT_RECEIVED:
            return cls._inr(graph)
        if category == DisputeCategory.SIGNIFICANTLY_NOT_AS_DESCRIBED:
            return cls._snad(graph)
        if category == DisputeCategory.DUPLICATE_TRANSACTION:
            return cls._duplicate(graph)
        if category == DisputeCategory.INCORRECT_AMOUNT:
            return cls._incorrect_amount(graph)
        return cls._generic(category, graph)

    @staticmethod
    def _inr(graph):
        category = DisputeCategory.ITEM_NOT_RECEIVED
        satisfied, missing, conflicts = [], [], _contradictions(graph)
        txs = [n for n in graph.get_nodes_by_type(NodeType.TRANSACTION) if _corroborated(n)]
        if txs:
            satisfied.append("Corroborated transaction record (external or explicitly simulated case).")
        else:
            missing.append("PayPal transaction record with confirmed source authority.")
        orders = graph.get_nodes_by_type(NodeType.ORDER)
        shipments = graph.get_nodes_by_type(NodeType.SHIPMENT)
        if len(orders) == 1 and isinstance(orders[0].content.get("destination_address"), dict) and orders[0].content["destination_address"].get("postal_code"):
            satisfied.append("Order postal code recorded (may be merchant-submitted).")
        else:
            missing.append("Unique merchant order with destination postal code.")
        if len(shipments) == 1 and shipments[0].content.get("tracking_number"):
            satisfied.append("Shipment tracking identifier recorded; presence alone does not verify delivery.")
        else:
            missing.append("Unique shipment tracking identifier for this order.")

        review = assess_inr_hypotheses(graph)
        statuses = {a.hypothesis_id: a.status for a in review.assessments}
        supported_match = statuses.get("carrier_delivered_to_order_postal_code") == "SUPPORTED"
        supported_wrong = statuses.get("carrier_delivered_to_other_postal_code") == "SUPPORTED"
        supported_transit = statuses.get("carrier_reports_in_transit_or_exception") == "SUPPORTED"
        if len(orders) == 1 and len(shipments) == 1:
            if supported_wrong or any(a.status == "CONFLICTED" for a in review.assessments) or (supported_match and supported_transit):
                evidence_ids = sorted({
                    item for assessment in review.assessments
                    for item in (*assessment.supporting_evidence_ids, *assessment.contradicting_evidence_ids)
                })
                conflicts.append("Carrier reports disagree with the order or with each other; evidence IDs: " + ", ".join(evidence_ids))
        if supported_match and not conflicts:
            satisfied.append(
                "Simulated carrier delivery-to-ZIP report (NOT independent verification)."
                if review.evidence_basis == "SIMULATED" else
                "Carrier verified delivery-to-ZIP scan (NOT physical receipt)."
            )
            buyer_disputes = any(n.content.get("party") == "BUYER" for n in graph.get_nodes_by_type(NodeType.CLAIM))
            linked = {
                (e.source_id, e.target_id) for e in graph.to_data().edges
                if e.type == EdgeType.RELATES_TO
            }
            proofs = [
                n for n in graph.get_nodes_by_type(NodeType.EVIDENCE_ITEM)
                if _corroborated(n)
                and n.content.get("kind") in ("signature_record", "delivery_photo", "recipient_acknowledgement")
                and (n.id, shipments[0].id) in linked
            ]
            if buyer_disputes and not proofs:
                missing.append("Buyer reports non-receipt: obtain linked carrier signature/photo or handoff documentation; ZIP scan cannot establish possession.")
            if proofs:
                satisfied.append(
                    "Linked simulated handoff fixture available for human review (NOT external verification)."
                    if all(n.origin == EvidenceOrigin.SYNTHETIC_FIXTURE for n in proofs) else
                    "Linked external handoff documentation available for human review; receipt still subject to adjudication."
                )
        elif supported_transit and not conflicts:
            missing.append("Proof of completed delivery (shipment in-transit/exception).")
        elif not conflicts:
            missing.append("Eligible, shipment-linked carrier delivery report with matching postal code.")

        escalation = any(
            "escalate" in q.id.lower() or "insufficient" in q.label.lower()
            for q in graph.get_nodes_by_type(NodeType.QUESTION)
        )
        return _result(category, satisfied, missing, list(dict.fromkeys(conflicts)),
                       "Carrier observation is not proof the buyer took possession.", escalation)

    @staticmethod
    def _snad(graph):
        category = DisputeCategory.SIGNIFICANTLY_NOT_AS_DESCRIBED
        satisfied, missing, conflicts = [], [], _contradictions(graph)
        orders = graph.get_nodes_by_type(NodeType.ORDER)
        if len(orders) == 1 and orders[0].content.get("item_name"):
            satisfied.append("Merchant order/item specification recorded; not independently authenticated.")
        else:
            missing.append("Order item specification.")

        items = graph.get_nodes_by_type(NodeType.EVIDENCE_ITEM)
        photos = [
            n for n in items
            if str(n.content.get("mime_type", "")).lower().startswith("image/")
            and n.origin in (EvidenceOrigin.USER_SUBMITTED, EvidenceOrigin.SYNTHETIC_FIXTURE, EvidenceOrigin.VERIFIED_EXTERNAL)
            and n.verification_status != EvidenceVerificationStatus.REJECTED
        ]
        if photos:
            satisfied.append("Condition photograph submitted (authenticity and content not independently verified).")
        else:
            missing.append("Buyer condition photograph/unboxing image.")

        listings = [
            n for n in items if n.content.get("kind") == "merchant_listing"
            and n.origin in (EvidenceOrigin.USER_SUBMITTED, EvidenceOrigin.SYNTHETIC_FIXTURE, EvidenceOrigin.VERIFIED_EXTERNAL)
            and n.verification_status != EvidenceVerificationStatus.REJECTED
        ]
        if listings:
            satisfied.append("Original merchant listing supplied for comparison (not proof of its accuracy).")
        else:
            missing.append("Original merchant listing/description for comparison.")
        return _result(category, satisfied, missing, conflicts,
                       "A photo plus listing enables review, not a finding of misrepresentation.")

    @staticmethod
    def _duplicate(graph):
        category = DisputeCategory.DUPLICATE_TRANSACTION
        satisfied, missing, conflicts = [], [], _contradictions(graph)
        transactions = [n for n in graph.get_nodes_by_type(NodeType.TRANSACTION) if _corroborated(n)]
        by_id = {str(n.content.get("transaction_id", "")).strip(): n for n in transactions if n.content.get("transaction_id")}
        if len(by_id) < 2:
            missing.append("Two distinct, source-corroborated payment transaction IDs (not uploaded assertions).")
        else:
            pairs = list(by_id.values())
            # A matched order reference is required before two legitimate payments
            # can be treated as a useful duplicate-charge review package.
            order_ids = {str(n.content.get("order_id", "")).strip() for n in pairs}
            amounts = {(n.content.get("amount"), n.content.get("currency")) for n in pairs}
            if "" in order_ids or len(order_ids) != 1:
                missing.append("Both transactions reconciled to the same original order reference.")
            else:
                satisfied.append("Distinct corroborated transactions reference the same order.")
            if len(amounts) != 1 or any(amt is None or not currency for amt, currency in amounts):
                missing.append("Consistent transaction amount and currency for duplicate-charge comparison.")
            else:
                satisfied.append("Both transaction amounts and currencies recorded as equal (not proof of erroneous duplication).")
        return _result(category, satisfied, missing, conflicts,
                       "A pair of charges can still represent legitimate separate transactions.")

    @staticmethod
    def _incorrect_amount(graph):
        category = DisputeCategory.INCORRECT_AMOUNT
        satisfied, missing, conflicts = [], [], _contradictions(graph)
        if any(_corroborated(n) for n in graph.get_nodes_by_type(NodeType.TRANSACTION)):
            satisfied.append("Source-corroborated settlement record present.")
        else:
            missing.append("Source-corroborated transaction settlement record.")
        if graph.get_nodes_by_type(NodeType.ORDER):
            satisfied.append("Merchant order amount recorded (possibly submitted).")
        else:
            missing.append("Original merchant order/cart amount.")
        return _result(category, satisfied, missing, conflicts,
                       "Amount comparison requires human interpretation.")

    @staticmethod
    def _generic(category, graph):
        missing = ["Category-specific evidence standard not implemented; human review required."]
        return _result(category, [], missing, _contradictions(graph),
                       "No automatic determination is supported.", escalation=True)
