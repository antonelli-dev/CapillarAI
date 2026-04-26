"""Use case: Create async simulation job (batch or single)."""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.domain.job import JobStatus, JobType, SimulationJob
from app.ports.job_repository import JobRepositoryPort
from app.ports.storage import StoragePort

logger = logging.getLogger(__name__)


class CreateSimulationJobUseCase:
    """
    Create and queue simulation jobs for async processing.
    Supports both single images and batch uploads.
    """
    
    def __init__(
        self,
        job_repository: JobRepositoryPort,
        storage: StoragePort,
    ):
        self.job_repository = job_repository
        self.storage = storage
    
    async def execute_single(
        self,
        clinic_id: str,
        front_image_bytes: bytes,
        donor_image_bytes: Optional[bytes] = None,
        webhook_url: Optional[str] = None,
        patient_reference: Optional[str] = None,
        preset_id: Optional[str] = None,
        seed: Optional[int] = None,
        consent_given: bool = False,
    ) -> SimulationJob:
        """
        Create single simulation job.
        
        Args:
            clinic_id: Organization identifier
            front_image_bytes: Frontal portrait photo
            donor_image_bytes: Optional donor area photo for viability analysis
            webhook_url: Callback URL for completion notification
            patient_reference: Pseudonymized patient ID
            preset_id: Hairline preset to use
            seed: Random seed for reproducibility
            consent_given: GDPR consent status
            
        Returns:
            Created job with pending status
        """
        import uuid
        
        job_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # Store images in configured storage (S3/MinIO/local)
        front_key = self.storage.generate_key(
            clinic_id,
            patient_reference or "anonymous",
            "front",
            "jpg",
        )
        front_url = self.storage.upload(
            front_key,
            front_image_bytes,
            content_type="image/jpeg",
            metadata={
                "clinic_id": clinic_id,
                "patient_reference": patient_reference or "",
                "job_id": job_id,
            },
        )
        
        donor_key = None
        if donor_image_bytes:
            donor_key = self.storage.generate_key(
                clinic_id,
                patient_reference or "anonymous",
                "donor",
                "jpg",
            )
            self.storage.upload(
                donor_key,
                donor_image_bytes,
                content_type="image/jpeg",
            )
        
        job = SimulationJob(
            job_id=job_id,
            job_type=JobType.SINGLE_SIMULATION,
            clinic_id=clinic_id,
            status=JobStatus.PENDING,
            input_image_path=front_key,
            donor_image_path=donor_key,
            parameters={
                "preset_id": preset_id,
                "seed": seed,
                "timestamp": timestamp,
            },
            webhook_url=webhook_url,
            patient_consent_given=consent_given,
            consent_timestamp=datetime.utcnow() if consent_given else None,
        )
        
        return self.job_repository.create(job)
    
    async def execute_batch(
        self,
        clinic_id: str,
        images: List[bytes],
        webhook_url: Optional[str] = None,
        preset_id: Optional[str] = None,
    ) -> List[SimulationJob]:
        """
        Create batch of simulation jobs.
        
        Returns:
            List of created jobs (all pending)
        """
        jobs = []
        for idx, image_bytes in enumerate(images):
            job = await self.execute_single(
                clinic_id=clinic_id,
                front_image_bytes=image_bytes,
                webhook_url=webhook_url if idx == 0 else None,  # Only notify once for batch
                preset_id=preset_id,
            )
            jobs.append(job)
        
        return jobs
