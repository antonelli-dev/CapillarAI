"""Domain entities for async job processing."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class JobStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(Enum):
    SINGLE_SIMULATION = "single_simulation"
    BATCH_SIMULATION = "batch_simulation"
    DONOR_ANALYSIS = "donor_analysis"
    PDF_GENERATION = "pdf_generation"


@dataclass
class SimulationJob:
    job_id: str
    job_type: JobType
    clinic_id: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Input data (stored encrypted/at-rest as per GDPR)
    input_image_path: Optional[str] = None
    donor_image_path: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Results
    result_urls: Dict[str, str] = field(default_factory=dict)  # simulation_url, pdf_url, etc.
    error_message: Optional[str] = None
    
    # Webhook
    webhook_url: Optional[str] = None
    webhook_sent: bool = False
    webhook_response_status: Optional[int] = None
    
    # GDPR
    retention_days: int = 30  # Auto-delete after N days
    patient_consent_given: bool = False
    consent_timestamp: Optional[datetime] = None
    
    def is_expired(self) -> bool:
        """Check if job data should be purged per GDPR retention policy."""
        if self.completed_at is None:
            return False
        from datetime import timedelta
        purge_date = self.completed_at + timedelta(days=self.retention_days)
        return datetime.utcnow() > purge_date
    
    def to_public_dict(self) -> Dict[str, Any]:
        """Safe representation for API responses (excludes internal paths)."""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result_urls": self.result_urls,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class ShareLink:
    """Time-limited access to simulation results for patient sharing."""
    token: str
    job_id: str
    clinic_id: str
    expires_at: datetime
    max_views: Optional[int] = 10
    view_count: int = 0
    watermark_text: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def is_valid(self) -> bool:
        if datetime.utcnow() > self.expires_at:
            return False
        if self.max_views is not None and self.view_count >= self.max_views:
            return False
        return True
    
    def record_view(self) -> None:
        """Increment view counter (call on each access)."""
        # Note: This modifies the dataclass, use in repository with update
        object.__setattr__(self, 'view_count', self.view_count + 1)
