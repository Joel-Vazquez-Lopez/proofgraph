from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from app.adapters.base import DisputeAdapter
from packages.shared_schemas.models import DisputeCategory


class SyntheticDisputeAdapter(DisputeAdapter):
    """
    Deterministic synthetic dispute adapter.
    Supplies realistic scenarios with explicit `is_synthetic: True` markers.
    Used for local testing, CI/CD, and repeatable benchmarking.
    """

    def __init__(self):
        self._scenarios: Dict[str, Dict[str, Any]] = self._build_synthetic_dataset()

    def _build_synthetic_dataset(self) -> Dict[str, Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        two_days_ago = (now - timedelta(days=2)).isoformat()
        four_days_ago = (now - timedelta(days=4)).isoformat()
        five_days_ago = (now - timedelta(days=5)).isoformat()

        return {
            "PP-D-INR-8841": {
                "dispute_id": "PP-D-INR-8841",
                "category": DisputeCategory.ITEM_NOT_RECEIVED.value,
                "amount": 189.99,
                "currency": "USD",
                "buyer_id": "payer_sarah_connor_99",
                "seller_id": "merchant_cyber_dyne_retail",
                "transaction_id": "TX-998811223344",
                "created_at": two_days_ago,
                "updated_at": two_days_ago,
                "buyer_claim": "I ordered a mechanical keychron keyboard on Oct 2nd for $189.99. It has been 8 days and no package ever arrived at my address. Merchant has not replied to my emails.",
                "seller_response": "We packaged and sent this order via USPS immediately. Let me check the shipping logs.",
                "is_synthetic": True,
                "order_details": {
                    "order_id": "ORD-2026-8841",
                    "destination_address": {
                        "street": "742 Evergreen Terrace",
                        "city": "Springfield",
                        "state": "OR",
                        "postal_code": "97477",
                        "country": "US"
                    },
                    "item_sku": "KEYCHRON-Q1-PRO",
                    "item_name": "Keychron Q1 Pro Wireless Mechanical Keyboard",
                    "subtotal": 189.99,
                    "order_date": five_days_ago
                },
                "preexisting_shipment": None,  # Merchant hasn't provided tracking yet!
            },
            "PP-D-INR-9923": {
                "dispute_id": "PP-D-INR-9923",
                "category": DisputeCategory.ITEM_NOT_RECEIVED.value,
                "amount": 349.00,
                "currency": "USD",
                "buyer_id": "payer_alex_rivera_12",
                "seller_id": "merchant_audio_vault",
                "transaction_id": "TX-774411002233",
                "created_at": two_days_ago,
                "updated_at": two_days_ago,
                "buyer_claim": "The seller says the package was delivered, but UPS delivered it to Seattle WA instead of my Portland OR address. I live at 100 Main St, Portland OR 97201.",
                "seller_response": "Tracking shows delivered. No refund.",
                "is_synthetic": True,
                "order_details": {
                    "order_id": "ORD-2026-9923",
                    "destination_address": {
                        "street": "100 Main St",
                        "city": "Portland",
                        "state": "OR",
                        "postal_code": "97201",
                        "country": "US"
                    },
                    "item_sku": "SONY-WH-1000XM5",
                    "item_name": "Sony WH-1000XM5 Noise Canceling Headphones",
                    "subtotal": 349.00,
                    "order_date": four_days_ago
                },
                "preexisting_shipment": {
                    "carrier_name": "UPS",
                    "tracking_number": "1Z9999999912345678",
                    "status": "DELIVERED",
                    "delivered_to_address": {
                        "city": "Seattle",
                        "state": "WA",
                        "postal_code": "98101"
                    },
                    "delivery_date": two_days_ago
                }
            },
            "PP-D-SNAD-3012": {
                "dispute_id": "PP-D-SNAD-3012",
                "category": DisputeCategory.SIGNIFICANTLY_NOT_AS_DESCRIBED.value,
                "amount": 420.00,
                "currency": "USD",
                "buyer_id": "payer_elena_rostova_44",
                "seller_id": "merchant_vintage_optics",
                "transaction_id": "TX-556677889900",
                "created_at": two_days_ago,
                "updated_at": two_days_ago,
                "buyer_claim": "Item was advertised as 'Mint Condition Camera Lens'. It arrived with a deep diagonal scratch across the front element and loose focus ring.",
                "seller_response": "The lens was in pristine condition when packaged with bubble wrap.",
                "is_synthetic": True,
                "order_details": {
                    "order_id": "ORD-2026-3012",
                    "destination_address": {
                        "street": "12 Ocean Drive",
                        "city": "Miami",
                        "state": "FL",
                        "postal_code": "33139",
                        "country": "US"
                    },
                    "item_sku": "LEICA-50MM-F2",
                    "item_name": "Leica Summicron-M 50mm f/2 Lens (Used)",
                    "subtotal": 420.00,
                    "order_date": five_days_ago
                },
                "preexisting_shipment": {
                    "carrier_name": "FedEx",
                    "tracking_number": "987654321012",
                    "status": "DELIVERED",
                    "delivered_to_address": {
                        "city": "Miami",
                        "state": "FL",
                        "postal_code": "33139"
                    },
                    "delivery_date": two_days_ago
                }
            },
            "PP-D-DUP-4044": {
                "dispute_id": "PP-D-DUP-4044",
                "category": DisputeCategory.DUPLICATE_TRANSACTION.value,
                "amount": 49.50,
                "currency": "USD",
                "buyer_id": "payer_david_kim_08",
                "seller_id": "merchant_coffee_roasters",
                "transaction_id": "TX-112233445566",
                "created_at": two_days_ago,
                "updated_at": two_days_ago,
                "buyer_claim": "I was charged twice for the exact same order of coffee beans within 4 seconds due to a website checkout glitch.",
                "seller_response": "Checking merchant transaction log.",
                "is_synthetic": True,
                "order_details": {
                    "order_id": "ORD-2026-4044",
                    "destination_address": {
                        "street": "500 Elm St",
                        "city": "Austin",
                        "state": "TX",
                        "postal_code": "78701",
                        "country": "US"
                    },
                    "item_sku": "ESPRESSO-BLEND-2KG",
                    "item_name": "Artisan Espresso Blend 2kg",
                    "subtotal": 49.50,
                    "order_date": two_days_ago
                },
                "duplicate_tx_id": "TX-112233445567"
            }
        }

    def list_disputes(self) -> List[Dict[str, Any]]:
        return list(self._scenarios.values())

    def get_dispute(self, dispute_id: str) -> Optional[Dict[str, Any]]:
        return self._scenarios.get(dispute_id)

    def submit_evidence(self, dispute_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "SUCCESS",
            "dispute_id": dispute_id,
            "message": "Simulated evidence successfully recorded in test harness.",
            "is_synthetic": True
        }
