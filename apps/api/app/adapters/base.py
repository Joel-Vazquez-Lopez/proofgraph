from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class DisputeAdapter(ABC):
    @abstractmethod
    def list_disputes(self) -> List[Dict[str, Any]]:
        """List incoming disputes from source."""
        pass

    @abstractmethod
    def get_dispute(self, dispute_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full dispute details by ID."""
        pass

    @abstractmethod
    def submit_evidence(self, dispute_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit evidence package to upstream processor."""
        pass
