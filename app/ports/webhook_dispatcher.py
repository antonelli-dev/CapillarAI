"""Port for webhook notifications to clinics."""
from typing import Any, Dict, Optional, Protocol

from app.domain.job import SimulationJob


class WebhookDispatcherPort(Protocol):
    """Dispatch async notifications to clinic systems."""
    
    def send_job_completed(
        self,
        webhook_url: str,
        job: SimulationJob,
        retry_count: int = 3,
    ) -> int:
        """
        Notify clinic that job is complete.
        
        Args:
            webhook_url: Clinic's callback URL
            job: Completed simulation job
            retry_count: Number of retries on failure
            
        Returns:
            HTTP status code from webhook response
        """
        ...
    
    def send_batch_completed(
        self,
        webhook_url: str,
        job_ids: list[str],
        summary: Dict[str, Any],
    ) -> int:
        """Notify clinic that batch processing is complete."""
        ...
    
    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify webhook signature (HMAC-SHA256)."""
        ...
    
    def generate_signature(self, payload: bytes, secret: str) -> str:
        """Generate webhook signature for testing."""
        ...
