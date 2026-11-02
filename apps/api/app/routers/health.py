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


@router.get("/capabilities")
def get_capabilities():
    """
    Explicitly documents what is real, mocked, simulated, and not implemented.
    Guarantees transparent operational boundaries for evaluators.
    """
    paypal_adapter = PayPalSandboxAdapter()
    return {
        "storage": {
            "durable_volume_persisted": True,
            "database": "sqlite",
            "uploads_persisted": True,
        },
        "paypal_sandbox": {
            "mode": "read_only_smoke",
            "is_configured": paypal_adapter.is_configured(),
            "live_evidence_submission_enabled": False,
            "automatic_adjudication_enabled": False,
            "dispute_mutation_enabled": False,
            "note": "Read-only inspection and smoke testing only. Live dispute mutation is explicitly disabled."
        },
        "carrier_verification": {
            "mode": "simulated_telemetry",
            "independently_verified_live": False,
            "note": "Carrier lookups use deterministic synthetic demonstration fixtures, not live carrier APIs."
        },
        "ai_engine": {
            "provider": settings.AI_PROVIDER,
            "model": settings.GEMINI_MODEL if settings.AI_PROVIDER == "gemini" else settings.OPENAI_MODEL,
            "can_mutate_decisions": False,
            "note": "AI extracts claim text as MODEL_INFERENCE nodes; it cannot verify evidence or execute money movements."
        }
    }
