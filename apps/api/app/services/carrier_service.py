from datetime import datetime, timezone
from typing import Dict, Any, Optional, Literal
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
    # A lookup may yield a useful fixture outcome without independently checking
    # a real carrier. Never infer external verification from delivery status alone.
    verification_outcome: Literal["SIMULATED", "UNAVAILABLE", "EXTERNALLY_VERIFIED"]
    independently_verified: bool = False


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
                audit_note=f"Simulated fixture lookup returned status: {rec['status']} ({rec.get('notes', '')}). No external carrier contacted.",
                verification_outcome="SIMULATED",
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
                verification_source="SyntheticCarrierAdapter (Simulated Fixture)",
                audit_note="Tracking number not found in the local synthetic fixture dataset; no external carrier queried.",
                verification_outcome="SIMULATED",
            )


class CarrierVerificationService:
    """
    Carrier lookup boundary. No independent external carrier provider is
    implemented. Synthetic fixture outcomes are demo-only; all other case
    sources return UNKNOWN/UNAVAILABLE without attempting an API request.
    """

    @classmethod
    def verify_tracking(
        cls,
        carrier_name: str,
        tracking_number: str,
        case_data_source: DataSourceType
    ) -> CarrierVerificationResult:
        # Only an explicitly synthetic case can query demo fixture records.
        # There is no configured external carrier adapter in this application.
        if case_data_source != DataSourceType.SYNTHETIC_FIXTURE:
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
                verification_source="CarrierGateway (UNCONFIGURED)",
                audit_note=(
                    "External carrier telemetry query unconfigured; no carrier API was contacted. "
                    "Tracking status remains UNVERIFIED. Cannot assume delivery."
                ),
                verification_outcome="UNAVAILABLE",
            )
        # Demo scenario: only consult a clearly labeled local fixture.
        return SyntheticCarrierAdapter.lookup(carrier_name, tracking_number)
