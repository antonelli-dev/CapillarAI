"""Port for async job persistence and queue management."""
from typing import Any, Dict, List, Optional, Protocol

from app.domain.job import JobStatus, ShareLink, SimulationJob


class JobRepositoryPort(Protocol):
    """Repository for simulation jobs with GDPR-compliant data handling."""
    
    def create(self, job: SimulationJob) -> SimulationJob:
        """Persist new job."""
        ...
    
    def get_by_id(self, job_id: str) -> Optional[SimulationJob]:
        """Retrieve job by ID."""
        ...
    
    def get_by_clinic(
        self,
        clinic_id: str,
        status: Optional[JobStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[SimulationJob]:
        """List jobs for a clinic with optional filtering."""
        ...
    
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> SimulationJob:
        """Update job status (transition to processing/completed/failed)."""
        ...
    
    def update_results(
        self,
        job_id: str,
        result_urls: Dict[str, str],
    ) -> SimulationJob:
        """Update job with result URLs."""
        ...
    
    def mark_webhook_sent(
        self,
        job_id: str,
        response_status: int,
    ) -> None:
        """Record webhook delivery."""
        ...
    
    def get_pending_jobs(self, limit: int = 10) -> List[SimulationJob]:
        """Get jobs waiting to be processed (for worker)."""
        ...
    
    def get_expired_jobs(self, limit: int = 100) -> List[SimulationJob]:
        """Get jobs past retention period for GDPR deletion."""
        ...
    
    def delete(self, job_id: str) -> None:
        """Hard delete (GDPR erasure)."""
        ...
    
    # Share links
    def create_share_link(self, link: ShareLink) -> ShareLink:
        """Create time-limited share token."""
        ...
    
    def get_share_link(self, token: str) -> Optional[ShareLink]:
        """Validate and retrieve share link."""
        ...
    
    def increment_share_link_views(self, token: str) -> None:
        """Record view count for share link."""
        ...
