"""GDPR compliance domain entities and policies."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ConsentType(Enum):
    DATA_PROCESSING = "data_processing"
    MARKETING = "marketing"
    RESEARCH = "research"


class DataRetentionCategory(Enum):
    SIMULATION_IMAGES = "simulation_images"  # 30 days
    ANALYTICS_LOGS = "analytics_logs"  # 90 days
    MEDICAL_REPORTS = "medical_reports"  # 7 years (medical records)
    BILLING_DATA = "billing_data"  # 10 years


@dataclass(frozen=True)
class PatientConsent:
    consent_id: str
    clinic_id: str
    patient_reference: str  # Pseudonymized ID
    consent_type: ConsentType
    given_at: datetime
    ip_address: Optional[str] = None  # Hash this!
    user_agent_hash: Optional[str] = None  # Hash of UA
    withdrawn_at: Optional[datetime] = None
    
    def is_active(self) -> bool:
        return self.withdrawn_at is None


@dataclass(frozen=True)
class DataExport:
    """GDPR Article 20 - Right to data portability."""
    export_id: str
    clinic_id: str
    patient_reference: str
    requested_at: datetime
    available_until: datetime
    download_url: Optional[str] = None
    data_format: str = "json"  # or "pdf"
    status: str = "pending"  # pending, ready, expired
    
    def is_available(self) -> bool:
        return self.status == "ready" and datetime.utcnow() < self.available_until


@dataclass
class GDPRDeletionRequest:
    """GDPR Article 17 - Right to erasure."""
    request_id: str
    clinic_id: str
    patient_reference: str
    requested_at: datetime
    reason: str
    status: str = "pending"  # pending, in_progress, completed, denied
    
    # What to delete
    delete_simulations: bool = True
    delete_reports: bool = True
    delete_analytics: bool = True
    keep_billing_records: bool = True  # Legal obligation exception
    
    completed_at: Optional[datetime] = None
    deletion_log: Optional[str] = None  # Audit trail


@dataclass(frozen=True)
class DataProcessingRecord:
    """GDPR Article 30 - Record of processing activities."""
    purpose: str
    data_categories: List[str]
    retention_days: int
    lawful_basis: str  # "consent", "contract", "legal_obligation", "legitimate_interest"
    data_recipients: List[str]
    security_measures: List[str]
    

# Default retention policy per category
DEFAULT_RETENTION_POLICY: Dict[DataRetentionCategory, int] = {
    DataRetentionCategory.SIMULATION_IMAGES: 30,
    DataRetentionCategory.ANALYTICS_LOGS: 90,
    DataRetentionCategory.MEDICAL_REPORTS: 2555,  # 7 years
    DataRetentionCategory.BILLING_DATA: 3650,  # 10 years
}


@dataclass(frozen=True)
class RegionalConfig:
    """EU-specific configuration for GDPR compliance."""
    region_code: str  # "EU", "UK", "CH", etc.
    data_residency_required: bool = True
    allowed_storage_regions: List[str] = None
    encryption_required: bool = True
    dpo_contact: Optional[str] = None
    privacy_policy_url: str = ""
    
    def __post_init__(self):
        if self.allowed_storage_regions is None:
            object.__setattr__(self, 'allowed_storage_regions', ["EU", "EEA"])
