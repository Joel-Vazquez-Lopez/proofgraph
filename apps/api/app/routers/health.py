from datetime import datetime, timezone
from fastapi import APIRouter
from app.config import settings
from app.adapters.paypal_sandbox import PayPalSandboxAdapter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    paypal_adapter = PayPalSandboxAdapter()
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "paypal_sandbox_configured": paypal_adapter.is_configured(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0"
    }
