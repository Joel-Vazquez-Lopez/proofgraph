import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from packages.shared_schemas.models import (
    DisputeDetail,
    InvestigationReport,
    NodeType,
    EdgeType,
    EvidenceVerificationStatus,
    EvidenceOrigin,
)
from app.services.evidence_graph import EvidenceGraph


class ReportGenerator:
    """
    Generates structured, auditable investigation packages
    ready for human dispute reviewers or PayPal adjudication.
    """

    @staticmethod
    def _is_independently_verified(node) -> bool:
        if node.verification_status != EvidenceVerificationStatus.VERIFIED:
            return False
        # Never turn scenario truth into independent external evidence, including
        # graphs stored before explicit verification_scope metadata was added.
        if node.origin == EvidenceOrigin.SYNTHETIC_FIXTURE:
            return False
        if node.metadata.get("verification_scope") == "SIMULATED_FIXTURE":
            return False
        if node.origin == EvidenceOrigin.VERIFIED_EXTERNAL:
            return True
        # An explicitly audited user-submitted document may be corroborated
        # without rewriting its original USER_SUBMITTED provenance.
        return bool(node.verified_at and node.metadata.get("verification_audit"))

    @classmethod
    def generate_report(cls, dispute: DisputeDetail) -> InvestigationReport:
        graph = EvidenceGraph.from_data(dispute.dispute_id, dispute.evidence_graph)

        # 1. Separately inventory independently corroborated observations and
        # demo fixture facts, including older seeded fixture observations.
        obs_nodes = graph.get_nodes_by_type(NodeType.OBSERVATION)
        verified_facts = [
            f"[{obs.source}] {obs.label}"
            for obs in obs_nodes
            if cls._is_independently_verified(obs)
        ]
        simulated_facts = [
            f"[SIMULATED / {obs.source}] {obs.label}"
            for obs in obs_nodes
            if obs.origin == EvidenceOrigin.SYNTHETIC_FIXTURE
        ]
        if not verified_facts:
            # A synthetic VERIFIED transaction is still a scenario assumption.
            for tx in graph.get_nodes_by_type(NodeType.TRANSACTION):
                if cls._is_independently_verified(tx):
                    verified_facts.append(f"[{tx.source}] {tx.label}")

        # 2. Unresolved questions
        open_questions = graph.get_open_questions()
        unresolved_q_texts = [q.label for q in open_questions]

        # 3. Contradictions
        contradictions = graph.get_contradictions()
        contradiction_texts = [
            f"{src.label} CONTRADICTS {tgt.label} ({edge.provenance})"
            for src, tgt, edge in contradictions
        ]

        # 4. Provenance trail
        provenance_trail = []
        for node in graph._nodes.values():
            provenance_trail.append({
                "node_id": node.id,
                "type": node.type.value,
                "label": node.label,
                "source": node.source,
                "origin": node.origin.value,
                "verification_status": node.verification_status.value,
                "verification_scope": node.metadata.get(
                    "verification_scope",
                    "SIMULATED_FIXTURE" if node.origin == EvidenceOrigin.SYNTHETIC_FIXTURE
                    else "INDEPENDENT_EXTERNAL" if cls._is_independently_verified(node)
                    else "UNVERIFIED",
                ),
                "independently_verified": cls._is_independently_verified(node),
                "created_at": node.created_at,
            })

        # 5. Executive summary
        status_label = dispute.state.value
        readiness_note = dispute.readiness.rationale
        exec_summary = (
            f"Case {dispute.dispute_id} ({dispute.category.value}) is in state {status_label}. "
            f"Total disputed amount: {dispute.amount:.2f} {dispute.currency}. "
            f"{readiness_note}"
            + (
                " This is a synthetic demo case; fixture observations are simulated "
                "and are not independently verified external facts."
                if dispute.data_source.value == "SYNTHETIC_FIXTURE" else ""
            )
        )

        return InvestigationReport(
            report_id=f"rep_{uuid.uuid4().hex[:12]}",
            generated_at=datetime.now(timezone.utc).isoformat(),
            dispute_id=dispute.dispute_id,
            category=dispute.category,
            final_state=dispute.state,
            data_source=dispute.data_source,
            executive_summary=exec_summary,
            verified_facts=verified_facts,
            simulated_facts=simulated_facts,
            unresolved_questions=unresolved_q_texts,
            identified_contradictions=contradiction_texts,
            missing_evidence_inventory=dispute.readiness.missing_requirements,
            evidence_provenance_trail=provenance_trail,
            integrity_findings=dispute.integrity_findings,
            readiness_evaluation=dispute.readiness,
            recommended_adjudication_handoff=(
                "APPROVE_REVIEW" if dispute.readiness.is_decision_ready
                else "ESCALATE_TO_SENIOR_REVIEWER" if dispute.readiness.requires_escalation
                else "CONTINUE_EVIDENCE_GATHERING"
            ),
        )

    @classmethod
    def to_markdown(cls, report: InvestigationReport) -> str:
        md = []
        md.append(f"# PayPal AI Dispute Investigation Package")
        md.append(f"**Report ID:** `{report.report_id}`  ")
        md.append(f"**Case ID:** `{report.dispute_id}` | **Category:** `{report.category.value}`  ")
        md.append(f"**Generated:** `{report.generated_at}` | **Investigation State:** `{report.final_state.value}`  ")
        md.append(f"**Data Source:** `{report.data_source.value}`  \n")
        
        md.append("---")
        md.append("## 1. Executive Summary")
        md.append(f"{report.executive_summary}\n")

        md.append("## 2. Decision-Readiness Status")
        md.append(f"- **Decision Ready:** `{'YES' if report.readiness_evaluation.is_decision_ready else 'NO'}`")
        md.append(f"- **Escalation Required:** `{'YES' if report.readiness_evaluation.requires_escalation else 'NO'}`")
        md.append(f"- **Handoff Recommendation:** `{report.recommended_adjudication_handoff}`")
        md.append(f"- **Readiness Rationale:** {report.readiness_evaluation.rationale}\n")

        md.append("## 3. Independently Verified Factual Observations")
        if report.verified_facts:
            for fact in report.verified_facts:
                md.append(f"- [x] {fact}")
        else:
            md.append("*No independently verified observations recorded yet.*")
        md.append("")

        md.append("## 3A. Simulated Demo Observations (NOT Externally Verified)")
        if report.simulated_facts:
            for fact in report.simulated_facts:
                md.append(f"- [SIMULATED] {fact}")
        else:
            md.append("*No simulated carrier observations recorded.*")
        md.append("")

        md.append("## 4. Contradictions & Discrepancies")
        if report.identified_contradictions:
            for c in report.identified_contradictions:
                md.append(f"- ⚠️ **CONTRADICTION:** {c}")
        else:
            md.append("*No active contradictions identified.*")
        md.append("")

        md.append("## 5. Missing Evidence Requirements")
        if report.missing_evidence_inventory:
            for item in report.missing_evidence_inventory:
                md.append(f"- [ ] **MISSING:** {item}")
        else:
            md.append("*All primary category requirements satisfied.*")
        md.append("")

        if report.integrity_findings:
            md.append("## 6. Document & Image Integrity Audit")
            for f in report.integrity_findings:
                md.append(f"- **File:** `{f.file_name}` (`{f.mime_type}`) | **Status:** `{f.integrity_status.value}`")
                md.append(f"  - SHA-256: `{f.sha256_hash}`")
                md.append(f"  - Finding: {f.findings_summary}")
                md.append(f"  - Epistemic note: *{f.probabilistic_uncertainty_note}*")
            md.append("")

        md.append("## 7. Traceable Provenance Inventory")
        md.append("| Node ID | Type | Label | Source | Origin | Verification | Scope |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for p in report.evidence_provenance_trail:
            md.append(
                f"| `{p['node_id']}` | {p['type']} | {p['label']} | {p['source']} | "
                f"`{p['origin']}` | `{p['verification_status']}` | `{p['verification_scope']}` |"
            )
        md.append("")

        md.append("---")
        md.append(f"> **Notice:** {report.disclaimer}")
        return "\n".join(md)
