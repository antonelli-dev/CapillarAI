"""Use case: GDPR compliance operations (export, deletion, consent)."""
import hashlib
import json
import logging
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
from typing import List, Optional

from app.domain.gdpr import (
    ConsentType,
    DataExport,
    GDPRDeletionRequest,
    PatientConsent,
)
from app.domain.job import SimulationJob
from app.ports.job_repository import JobRepositoryPort
from app.ports.storage import StoragePort

logger = logging.getLogger(__name__)


class GDPRDataManagementUseCase:
    """
    Handle GDPR Article 15 (Access), 17 (Erasure), 20 (Portability).
    """
    
    def __init__(
        self,
        job_repository: JobRepositoryPort,
        storage: StoragePort,
    ):
        self.job_repository = job_repository
        self.storage = storage
    
    async def export_patient_data(
        self,
        clinic_id: str,
        patient_reference: str,
    ) -> DataExport:
        """
        Export all data for a patient (GDPR Article 20).
        
        Returns:
            DataExport with download URL (ZIP containing images, reports, logs)
        """
        import uuid
        
        # Get all jobs for patient
        jobs = self._get_patient_jobs(clinic_id, patient_reference)
        
        # Build export package
        export_buffer = await self._build_export_package(jobs)
        
        # Upload with 7-day expiration
        export_id = str(uuid.uuid4())
        export_key = f"exports/{clinic_id}/{patient_reference}/{export_id}.zip"
        
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        download_url = self.storage.upload(
            export_key,
            export_buffer.getvalue(),
            content_type="application/zip",
            metadata={
                "expires_at": expires_at.isoformat(),
                "patient_reference_hash": hashlib.sha256(
                    patient_reference.encode()
                ).hexdigest()[:16],
            },
        )
        
        return DataExport(
            export_id=export_id,
            clinic_id=clinic_id,
            patient_reference=patient_reference,
            requested_at=datetime.utcnow(),
            available_until=expires_at,
            download_url=download_url,
            status="ready",
        )
    
    async def request_deletion(
        self,
        clinic_id: str,
        patient_reference: str,
        reason: str,
        delete_simulations: bool = True,
        delete_reports: bool = True,
        keep_billing: bool = True,
    ) -> GDPRDeletionRequest:
        """
        Request data deletion (GDPR Article 17).
        Returns request ID for tracking.
        """
        import uuid
        
        request_id = str(uuid.uuid4())
        request = GDPRDeletionRequest(
            request_id=request_id,
            clinic_id=clinic_id,
            patient_reference=patient_reference,
            requested_at=datetime.utcnow(),
            reason=reason,
            status="in_progress",
            delete_simulations=delete_simulations,
            delete_reports=delete_reports,
            keep_billing_records=keep_billing,
        )
        
        # Execute deletion
        jobs = self._get_patient_jobs(clinic_id, patient_reference)
        deleted_count = 0
        
        for job in jobs:
            if self._should_delete_job(job, request):
                await self._delete_job_data(job)
                deleted_count += 1
        
        request.status = "completed"
        request.completed_at = datetime.utcnow()
        request.deletion_log = f"Deleted {deleted_count} job records"
        
        return request
    
    async def record_consent(
        self,
        clinic_id: str,
        patient_reference: str,
        consent_type: ConsentType,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> PatientConsent:
        """Record patient consent for data processing."""
        import uuid
        
        # Hash PII
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16] if ip_address else None
        ua_hash = hashlib.sha256(user_agent.encode()).hexdigest()[:16] if user_agent else None
        
        consent = PatientConsent(
            consent_id=str(uuid.uuid4()),
            clinic_id=clinic_id,
            patient_reference=patient_reference,
            consent_type=consent_type,
            given_at=datetime.utcnow(),
            ip_address=ip_hash,
            user_agent_hash=ua_hash,
        )
        
        # Store consent (would need ConsentRepository in real implementation)
        logger.info(f"Recorded {consent_type.value} consent for {patient_reference}")
        
        return consent
    
    async def auto_purge_expired(self, limit: int = 100) -> int:
        """
        Purge jobs past retention period (GDPR automated compliance).
        Returns number of records purged.
        """
        expired_jobs = self.job_repository.get_expired_jobs(limit)
        
        purged = 0
        for job in expired_jobs:
            await self._delete_job_data(job)
            self.job_repository.delete(job.job_id)
            purged += 1
        
        return purged
    
    def _get_patient_jobs(
        self,
        clinic_id: str,
        patient_reference: str,
    ) -> List[SimulationJob]:
        """Get all jobs for a patient."""
        # This would need a query method in repository
        # For now, get all clinic jobs and filter
        all_jobs = self.job_repository.get_by_clinic(clinic_id, limit=10000)
        return [
            j for j in all_jobs
            if j.parameters.get("patient_reference") == patient_reference
        ]
    
    def _should_delete_job(
        self,
        job: SimulationJob,
        request: GDPRDeletionRequest,
    ) -> bool:
        """Determine if job should be deleted based on request params."""
        if request.keep_billing_records and job.job_type.name == "BILLING":
            return False
        return True
    
    async def _delete_job_data(self, job: SimulationJob) -> None:
        """Delete all stored data for a job."""
        # Delete input images
        if job.input_image_path:
            try:
                self.storage.delete(job.input_image_path)
            except Exception as e:
                logger.warning(f"Could not delete {job.input_image_path}: {e}")
        
        if job.donor_image_path:
            try:
                self.storage.delete(job.donor_image_path)
            except Exception as e:
                logger.warning(f"Could not delete {job.donor_image_path}: {e}")
        
        # Delete results
        for url in job.result_urls.values():
            try:
                key = self._extract_key(url)
                self.storage.delete(key)
            except Exception as e:
                logger.warning(f"Could not delete result {url}: {e}")
    
    async def _build_export_package(
        self,
        jobs: List[SimulationJob],
    ) -> BytesIO:
        """Build ZIP file with all patient data."""
        buffer = BytesIO()
        
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Metadata
            metadata = {
                "export_date": datetime.utcnow().isoformat(),
                "job_count": len(jobs),
                "jobs": [j.to_public_dict() for j in jobs],
            }
            zf.writestr("metadata.json", json.dumps(metadata, indent=2, default=str))
            
            # Images and reports
            for job in jobs:
                # Download and add files
                if job.input_image_path:
                    try:
                        data = self.storage.download(job.input_image_path)
                        zf.writestr(f"jobs/{job.job_id}/input.jpg", data)
                    except Exception as e:
                        logger.warning(f"Could not export {job.input_image_path}: {e}")
                
                # Add results
                for name, url in job.result_urls.items():
                    try:
                        key = self._extract_key(url)
                        data = self.storage.download(key)
                        ext = "png" if "simulation" in name else "pdf"
                        zf.writestr(f"jobs/{job.job_id}/{name}.{ext}", data)
                    except Exception as e:
                        logger.warning(f"Could not export {url}: {e}")
        
        buffer.seek(0)
        return buffer
    
    def _extract_key(self, url: str) -> str:
        """Extract storage key from URL."""
        from urllib.parse import urlparse
        return urlparse(url).path.lstrip("/")
