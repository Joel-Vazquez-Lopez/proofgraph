"""
Authentication and Role-Based Authorization Boundary for PayPal AI Dispute Investigator.

NOTE: This implements a lightweight development/demonstration authentication boundary
for the hackathon prototype. Production deployments must integrate an enterprise
identity provider (e.g., OAuth 2.0 PKCE / PayPal Merchant Login).
"""

from enum import Enum
from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.models.db_models import get_db, DisputeCaseDB


class UserRole(str, Enum):
    BUYER = "BUYER"
    MERCHANT = "MERCHANT"
    REVIEWER = "REVIEWER"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class AuthContext:
    def __init__(self, user_id: str, role: UserRole, is_demo_mode: bool = True):
        self.user_id = user_id
        self.role = role
        self.is_demo_mode = is_demo_mode


def get_current_user(
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> AuthContext:
    """
    Extracts current authenticated identity and role.
    In DEMO_MODE:
      Defaults to REVIEWER role when headers are absent to facilitate interactive evaluation.
    In non-demo mode (DEMO_MODE=False):
      Deny-by-default: requires valid Authorization Bearer token matching DEMO_AUTH_SECRET.
      Unauthenticated requests or untrusted role headers are rejected with 401.
    """
    if not settings.DEMO_MODE:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: DEMO_MODE is disabled."
            )
        if not settings.DEMO_AUTH_SECRET:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Non-demo mode requires configured DEMO_AUTH_SECRET credentials."
            )
        expected_bearer = f"Bearer {settings.DEMO_AUTH_SECRET}"
        if authorization.strip() != expected_bearer:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization token in non-demo mode."
            )

    role_str = (x_user_role or "REVIEWER").upper().strip()
    try:
        role = UserRole(role_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid X-User-Role: '{x_user_role}'. Valid roles are: {[r.value for r in UserRole]}"
        )

    user_id = (x_user_id or "reviewer_demo_user").strip()
    return AuthContext(user_id=user_id, role=role, is_demo_mode=settings.DEMO_MODE)


def enforce_submitter_role(auth: AuthContext, declared_role: Optional[str]) -> str:
    """
    Ensures that an authenticated BUYER or MERCHANT cannot spoof a different submitter role.
    REVIEWER and SYSTEM_ADMIN may submit on behalf of parties in demonstration workflows.
    """
    clean_declared = (declared_role or "").upper().strip()
    if auth.role == UserRole.MERCHANT and clean_declared and clean_declared != UserRole.MERCHANT.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Authenticated Merchant cannot submit evidence as '{clean_declared}'."
        )
    if auth.role == UserRole.BUYER and clean_declared and clean_declared != UserRole.BUYER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Authenticated Buyer cannot submit evidence as '{clean_declared}'."
        )
    return clean_declared or auth.role.value


def verify_case_access(
    dispute_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> DisputeCaseDB:
    """
    Enforces case-level tenancy and authorization:
    - REVIEWER and SYSTEM_ADMIN can access all cases.
    - BUYER can only access cases where case.buyer_id == auth.user_id.
    - MERCHANT can only access cases where case.seller_id == auth.user_id.
    Prevents cross-case leakage and unauthorized dispute access.
    """
    from app.services.dispute_service import DisputeService
    DisputeService(db)._ensure_seed_scenarios()

    case = db.query(DisputeCaseDB).filter(DisputeCaseDB.dispute_id == dispute_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dispute case '{dispute_id}' not found."
        )

    if auth.role in (UserRole.REVIEWER, UserRole.SYSTEM_ADMIN):
        return case

    if auth.role == UserRole.BUYER:
        if case.buyer_id != auth.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Buyer '{auth.user_id}' does not own dispute '{dispute_id}'."
            )
        return case

    if auth.role == UserRole.MERCHANT:
        if case.seller_id != auth.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Merchant '{auth.user_id}' is not the seller on dispute '{dispute_id}'."
            )
        return case

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


def require_consequential_action_permission(
    auth: AuthContext = Depends(get_current_user)
):
    """
    Guards consequential actions (adjudication handoff, case closure, manual state override).
    Restricted strictly to human reviewers or system admins.
    """
    if auth.role not in (UserRole.REVIEWER, UserRole.SYSTEM_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Consequential action requires authenticated REVIEWER or SYSTEM_ADMIN role."
        )
    return auth
