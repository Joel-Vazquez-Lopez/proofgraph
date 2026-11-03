import base64
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response
from sqlalchemy.orm import Session

from app.models.db_models import get_db, DisputeCaseDB
from app.services.dispute_service import DisputeService
from app.security.auth import verify_case_access, get_current_user, enforce_submitter_role, AuthContext
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
    auth: AuthContext = Depends(get_current_user),
    case: DisputeCaseDB = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    service = DisputeService(db)
    submission.submitter_role = enforce_submitter_role(auth, submission.submitter_role)
    try:
        return service.process_evidence_submission(dispute_id, submission)
    except HTTPException:
        # Preserve validator status codes, in particular 413 for oversized files.
        raise
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    auth: AuthContext = Depends(get_current_user),
    case: DisputeCaseDB = Depends(verify_case_access),
    db: Session = Depends(get_db),
):
    service = DisputeService(db)
    clean_role = enforce_submitter_role(auth, submitter_role)
    
    # Secure streaming read, size limit (10MB), and magic byte verification
    file_bytes, verified_mime, safe_filename = await validate_and_read_upload(file)
    b64_data = base64.b64encode(file_bytes).decode("utf-8")

    submission = EvidenceSubmissionRequest(
        action_id=action_id,
        submitter_role=clean_role,
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{dispute_id}/evidence/{evidence_id}/download")
def download_evidence_file(
    dispute_id: str,
    evidence_id: str,
    case: DisputeCaseDB = Depends(verify_case_access),
    db: Session = Depends(get_db)
):
    """
    Downloads original durable evidence file bytes.
    Enforces tenant case access and verifies SHA-256 integrity before returning bytes.
    """
    service = DisputeService(db)
    try:
        file_bytes, mime_type, file_name, sha256_hash = service.get_evidence_file(dispute_id, evidence_id)
        return Response(
            content=file_bytes,
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}"',
                "X-Evidence-SHA256": sha256_hash,
            }
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=f"Evidence file integrity failure: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
