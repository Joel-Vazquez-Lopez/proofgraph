from typing import List
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.models.db_models import get_db, DisputeCaseDB
from app.services.dispute_service import DisputeService
from app.services.report_generator import ReportGenerator
from app.security.auth import get_current_user, verify_case_access, AuthContext, UserRole
from packages.shared_schemas.models import (
    DisputeSummary,
    DisputeDetail,
    EvidenceGraphData,
    InvestigationReport,
)

router = APIRouter(prefix="/disputes", tags=["Disputes"])


@router.get("", response_model=List[DisputeSummary])
def list_disputes(
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = DisputeService(db)
    all_disputes = service.list_disputes()
    
    # Tenancy filtering based on authenticated role
    if auth.role in (UserRole.REVIEWER, UserRole.SYSTEM_ADMIN):
        return all_disputes
    elif auth.role == UserRole.BUYER:
        return [d for d in all_disputes if d.buyer_id == auth.user_id]
    elif auth.role == UserRole.MERCHANT:
        return [d for d in all_disputes if d.seller_id == auth.user_id]
    return []


@router.get("/{dispute_id}", response_model=DisputeDetail)
def get_dispute(
    dispute_id: str,
    case: DisputeCaseDB = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    service = DisputeService(db)
    detail = service.get_dispute(dispute_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")
    return detail


@router.get("/{dispute_id}/graph", response_model=EvidenceGraphData)
def get_evidence_graph(
    dispute_id: str,
    case: DisputeCaseDB = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    service = DisputeService(db)
    detail = service.get_dispute(dispute_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")
    return detail.evidence_graph


@router.get("/{dispute_id}/report", response_model=InvestigationReport)
def get_investigation_report(
    dispute_id: str,
    case: DisputeCaseDB = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    service = DisputeService(db)
    detail = service.get_dispute(dispute_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")
    return ReportGenerator.generate_report(detail)


@router.get("/{dispute_id}/report/markdown")
def get_investigation_report_markdown(
    dispute_id: str,
    case: DisputeCaseDB = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    service = DisputeService(db)
    detail = service.get_dispute(dispute_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")
    report = ReportGenerator.generate_report(detail)
    md_text = ReportGenerator.to_markdown(report)
    return Response(content=md_text, media_type="text/markdown")
