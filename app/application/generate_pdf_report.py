"""Use case: Generate medical PDF reports on demand."""
import logging
from datetime import datetime
from typing import Optional

from app.domain.job import SimulationJob
from app.domain.report import MedicalReport
from app.ports.job_repository import JobRepositoryPort
from app.ports.pdf_generator import PDFGeneratorPort
from app.ports.storage import StoragePort

logger = logging.getLogger(__name__)


class GeneratePdfReportUseCase:
    """
    Generate PDF report for completed simulation job.
    Can be called on-demand (user clicks "Download PDF") or automatically.
    """
    
    def __init__(
        self,
        job_repository: JobRepositoryPort,
        storage: StoragePort,
        pdf_generator: PDFGeneratorPort,
    ):
        self.job_repository = job_repository
        self.storage = storage
        self.pdf_generator = pdf_generator
    
    async def execute(
        self,
        job_id: str,
        include_disclaimer: bool = True,
        watermark: str = "",
    ) -> str:
        """
        Generate PDF for job and return download URL.
        
        Returns:
            Presigned URL for PDF download
        """
        job = self.job_repository.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        if job.status.name != "COMPLETED":
            raise ValueError(f"Job not completed (status: {job.status.name})")
        
        # Reconstruct or fetch MedicalReport domain object
        # In real implementation, you'd store the report data, not just images
        report = await self._reconstruct_report(job)
        
        # Generate PDF
        pdf_bytes = await asyncio.to_thread(
            self.pdf_generator.generate_medical_report,
            report,
            include_disclaimer=include_disclaimer,
            watermark=watermark,
        )
        
        # Upload
        pdf_key = self.storage.generate_key(
            job.clinic_id,
            job.parameters.get("patient_reference", "anonymous"),
            "report",
            "pdf",
        )
        pdf_url = self.storage.upload(
            pdf_key,
            pdf_bytes,
            content_type="application/pdf",
        )
        
        # Update job with PDF URL
        result_urls = job.result_urls.copy()
        result_urls["pdf"] = pdf_url
        self.job_repository.update_results(job_id, result_urls)
        
        return pdf_url
    
    async def _reconstruct_report(self, job: SimulationJob) -> MedicalReport:
        """Rebuild MedicalReport from job data and stored images."""
        import asyncio
        
        # Download original and result images
        front_bytes = await asyncio.to_thread(
            self.storage.download,
            job.input_image_path,
        )
        
        result_url = job.result_urls.get("simulation")
        if not result_url:
            raise ValueError("No simulation result found")
        
        # Extract key from URL (implementation depends on storage backend)
        result_key = self._extract_key_from_url(result_url)
        result_bytes = await asyncio.to_thread(
            self.storage.download,
            result_key,
        )
        
        return MedicalReport(
            report_id=job.job_id,
            clinic_id=job.clinic_id,
            patient_reference=job.parameters.get("patient_reference"),
            created_at=job.created_at or datetime.utcnow(),
            original_image=front_bytes,
            simulation_image=result_bytes,
            scalp_analysis=None,  # Would need to store analysis results
            simulation_params=None,
        )
    
    def _extract_key_from_url(self, url: str) -> str:
        """Extract storage key from URL (simplified)."""
        # Implementation depends on your URL format
        # For S3/MinIO: parse the path component
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.path.lstrip("/")
