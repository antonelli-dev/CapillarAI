"""API endpoints for GDPR compliance (v1/gdpr)."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.rate_limit_ext import limiter
from app.config import get_settings
from app.deps import get_gdpr_management_use_case, get_job_repository

_settings = get_settings()
router = APIRouter(prefix="/gdpr", tags=["v1"])


class ConsentRequest(BaseModel):
    """Record patient consent."""
    patient_reference: str = Field(..., description="Pseudonymized patient ID")
    consent_type: str = Field("data_processing", description="data_processing, marketing, or research")
    ip_address: Optional[str] = Field(None)
    user_agent: Optional[str] = Field(None)


class DataExportRequest(BaseModel):
    """Request data export."""
    patient_reference: str = Field(..., description="Patient to export data for")


class DataDeletionRequest(BaseModel):
    """Request data deletion (GDPR Article 17)."""
    patient_reference: str = Field(..., description="Patient to delete data for")
    reason: str = Field("", description="Reason for deletion request")
    delete_simulations: bool = Field(True)
    delete_reports: bool = Field(True)
    keep_billing: bool = Field(True, description="Retain billing records (legal obligation)")


@router.post(
    "/consent",
    summary="Record patient consent",
    description="Record GDPR-compliant consent for data processing.",
)
async def record_consent(
    request: Request,
    data: ConsentRequest,
):
    """Record patient consent for GDPR compliance."""
    clinic_id = "default_clinic"
    
    use_case = get_gdpr_management_use_case()
    
    from app.domain.gdpr import ConsentType
    
    try:
        consent_type = ConsentType(data.consent_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid consent_type. Must be one of: {[t.value for t in ConsentType]}"
        )
    
    # Get client info from request
    client_ip = data.ip_address or request.client.host if request.client else None
    user_agent = data.user_agent or request.headers.get("user-agent")
    
    consent = await use_case.record_consent(
        clinic_id=clinic_id,
        patient_reference=data.patient_reference,
        consent_type=consent_type,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    
    return {
        "consent_id": consent.consent_id,
        "consent_type": consent.consent_type.value,
        "given_at": consent.given_at.isoformat(),
        "status": "active" if consent.is_active() else "withdrawn",
    }


@router.post(
    "/export",
    summary="Export patient data",
    description="GDPR Article 20 - Export all data for a patient (ZIP format).",
)
async def export_patient_data(
    request: Request,
    data: DataExportRequest,
):
    """
    Export all patient data as ZIP archive.
    
    Includes:
    - All simulation images (input and results)
    - PDF reports
    - Processing logs
    - Metadata
    
    Download URL valid for 7 days.
    """
    clinic_id = "default_clinic"
    
    use_case = get_gdpr_management_use_case()
    
    export = await use_case.export_patient_data(
        clinic_id=clinic_id,
        patient_reference=data.patient_reference,
    )
    
    return {
        "export_id": export.export_id,
        "status": export.status,
        "download_url": export.download_url,
        "expires_at": export.available_until.isoformat(),
        "data_format": export.data_format,
    }


@router.post(
    "/delete",
    summary="Request data deletion",
    description="GDPR Article 17 - Right to erasure. Request deletion of patient data.",
)
async def request_deletion(
    request: Request,
    data: DataDeletionRequest,
):
    """
    Request deletion of patient data.
    
    By default:
    - Simulations: DELETED
    - Reports: DELETED
    - Billing records: RETAINED (legal obligation)
    
    Returns deletion request ID for tracking.
    """
    clinic_id = "default_clinic"
    
    use_case = get_gdpr_management_use_case()
    
    deletion = await use_case.request_deletion(
        clinic_id=clinic_id,
        patient_reference=data.patient_reference,
        reason=data.reason,
        delete_simulations=data.delete_simulations,
        delete_reports=data.delete_reports,
        keep_billing=data.keep_billing,
    )
    
    return {
        "request_id": deletion.request_id,
        "status": deletion.status,
        "requested_at": deletion.requested_at.isoformat(),
        "completed_at": deletion.completed_at.isoformat() if deletion.completed_at else None,
        "deletion_log": deletion.deletion_log,
    }


@router.get(
    "/retention-policy",
    summary="View data retention policy",
    description="Get current data retention periods per category.",
)
async def get_retention_policy():
    """Get GDPR retention policy."""
    from app.domain.gdpr import DEFAULT_RETENTION_POLICY, DataRetentionCategory
    
    return {
        "categories": {
            cat.value: {"days": days}
            for cat, days in DEFAULT_RETENTION_POLICY.items()
        },
        "description": {
            DataRetentionCategory.SIMULATION_IMAGES.value: "Auto-deleted after 30 days",
            DataRetentionCategory.ANALYTICS_LOGS.value: "Purged after 90 days",
            DataRetentionCategory.MEDICAL_REPORTS.value: "Retained 7 years (medical records)",
            DataRetentionCategory.BILLING_DATA.value: "Retained 10 years (legal)",
        }
    }


@router.get(
    "/jobs/expired",
    summary="List expired jobs (admin)",
    description="List jobs past retention period ready for purging (GDPR compliance).",
)
async def list_expired_jobs(
    request: Request,
    limit: int = 100,
):
    """List expired jobs for GDPR purging."""
    clinic_id = "default_clinic"
    
    repo = get_job_repository()
    expired = repo.get_expired_jobs(limit)
    
    # Filter to clinic's jobs only
    clinic_expired = [j for j in expired if j.clinic_id == clinic_id]
    
    return {
        "count": len(clinic_expired),
        "jobs": [
            {
                "job_id": j.job_id,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                "retention_days": j.retention_days,
                "status": "expired" if j.is_expired() else "expiring_soon",
            }
            for j in clinic_expired
        ],
    }


@router.post(
    "/admin/purge-expired",
    summary="Purge expired data (admin)",
    description="Immediately delete all expired job data (GDPR compliance).",
)
async def purge_expired_data(
    request: Request,
    limit: int = 100,
):
    """Purge all expired job data (admin only)."""
    # In real implementation, check for admin role
    # For now, placeholder
    
    use_case = get_gdpr_management_use_case()
    purged = await use_case.auto_purge_expired(limit)
    
    return {
        "purged_count": purged,
        "timestamp": datetime.utcnow().isoformat(),
    }
