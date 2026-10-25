from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from packages.shared_schemas.models import (
    DataSourceType,
    EvidenceOrigin,
)


class CarrierVerificationResult(BaseModel):
    carrier_name: str
    tracking_number: str
    status: str  # "DELIVERED", "IN_TRANSIT", "EXCEPTION", "NOT_FOUND", "UNKNOWN"
    delivered_to_address: Optional[Dict[str, str]] = None
    delivery_timestamp: Optional[str] = None
    has_signature: bool = False
    signature_name: Optional[str] = None
    has_delivery_photo: bool = False
    origin: EvidenceOrigin
    is_synthetic: bool
    verification_source: str
    audit_note: str


class SyntheticCarrierAdapter:
    """
    Explicit, isolated carrier simulation adapter for test and demonstration fixtures.
    Synthetic evidence is strictly labeled as SYNTHETIC_FIXTURE and cannot enter real cases.
    """

    KNOWN_RECORDS: Dict[str, Dict[str, Any]] = {
        # Scenario A: Delivered to Springfield 97477 (matching order)
        "940010009999": {
            "carrier_name": "USPS",
            "status": "DELIVERED",
            "delivered_to_address": {"city": "Springfield", "state": "OR", "postal_code": "97477"},
            "has_signature": False,
            "has_delivery_photo": False,
            "notes": "Delivered to Front Door/Porch",
        },
        # Scenario A with Signature:
        "94001000_SIG": {
            "carrier_name": "USPS",
            "status": "DELIVERED",
            "delivered_to_address": {"city": "Springfield", "state": "OR", "postal_code": "97477"},
            "has_signature": True,
            "signature_name": "S. Connor",
            "has_delivery_photo": True,
            "notes": "Signed by recipient at residence",
        },
        # Scenario B: Undelivered / In-Transit
        "94001000_TRANSIT": {
            "carrier_name": "USPS",
            "status": "IN_TRANSIT",
            "delivered_to_address": None,
            "has_signature": False,
            "has_delivery_photo": False,
            "notes": "Departed Regional Facility, in transit to destination",
        },
        # Scenario B: Delivery Exception / Stuck
        "94001000_EXCEPTION": {
            "carrier_name": "USPS",
            "status": "EXCEPTION",
            "delivered_to_address": None,
            "has_signature": False,
            "has_delivery_photo": False,
            "notes": "Severe weather delay; shipment held at hub",
        },
        # Scenario D: Contradiction - Delivered to Seattle WA 98101 (wrong address)
        "1Z9999999912345678": {
            "carrier_name": "UPS",
            "status": "DELIVERED",
            "delivered_to_address": {"city": "Seattle", "state": "WA", "postal_code": "98101"},
            "has_signature": False,
            "has_delivery_photo": False,
            "notes": "Delivered to commercial loading dock in Seattle",
        },
    }

    @classmethod
    def lookup(cls, carrier_name: str, tracking_number: str) -> CarrierVerificationResult:
        rec = cls.KNOWN_RECORDS.get(tracking_number)
        now_str = datetime.now(timezone.utc).isoformat()

        if rec:
            return CarrierVerificationResult(
                carrier_name=rec.get("carrier_name", carrier_name),
                tracking_number=tracking_number,
                status=rec["status"],
                delivered_to_address=rec.get("delivered_to_address"),
                delivery_timestamp=now_str if rec["status"] == "DELIVERED" else None,
                has_signature=rec.get("has_signature", False),
                signature_name=rec.get("signature_name"),
                has_delivery_photo=rec.get("has_delivery_photo", False),
                origin=EvidenceOrigin.SYNTHETIC_FIXTURE,
                is_synthetic=True,
                verification_source="SyntheticCarrierAdapter (Simulated Fixture)",
                audit_note=f"Simulated fixture lookup returned status: {rec['status']} ({rec.get('notes', '')})",
            )
        else:
            # If tracking number is unknown to synthetic database
            return CarrierVerificationResult(
                carrier_name=carrier_name,
                tracking_number=tracking_number,
                status="NOT_FOUND",
                delivered_to_address=None,
                delivery_timestamp=None,
                has_signature=False,
                signature_name=None,
                has_delivery_photo=False,
                origin=EvidenceOrigin.SYNTHETIC_FIXTURE,
                is_synthetic=True,
                verification_source="SyntheticCarrierAdapter",
                audit_note="Carrier telemetry query: tracking number not found in carrier database.",
            )


class CarrierVerificationService:
    """
    Independent carrier verification boundary.
    Enforces that synthetic evidence CANNOT enter real PayPal cases,
    and unverified user-submitted tracking numbers remain UNVERIFIED
    unless an independent verification event takes place.
    """

    @classmethod
    def verify_tracking(
        cls,
        carrier_name: str,
        tracking_number: str,
        case_data_source: DataSourceType
    ) -> CarrierVerificationResult:
        # CRITICAL SAFETY GATE: Real cases must never query or ingest synthetic carrier data!
        if case_data_source == DataSourceType.PAYPAL_SANDBOX:
            # In sandbox/production, real carrier API is queried if configured
            # Otherwise, explicitly preserve uncertainty.
            return CarrierVerificationResult(
                carrier_name=carrier_name,
                tracking_number=tracking_number,
                status="UNKNOWN",
                delivered_to_address=None,
                delivery_timestamp=None,
                has_signature=False,
                signature_name=None,
                has_delivery_photo=False,
                origin=EvidenceOrigin.UNVERIFIED,
                is_synthetic=False,
                verification_source="PayPalSandboxCarrierGateway (Live)",
                audit_note=(
                    "External carrier telemetry query unconfigured or pending carrier sync. "
                    "Tracking status remains UNVERIFIED. Cannot assume delivery."
                ),
            )
        else:
            # Synthetic dispute case: query explicit synthetic carrier adapter
            return SyntheticCarrierAdapter.lookup(carrier_name, tracking_number)
