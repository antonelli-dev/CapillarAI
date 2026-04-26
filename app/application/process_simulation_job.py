"""Use case: Process pending simulation jobs (worker)."""
import asyncio
import io
import logging
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from app.application.generate_hair import GenerateHairUseCase
from app.domain.job import JobStatus, SimulationJob
from app.domain.report import DonorAnalysis, MedicalReport, ScalpAnalysis, SimulationParameters
from app.ports.donor_analyzer import DonorAnalyzerPort
from app.ports.image_generator import ImageGeneratorPort
from app.ports.job_repository import JobRepositoryPort
from app.ports.pdf_generator import PDFGeneratorPort
from app.ports.storage import StoragePort
from app.ports.webhook_dispatcher import WebhookDispatcherPort

logger = logging.getLogger(__name__)


class ProcessSimulationJobUseCase:
    """
    Worker use case: Process simulation jobs from queue.
    Orchestrates: validation, inference, donor analysis, PDF generation, storage.
    """
    
    def __init__(
        self,
        job_repository: JobRepositoryPort,
        storage: StoragePort,
        image_generator: ImageGeneratorPort,
        donor_analyzer: Optional[DonorAnalyzerPort] = None,
        pdf_generator: Optional[PDFGeneratorPort] = None,
        webhook_dispatcher: Optional[WebhookDispatcherPort] = None,
    ):
        self.job_repository = job_repository
        self.storage = storage
        self.image_generator = image_generator
        self.donor_analyzer = donor_analyzer
        self.pdf_generator = pdf_generator
        self.webhook_dispatcher = webhook_dispatcher
    
    async def execute(self, job_id: str) -> SimulationJob:
        """
        Process single job end-to-end.
        
        Flow:
        1. Download images from storage
        2. Validate and preprocess
        3. Run GPU inference (image generation)
        4. Optional: Donor area analysis
        5. Optional: Generate PDF report
        6. Upload results
        7. Update job status
        8. Send webhook
        """
        job = self.job_repository.get_by_id(job_id)
        if not job or job.status != JobStatus.PENDING:
            logger.warning(f"Job {job_id} not found or not pending")
            return job
        
        # Mark as processing
        job = self.job_repository.update_status(job_id, JobStatus.PROCESSING)
        
        try:
            # 1. Download images
            front_bytes = self.storage.download(job.input_image_path)
            front_image = self._bytes_to_cv2(front_bytes)
            
            donor_analysis = None
            if job.donor_image_path and self.donor_analyzer:
                donor_bytes = self.storage.download(job.donor_image_path)
                donor_image = self._bytes_to_cv2(donor_bytes)
                donor_analysis = self.donor_analyzer.analyze(donor_image)
            
            # 2. GPU Inference (this is the heavy part)
            # Delegate to existing GenerateHairUseCase or direct generator
            # For now, simplified:
            result_image = await self._run_inference(front_image, job)
            
            # 3. Upload result
            result_key = self.storage.generate_key(
                job.clinic_id,
                job.parameters.get("patient_reference", "anonymous"),
                "result",
                "png",
            )
            result_bytes = self._pil_to_bytes(result_image)
            result_url = self.storage.upload(
                result_key,
                result_bytes,
                content_type="image/png",
            )
            
            result_urls = {"simulation": result_url}
            
            # 4. Optional: Generate PDF
            if self.pdf_generator:
                report = self._build_medical_report(
                    job, front_image, result_image, donor_analysis
                )
                pdf_bytes = self.pdf_generator.generate_medical_report(report)
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
                result_urls["pdf"] = pdf_url
            
            # 5. Update job as completed
            job = self.job_repository.update_status(job_id, JobStatus.COMPLETED)
            job = self.job_repository.update_results(job_id, result_urls)
            
            # 6. Send webhook
            if job.webhook_url and self.webhook_dispatcher:
                status = await asyncio.to_thread(
                    self.webhook_dispatcher.send_job_completed,
                    job.webhook_url,
                    job,
                )
                self.job_repository.mark_webhook_sent(job_id, status)
            
            return job
            
        except Exception as e:
            logger.exception(f"Job {job_id} failed: {e}")
            job = self.job_repository.update_status(
                job_id, JobStatus.FAILED, str(e)
            )
            return job
    
    def _bytes_to_cv2(self, data: bytes) -> np.ndarray:
        nparr = np.frombuffer(data, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    def _pil_to_bytes(self, image: Image.Image) -> bytes:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    
    async def _run_inference(
        self,
        image: np.ndarray,
        job: SimulationJob,
    ) -> Image.Image:
        """Run GPU inference with proper semaphore management."""
        # This should integrate with your existing deps.py run_inference
        # For now, placeholder:
        from app.infrastructure.hair_mask import analyze_scalp_lighting
        from app.infrastructure.hair_preprocess import maybe_replace_background_flat
        
        # Get landmarks (would need face detector here)
        # Simplified for structure:
        return self.image_generator.generate(
            image,
            None,  # landmarks would come from validation
            seed=job.parameters.get("seed"),
        )
    
    def _build_medical_report(
        self,
        job: SimulationJob,
        original: np.ndarray,
        simulation: Image.Image,
        donor_analysis: Optional[DonorAnalysis],
    ) -> MedicalReport:
        """Build domain object for PDF generation."""
        import io
        from datetime import datetime
        
        # Convert images to bytes
        orig_pil = Image.fromarray(cv2.cvtColor(original, cv2.COLOR_BGR2RGB))
        orig_buf = io.BytesIO()
        orig_pil.save(orig_buf, format="PNG")
        
        sim_buf = io.BytesIO()
        simulation.save(sim_buf, format="PNG")
        
        return MedicalReport(
            report_id=job.job_id,
            clinic_id=job.clinic_id,
            patient_reference=job.parameters.get("patient_reference"),
            created_at=datetime.utcnow(),
            original_image=orig_buf.getvalue(),
            simulation_image=sim_buf.getvalue(),
            scalp_analysis=ScalpAnalysis(
                severity="moderate",  # Would come from actual analysis
                brightness_score=0.0,
                contrast_score=0.0,
            ),
            simulation_params=SimulationParameters(
                profile_name=job.parameters.get("preset_id", "launch"),
                num_inference_steps=50,
                inpaint_strength=0.75,
                guidance_scale=7.5,
                seed=job.parameters.get("seed"),
            ),
            donor_analysis=donor_analysis,
            disclaimer_text="This simulation is for illustrative purposes only...",
        )
