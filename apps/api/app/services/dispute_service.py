import json
import base64
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from packages.shared_schemas.models import (
    DisputeCategory,
    InvestigationState,
    DataSourceType,
    NodeType,
    EdgeType,
    EvidenceOrigin,
    EvidenceVerificationStatus,
    DisputeSummary,
    DisputeDetail,
    EvidenceSubmissionRequest,
    EvidenceSubmissionResult,
    DecisionReadinessEvaluation,
    PolicyDecision,
    EvidenceIntegrityFinding,
)
from app.models.db_models import DisputeCaseDB, EvidenceItemDB
from app.services.state_machine import InvestigationStateMachine
from app.services.evidence_graph import EvidenceGraph
from app.services.evaluator import DecisionReadinessEvaluator
from app.services.nbe_policy import HeuristicNBEPolicy
from app.services.image_integrity import EvidenceIntegrityAnalyzer
from app.security.file_validator import validate_and_decode_base64_upload
from app.services.carrier_service import CarrierVerificationService, CarrierVerificationResult
from app.adapters.synthetic import SyntheticDisputeAdapter
from app.adapters.paypal_sandbox import PayPalSandboxAdapter


class DisputeService:
    def __init__(self, db: Session):
        self.db = db
        self.synthetic_adapter = SyntheticDisputeAdapter()
        self.paypal_adapter = PayPalSandboxAdapter()
        self.nbe_policy = HeuristicNBEPolicy()

    def list_disputes(self) -> List[DisputeSummary]:
        self._ensure_seed_scenarios()
        cases = self.db.query(DisputeCaseDB).all()
        summaries = []
        for c in cases:
            readiness = json.loads(c.readiness_json or "{}")
            graph_data = json.loads(c.graph_json or "{}")
            nodes = graph_data.get("nodes", [])
            open_q = len([n for n in nodes if n.get("type") == NodeType.QUESTION.value])
            order_node = next((n for n in nodes if n.get("type") == NodeType.ORDER.value), None)
            item_name = order_node.get("content", {}).get("item_name") if order_node else None
            buyer_name = self._format_buyer_name(c.buyer_id)
            
            summaries.append(DisputeSummary(
                dispute_id=c.dispute_id,
                category=DisputeCategory(c.category),
                state=InvestigationState(c.state),
                data_source=DataSourceType(c.data_source),
                amount=c.amount,
                currency=c.currency,
                buyer_id=c.buyer_id,
                seller_id=c.seller_id,
                created_at=c.created_at.isoformat() if hasattr(c.created_at, "isoformat") else str(c.created_at),
                updated_at=c.updated_at.isoformat() if hasattr(c.updated_at, "isoformat") else str(c.updated_at),
                open_questions_count=open_q,
                is_decision_ready=readiness.get("is_decision_ready", False),
                item_name=item_name,
                buyer_name=buyer_name,
            ))
        return summaries

    @staticmethod
    def _format_buyer_name(buyer_id: str) -> str:
        s = buyer_id.replace("payer_", "").replace("user_", "")
        import re
        s = re.sub(r'_\d+$', '', s)
        return " ".join(word.capitalize() for word in s.split("_"))

    def get_dispute(self, dispute_id: str) -> Optional[DisputeDetail]:
        self._ensure_seed_scenarios()
        c = self.db.query(DisputeCaseDB).filter(DisputeCaseDB.dispute_id == dispute_id).first()
        if not c:
            return None
        
        graph_data = json.loads(c.graph_json or '{"nodes":[],"edges":[]}')
        policy_data = json.loads(c.policy_decision_json or "{}")
        readiness_data = json.loads(c.readiness_json or "{}")
        timeline = json.loads(c.timeline_json or "[]")
        integrity_findings = json.loads(c.integrity_findings_json or "[]")

        nodes = graph_data.get("nodes", [])
        order_node = next((n for n in nodes if n.get("type") == NodeType.ORDER.value), None)
        item_name = order_node.get("content", {}).get("item_name") if order_node else None
        buyer_name = self._format_buyer_name(c.buyer_id)

        return DisputeDetail(
            dispute_id=c.dispute_id,
            category=DisputeCategory(c.category),
            state=InvestigationState(c.state),
            data_source=DataSourceType(c.data_source),
            amount=c.amount,
            currency=c.currency,
            buyer_id=c.buyer_id,
            seller_id=c.seller_id,
            transaction_id=c.transaction_id,
            created_at=c.created_at.isoformat() if hasattr(c.created_at, "isoformat") else str(c.created_at),
            updated_at=c.updated_at.isoformat() if hasattr(c.updated_at, "isoformat") else str(c.updated_at),
            buyer_claim=c.buyer_claim,
            seller_response=c.seller_response,
            evidence_graph=graph_data,
            current_policy_decision=policy_data if policy_data else None,
            readiness=DecisionReadinessEvaluation(**readiness_data) if readiness_data else DecisionReadinessEvaluator.evaluate(DisputeCategory(c.category), EvidenceGraph(dispute_id)),
            timeline=timeline,
            integrity_findings=[EvidenceIntegrityFinding(**f) for f in integrity_findings],
            item_name=item_name,
            buyer_name=buyer_name,
        )

    def process_evidence_submission(
        self,
        dispute_id: str,
        submission: EvidenceSubmissionRequest
    ) -> EvidenceSubmissionResult:
        case = self.db.query(DisputeCaseDB).filter(DisputeCaseDB.dispute_id == dispute_id).first()
        if not case:
            raise KeyError(f"Dispute {dispute_id} not found.")

        current_state = InvestigationState(case.state)
        # Transition to INVESTIGATING if currently AWAITING_EVIDENCE
        if current_state == InvestigationState.AWAITING_EVIDENCE:
            current_state = InvestigationStateMachine.transition(current_state, InvestigationState.INVESTIGATING)

        graph_dict = json.loads(case.graph_json or '{"nodes":[],"edges":[]}')
        graph = EvidenceGraph.from_data(dispute_id, graph_dict)
        nodes_created: List[str] = []
        edges_created: List[str] = []
        integrity_finding: Optional[EvidenceIntegrityFinding] = None

        evidence_item_id = f"ev_{uuid.uuid4().hex[:8]}"

        # JSON and multipart ingestion share the same decoded byte-size limit,
        # extension, detected signature, and declared MIME checks.
        if any(value is not None for value in (
            submission.file_data_base64, submission.file_name, submission.mime_type
        )):
            if not all(value is not None for value in (
                submission.file_data_base64, submission.file_name, submission.mime_type
            )):
                raise ValueError("file_data_base64, file_name and mime_type must be provided together.")
            file_bytes, mime, safe_name = validate_and_decode_base64_upload(
                submission.file_data_base64, submission.file_name, submission.mime_type
            )
            integrity_finding = EvidenceIntegrityAnalyzer.analyze_image_bytes(
                file_bytes=file_bytes,
                file_name=safe_name,
                mime_type=mime,
                file_id=evidence_item_id
            )
            # Add EVIDENCE_ITEM node
            ev_node = graph.add_node(
                node_type=NodeType.EVIDENCE_ITEM,
                label=f"Uploaded File: {safe_name}",
                content={
                    "file_name": safe_name,
                    "mime_type": mime,
                    "sha256": integrity_finding.sha256_hash,
                    "status": integrity_finding.integrity_status.value,
                },
                source=f"{submission.submitter_role}_UPLOAD",
                node_id=evidence_item_id,
                origin=EvidenceOrigin.USER_SUBMITTED,
                verification_status=EvidenceVerificationStatus.VERIFIED,
                metadata={"integrity": integrity_finding.model_dump()}
            )
            nodes_created.append(ev_node.id)

        # Handle carrier tracking submission
        if submission.tracking_number and submission.carrier_name:
            tracking_clean = submission.tracking_number.strip()
            carrier_clean = submission.carrier_name.strip()
            
            # 1. Add/Update SHIPMENT node with origin USER_SUBMITTED and status UNVERIFIED
            ship_node_id = f"ship_{carrier_clean.lower()}_{tracking_clean[-4:]}"
            existing_ship = graph.get_node(ship_node_id)
            if not existing_ship:
                ship_node = graph.add_node(
                    node_type=NodeType.SHIPMENT,
                    label=f"Submitted Shipment: {carrier_clean} #{tracking_clean}",
                    content={"carrier_name": carrier_clean, "tracking_number": tracking_clean},
                    source=f"{submission.submitter_role}_SUBMISSION",
                    origin=EvidenceOrigin.USER_SUBMITTED,
                    verification_status=EvidenceVerificationStatus.UNVERIFIED,
                    node_id=ship_node_id,
                )
                nodes_created.append(ship_node.id)
                order_nodes = graph.get_nodes_by_type(NodeType.ORDER)
                if order_nodes:
                    graph.add_edge(
                        order_nodes[0].id,
                        ship_node.id,
                        EdgeType.RELATES_TO,
                        "Merchant submitted tracking for order."
                    )
            else:
                ship_node = existing_ship

            # Close open question asking for merchant tracking
            for q in graph.get_open_questions():
                if "tracking" in q.label.lower() or "act_merchant_tracking" in q.id:
                    edge_ans = graph.add_edge(
                        source_id=ship_node.id,
                        target_id=q.id,
                        edge_type=EdgeType.ANSWERS,
                        provenance=f"Merchant provided tracking identifier: {tracking_clean}"
                    )
                    edges_created.append(edge_ans.id)

            # 2. Independent Carrier Verification Gate:
            # A tracking number alone NEVER establishes delivery.
            # Carrier verification occurs ONLY if explicitly requested or authorized.
            if submission.verify_carrier_now or submission.action_id == "act_carrier_lookup":
                carrier_nodes, carrier_edges = self._perform_carrier_verification_internal(
                    graph=graph,
                    ship_node=ship_node,
                    carrier_name=carrier_clean,
                    tracking_number=tracking_clean,
                    case_data_source=DataSourceType(case.data_source)
                )
                nodes_created.extend(carrier_nodes)
                edges_created.extend(carrier_edges)

        # Close any open question nodes answered by this submission
        open_questions = graph.get_open_questions()
        for q in open_questions:
            if nodes_created:
                edge_ans = graph.add_edge(
                    source_id=nodes_created[0],
                    target_id=q.id,
                    edge_type=EdgeType.ANSWERS,
                    provenance=f"Submitted evidence directly addresses question: {q.label}"
                )
                edges_created.append(edge_ans.id)

        # Run Decision-Readiness Evaluator
        readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory(case.category), graph)

        # Transition State Machine based on evaluator
        new_state = InvestigationStateMachine.transition(current_state, readiness.recommended_state)

        # Update NBE Policy Decision
        policy_decision = self.nbe_policy.evaluate_candidates(DisputeCategory(case.category), graph, readiness)

        # Update Timeline
        timeline = json.loads(case.timeline_json or "[]")
        timeline.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": submission.submitter_role,
            "action": f"Submitted evidence ({', '.join(nodes_created)})",
            "state_transition": f"{current_state.value} -> {new_state.value}",
            "notes": submission.notes or "Evidence processed."
        })

        # Save to DB
        case.state = new_state.value
        case.graph_json = json.dumps(graph.to_data().model_dump())
        case.readiness_json = json.dumps(readiness.model_dump())
        case.policy_decision_json = json.dumps(policy_decision.model_dump())
        case.timeline_json = json.dumps(timeline)

        if integrity_finding:
            curr_findings = json.loads(case.integrity_findings_json or "[]")
            curr_findings.append(integrity_finding.model_dump())
            case.integrity_findings_json = json.dumps(curr_findings)

        self.db.commit()

        return EvidenceSubmissionResult(
            success=True,
            evidence_id=evidence_item_id,
            nodes_created=nodes_created,
            edges_created=edges_created,
            previous_state=current_state,
            new_state=new_state,
            readiness=readiness,
            integrity_finding=integrity_finding,
            message=f"Evidence ingested successfully. Case transitioned to {new_state.value}."
        )

    def _perform_carrier_verification_internal(
        self,
        graph: EvidenceGraph,
        ship_node,
        carrier_name: str,
        tracking_number: str,
        case_data_source: DataSourceType
    ) -> tuple[list[str], list[str]]:
        nodes_created = []
        edges_created = []

        result: CarrierVerificationResult = CarrierVerificationService.verify_tracking(
            carrier_name=carrier_name,
            tracking_number=tracking_number,
            case_data_source=case_data_source
        )

        obs_id = f"obs_carrier_{tracking_number[-4:]}"
        is_verified = result.status in ("DELIVERED", "IN_TRANSIT", "EXCEPTION")
        
        obs_node = graph.add_node(
            node_type=NodeType.OBSERVATION,
            label=f"Carrier Telemetry: {result.status} ({carrier_name} #{tracking_number})",
            content=result.model_dump(),
            source=result.verification_source,
            origin=result.origin,
            verification_status=EvidenceVerificationStatus.VERIFIED if is_verified else EvidenceVerificationStatus.UNVERIFIED,
            verified_at=datetime.now(timezone.utc).isoformat() if is_verified else None,
            node_id=obs_id,
            metadata={"audit": result.audit_note}
        )
        nodes_created.append(obs_node.id)

        # Provenance: Link Observation -> Shipment
        edge_derived = graph.add_edge(
            source_id=obs_node.id,
            target_id=ship_node.id,
            edge_type=EdgeType.DERIVED_FROM,
            provenance=f"Carrier telemetry scan verified via {result.verification_source}"
        )
        edges_created.append(edge_derived.id)

        # Address reconciliation
        if result.status == "DELIVERED":
            order_nodes = graph.get_nodes_by_type(NodeType.ORDER)
            order_dest = order_nodes[0].content.get("destination_address", {}) if order_nodes else {}
            dest_zip = str(order_dest.get("postal_code", "")).strip()

            delivered_zip = ""
            if result.delivered_to_address:
                delivered_zip = str(result.delivered_to_address.get("postal_code", "")).strip()

            if dest_zip and delivered_zip and dest_zip != delivered_zip:
                # Contradiction: Delivered to wrong postal code!
                if order_nodes:
                    edge_contra = graph.add_edge(
                        source_id=obs_node.id,
                        target_id=order_nodes[0].id,
                        edge_type=EdgeType.CONTRADICTS,
                        provenance=f"Destination Mismatch: Carrier delivered to ZIP {delivered_zip}, but buyer order specified ZIP {dest_zip}."
                    )
                    edges_created.append(edge_contra.id)
            elif dest_zip and delivered_zip and dest_zip == delivered_zip:
                # Address matched: verify the shipment node through explicit auditable event
                graph.verify_node(
                    node_id=ship_node.id,
                    verifier_source=result.verification_source,
                    origin=result.origin,
                    audit_note=f"Carrier confirmed delivery to matching destination postal code {dest_zip}"
                )

        # Close open question for carrier lookup if present
        for q in graph.get_open_questions():
            if "carrier" in q.label.lower() or "act_carrier_lookup" in q.id:
                edge_ans = graph.add_edge(
                    source_id=obs_node.id,
                    target_id=q.id,
                    edge_type=EdgeType.ANSWERS,
                    provenance=f"Carrier query completed: status {result.status}"
                )
                edges_created.append(edge_ans.id)

        return nodes_created, edges_created

    def verify_carrier_shipment(self, dispute_id: str) -> EvidenceSubmissionResult:
        """
        Explicit, auditable endpoint/method to execute carrier verification on an existing shipment.
        """
        case = self.db.query(DisputeCaseDB).filter(DisputeCaseDB.dispute_id == dispute_id).first()
        if not case:
            raise KeyError(f"Dispute {dispute_id} not found.")

        current_state = InvestigationState(case.state)
        graph_dict = json.loads(case.graph_json or '{"nodes":[],"edges":[]}')
        graph = EvidenceGraph.from_data(dispute_id, graph_dict)

        ship_nodes = graph.get_nodes_by_type(NodeType.SHIPMENT)
        if not ship_nodes:
            raise ValueError(f"No shipment tracking recorded on dispute {dispute_id} to verify.")

        primary_ship = ship_nodes[0]
        carrier_name = primary_ship.content.get("carrier_name", "USPS")
        tracking_number = primary_ship.content.get("tracking_number", "")

        nodes_created, edges_created = self._perform_carrier_verification_internal(
            graph=graph,
            ship_node=primary_ship,
            carrier_name=carrier_name,
            tracking_number=tracking_number,
            case_data_source=DataSourceType(case.data_source)
        )

        readiness = DecisionReadinessEvaluator.evaluate(DisputeCategory(case.category), graph)
        new_state = InvestigationStateMachine.transition(current_state, readiness.recommended_state)
        policy_decision = self.nbe_policy.evaluate_candidates(DisputeCategory(case.category), graph, readiness)

        timeline = json.loads(case.timeline_json or "[]")
        timeline.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": "CARRIER_GATEWAY",
            "action": f"Executed independent carrier verification for #{tracking_number}",
            "state_transition": f"{current_state.value} -> {new_state.value}",
            "notes": f"Verification status recorded: {readiness.rationale}"
        })

        case.state = new_state.value
        case.graph_json = json.dumps(graph.to_data().model_dump())
        case.readiness_json = json.dumps(readiness.model_dump())
        case.policy_decision_json = json.dumps(policy_decision.model_dump())
        case.timeline_json = json.dumps(timeline)
        self.db.commit()

        return EvidenceSubmissionResult(
            success=True,
            evidence_id=f"carrier_audit_{uuid.uuid4().hex[:8]}",
            nodes_created=nodes_created,
            edges_created=edges_created,
            previous_state=current_state,
            new_state=new_state,
            readiness=readiness,
            integrity_finding=None,
            message=f"Independent carrier verification executed. Case state: {new_state.value}."
        )

    def _ensure_seed_scenarios(self):
        """Seeds default synthetic scenarios into DB if empty."""
        count = self.db.query(DisputeCaseDB).count()
        if count > 0:
            return

        for raw in self.synthetic_adapter.list_disputes():
            dispute_id = raw["dispute_id"]
            category = DisputeCategory(raw["category"])
            
            # Construct initial evidence graph
            graph = EvidenceGraph(dispute_id=dispute_id)

            # 1. Root Dispute Node
            root_node = graph.add_node(
                node_type=NodeType.DISPUTE,
                label=f"Dispute {dispute_id} ({raw['amount']} {raw['currency']})",
                content={
                    "dispute_id": dispute_id,
                    "amount": raw["amount"],
                    "currency": raw["currency"],
                    "category": category.value,
                },
                source="PAYPAL_API",
                node_id=f"root_{dispute_id}",
                origin=EvidenceOrigin.SYNTHETIC_FIXTURE,
                verification_status=EvidenceVerificationStatus.VERIFIED
            )

            # 2. Transaction Node
            tx_node = graph.add_node(
                node_type=NodeType.TRANSACTION,
                label=f"Transaction {raw['transaction_id']}",
                content={
                    "transaction_id": raw["transaction_id"],
                    "amount": raw["amount"],
                    "currency": raw["currency"],
                    "payer": raw["buyer_id"],
                    "payee": raw["seller_id"],
                },
                source="PAYPAL_PAYMENTS",
                node_id=f"tx_{raw['transaction_id']}",
                origin=EvidenceOrigin.SYNTHETIC_FIXTURE,
                verification_status=EvidenceVerificationStatus.VERIFIED
            )
            graph.add_edge(root_node.id, tx_node.id, EdgeType.REFERENCES, "Dispute refers to transaction.")

            # 3. Buyer Claim Node
            claim_node = graph.add_node(
                node_type=NodeType.CLAIM,
                label=f"Buyer Claim: {category.value}",
                content={"text": raw["buyer_claim"], "party": "BUYER"},
                source="BUYER_CLAIM",
                node_id=f"claim_buyer_{dispute_id}",
                origin=EvidenceOrigin.USER_SUBMITTED,
                verification_status=EvidenceVerificationStatus.UNVERIFIED
            )
            graph.add_edge(root_node.id, claim_node.id, EdgeType.RELATES_TO, "Dispute contains buyer claim.")

            # 4. Merchant Order Node if available
            order_info = raw.get("order_details")
            if order_info:
                order_node = graph.add_node(
                    node_type=NodeType.ORDER,
                    label=f"Order {order_info['order_id']} ({order_info['item_name']})",
                    content=order_info,
                    source="MERCHANT_ERP",
                    node_id=f"order_{order_info['order_id']}",
                    origin=EvidenceOrigin.SYNTHETIC_FIXTURE,
                    verification_status=EvidenceVerificationStatus.VERIFIED
                )
                graph.add_edge(tx_node.id, order_node.id, EdgeType.REFERENCES, "Payment settled for order.")

            # 5. Preexisting shipment if any
            ship_info = raw.get("preexisting_shipment")
            if ship_info:
                ship_node = graph.add_node(
                    node_type=NodeType.SHIPMENT,
                    label=f"{ship_info['carrier_name']} #{ship_info['tracking_number']}",
                    content=ship_info,
                    source="MERCHANT_FULFILLMENT",
                    node_id=f"ship_{ship_info['carrier_name']}_{ship_info['tracking_number'][-4:]}",
                    origin=EvidenceOrigin.SYNTHETIC_FIXTURE,
                    verification_status=EvidenceVerificationStatus.VERIFIED
                )
                if order_info:
                    graph.add_edge(order_node.id, ship_node.id, EdgeType.RELATES_TO, "Order fulfilled via shipment.")

                # Add carrier delivery observation
                obs_node = graph.add_node(
                    node_type=NodeType.OBSERVATION,
                    label=f"Carrier Status: {ship_info['status']} to {ship_info['delivered_to_address']['city']}",
                    content=ship_info,
                    source="CARRIER_TELEMETRY",
                    node_id=f"obs_delivery_{ship_info['tracking_number'][-4:]}",
                    origin=EvidenceOrigin.SYNTHETIC_FIXTURE,
                    verification_status=EvidenceVerificationStatus.VERIFIED
                )
                graph.add_edge(obs_node.id, ship_node.id, EdgeType.DERIVED_FROM, "Telemetry derived from tracking.")

                # If destination addresses differ, record CONTRADICTS edge!
                order_zip = order_info.get("destination_address", {}).get("postal_code")
                deliv_zip = ship_info.get("delivered_to_address", {}).get("postal_code")
                if order_zip and deliv_zip and order_zip != deliv_zip:
                    graph.add_edge(
                        obs_node.id,
                        order_node.id,
                        EdgeType.CONTRADICTS,
                        f"Carrier delivered to ZIP {deliv_zip}, but buyer order specified ZIP {order_zip}."
                    )

            # Evaluate readiness
            readiness = DecisionReadinessEvaluator.evaluate(category, graph)
            
            # Evaluate NBE policy
            policy_decision = self.nbe_policy.evaluate_candidates(category, graph, readiness)

            # Initial state
            initial_state = InvestigationState.AWAITING_EVIDENCE if policy_decision.chosen_action else readiness.recommended_state

            # Add question node if action needed
            if policy_decision.chosen_action:
                q_node = graph.add_node(
                    node_type=NodeType.QUESTION,
                    label=policy_decision.chosen_action.title,
                    content={"action": policy_decision.chosen_action.model_dump()},
                    source="INVESTIGATION_ENGINE",
                    node_id=f"q_{policy_decision.chosen_action.action_id}",
                    origin=EvidenceOrigin.MODEL_INFERENCE,
                    verification_status=EvidenceVerificationStatus.UNVERIFIED
                )
                graph.add_edge(root_node.id, q_node.id, EdgeType.REQUIRES_VERIFICATION, "Investigation requires clarification.")

            db_case = DisputeCaseDB(
                dispute_id=dispute_id,
                category=category.value,
                state=initial_state.value,
                data_source=DataSourceType.SYNTHETIC_FIXTURE.value,
                amount=raw["amount"],
                currency=raw["currency"],
                buyer_id=raw["buyer_id"],
                seller_id=raw["seller_id"],
                transaction_id=raw["transaction_id"],
                buyer_claim=raw["buyer_claim"],
                seller_response=raw.get("seller_response"),
                graph_json=json.dumps(graph.to_data().model_dump()),
                readiness_json=json.dumps(readiness.model_dump()),
                policy_decision_json=json.dumps(policy_decision.model_dump()),
                timeline_json=json.dumps([{
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actor": "SYSTEM",
                    "action": f"Intake completed for {dispute_id}",
                    "state_transition": f"CREATED -> {initial_state.value}",
                    "notes": "Initial dispute case ingested with verified transaction and order records."
                }]),
                integrity_findings_json="[]",
            )
            self.db.add(db_case)

        self.db.commit()
