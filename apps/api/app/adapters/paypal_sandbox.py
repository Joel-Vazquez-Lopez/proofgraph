import time
from typing import List, Dict, Any, Optional
import httpx

from app.config import settings
from app.adapters.base import DisputeAdapter


class PayPalAPIError(Exception):
    def __init__(self, status_code: int, message: str, details: Any = None):
        self.status_code = status_code
        self.message = message
        self.details = details
        super().__init__(f"PayPal API Error [{status_code}]: {message}")


class PayPalSandboxAdapter(DisputeAdapter):
    """
    Genuine REST client for PayPal Sandbox APIs.
    Communicates with https://api-m.sandbox.paypal.com using OAuth 2.0.
    """

    def __init__(self):
        self.client_id = settings.PAYPAL_CLIENT_ID
        self.client_secret = settings.PAYPAL_CLIENT_SECRET
        self.base_url = settings.PAYPAL_BASE_URL
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_access_token(self) -> str:
        if not self.is_configured():
            raise PayPalAPIError(
                status_code=401,
                message="PayPal Sandbox credentials (PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET) are not configured."
            )

        now = time.time()
        if self._access_token and now < self._token_expiry - 60:
            return self._access_token

        token_url = f"{self.base_url}/v1/oauth2/token"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    token_url,
                    auth=(self.client_id, self.client_secret),
                    data={"grant_type": "client_credentials"},
                    headers={"Accept": "application/json", "Accept-Language": "en_US"},
                )
                if resp.status_code != 200:
                    raise PayPalAPIError(
                        status_code=resp.status_code,
                        message="PayPal OAuth token request rejected by upstream."
                    )
                data = resp.json()
                if not isinstance(data, dict) or not isinstance(data.get("access_token"), str) or not data["access_token"]:
                    raise PayPalAPIError(status_code=502, message="Malformed OAuth token response.")
                self._access_token = data["access_token"]
                self._token_expiry = now + data.get("expires_in", 32400)
                return self._access_token
        except httpx.RequestError as e:
            raise PayPalAPIError(status_code=503, message="Network error connecting to PayPal.")

    def list_disputes(self) -> List[Dict[str, Any]]:
        if not self.is_configured():
            return []
        token = self._get_access_token()
        url = f"{self.base_url}/v1/customer/disputes"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code != 200:
                    raise PayPalAPIError(
                        status_code=resp.status_code,
                        message="PayPal Disputes list request rejected by upstream.",
                    )
                payload = resp.json()
                # A valid empty result is {"items": []}; missing items is not proof
                # that the merchant has zero disputes.
                if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                    raise PayPalAPIError(status_code=502, message="Unexpected Disputes list response schema.")
                return payload["items"]
        except httpx.RequestError as e:
            raise PayPalAPIError(status_code=503, message="Network error connecting to PayPal.")

    def get_dispute(self, dispute_id: str) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            return None
        token = self._get_access_token()
        url = f"{self.base_url}/v1/customer/disputes/{dispute_id}"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code == 404:
                    return None
                if resp.status_code != 200:
                    raise PayPalAPIError(
                        status_code=resp.status_code,
                        message="PayPal dispute details request rejected by upstream.",
                    )
                return resp.json()
        except httpx.RequestError as e:
            raise PayPalAPIError(status_code=503, message="Network error connecting to PayPal.")

    def submit_evidence(self, dispute_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /v1/customer/disputes/{dispute_id}/provide-evidence
        """
        if not self.is_configured():
            raise PayPalAPIError(
                status_code=401,
                message="PayPal Sandbox credentials not configured. Cannot perform live submission."
            )
        token = self._get_access_token()
        url = f"{self.base_url}/v1/customer/disputes/{dispute_id}/provide-evidence"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code not in (200, 204):
                    raise PayPalAPIError(
                        status_code=resp.status_code,
                        message="PayPal provide-evidence request rejected by upstream.",
                    )
                return resp.json() if resp.text else {"status": "SUCCESS"}
        except httpx.RequestError as e:
            raise PayPalAPIError(status_code=503, message="Network error connecting to PayPal.")
