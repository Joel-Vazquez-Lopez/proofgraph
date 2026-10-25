"""Explicit reviewer-initiated model analysis, separate from readiness/NBE policy."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.db_models import DisputeCaseDB, get_db
from app.security.auth import require_consequential_action_permission, verify_case_access, AuthContext
from app.services.ai_claim_extractor import AIClaimResult, extract_claims
from app.services.evidence_graph import EvidenceGraph


router = APIRouter(prefix="/disputes", tags=["AI assistance"])


@router.post("/{dispute_id}/ai/extract", response_model=AIClaimResult)
def extract_dispute_claims(
    dispute_id: str,
    case: DisputeCaseDB = Depends(verify_case_access),
    reviewer: AuthContext = Depends(require_consequential_action_permission),
    db: Session = Depends(get_db),
):
    # Explicit, privileged click only: sending claim text to an external AI
    # provider requires reviewer/admin access, not a buyer/merchant action.
    graph = EvidenceGraph.from_data(dispute_id, json.loads(case.graph_json or '{"nodes":[],"edges":[]}'))
    cached = json.loads(case.policy_decision_json or "{}")
    chosen = cached.get("chosen_action") or {}
    result = extract_claims(case, graph, chosen.get("action_id"))
    if result.status in ("MODEL_SUCCESS", "MODEL_PARTIAL"):
        # Derived MODEL_INFERENCE nodes are informational; unlike an OBSERVATION
        # they are never promoted to VERIFIED, and readiness is not recomputed.
        case.graph_json = json.dumps(graph.to_data().model_dump())
        timeline = json.loads(case.timeline_json or "[]")
        timeline.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": "AI_ASSISTANCE",
            "action": "Quote-grounded model claim extraction (unverified)",
            "state_transition": f"{case.state} -> {case.state}",
            "notes": (
                f"{result.provider.upper()} model {result.model}; extracted {len(result.claims)} unverified "
                f"assertion(s), rejected {result.rejected_items}; no adjudication or policy change."
            ),
        })
        case.timeline_json = json.dumps(timeline)
        db.commit()
    return result
