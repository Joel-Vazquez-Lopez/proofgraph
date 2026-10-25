import base64
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.models.db_models import get_db, DisputeCaseDB
from app.services.dispute_service import DisputeService
from app.security.auth import verify_case_access
from app.security.file_validator import validate_and_read_upload
from packages.shared_schemas.models import (
    EvidenceSubmissionRequest,
    EvidenceSubmissionResult,
    PolicyDecision,
)

router = APIRouter(prefix="/disputes", tags=["Evidence"])


@router.post("/{dispute_id}/evidence", response_model=EvidenceSubmissionResult)
def submit_evidence(
    dispute_id: str,
    submission: EvidenceSubmissionRequest,
    case: DisputeCaseDB = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    service = DisputeService(db)
    try:
        return service.process_evidence_submission(dispute_id, submission)
    except HTTPException:
        # Preserve validator status codes, in particular 413 for oversized files.
        raise
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{dispute_id}/upload-evidence", response_model=EvidenceSubmissionResult)
async def upload_evidence_file(
    dispute_id: str,
    file: UploadFile = File(...),
    submitter_role: str = Form("MERCHANT"),
    notes: Optional[str] = Form(None),
    carrier_name: Optional[str] = Form(None),
    tracking_number: Optional[str] = Form(None),
    action_id: Optional[str] = Form(None),
    verify_carrier_now: bool = Form(False),
    case: DisputeCaseDB = Depends(verify_case_access),
    db: Session = Depends(get_db),
):
    service = DisputeService(db)
    
    # Secure streaming read, size limit (10MB), and magic byte verification
    file_bytes, verified_mime, safe_filename = await validate_and_read_upload(file)
    b64_data = base64.b64encode(file_bytes).decode("utf-8")

    submission = EvidenceSubmissionRequest(
        action_id=action_id,
        submitter_role=submitter_role,
        notes=notes,
        carrier_name=carrier_name,
        tracking_number=tracking_number,
        verify_carrier_now=verify_carrier_now,
        file_data_base64=b64_data,
        file_name=safe_filename,
        mime_type=verified_mime,
    )

    try:
        return service.process_evidence_submission(dispute_id, submission)
    except HTTPException:
        # Preserve validator status codes, in particular 413 for oversized files.
        raise
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{dispute_id}/verify-carrier", response_model=EvidenceSubmissionResult)
def verify_carrier_shipment(
    dispute_id: str,
    case: DisputeCaseDB = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    """
    Triggers explicit independent carrier verification for shipments associated with this dispute.
    Auditable verification transition event that bridges user-submitted tracking to verified telemetry.
    """
    service = DisputeService(db)
    try:
        return service.verify_carrier_shipment(dispute_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dispute_id}/candidates", response_model=PolicyDecision)
def get_nbe_candidates(
    dispute_id: str,
    case: DisputeCaseDB = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    service = DisputeService(db)
    detail = service.get_dispute(dispute_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found.")
    if detail.current_policy_decision:
        return detail.current_policy_decision
    raise HTTPException(status_code=404, detail="No policy decision active.")
