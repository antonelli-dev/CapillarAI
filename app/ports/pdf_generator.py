"""Port for PDF generation (Medical Reports)."""
from typing import Any, Protocol

from app.domain.report import MedicalReport


class PDFGeneratorPort(Protocol):
    """Generate professional medical-grade PDF reports."""
    
    def generate_medical_report(
        self,
        report: MedicalReport,
        include_disclaimer: bool = True,
        watermark: str = "",
    ) -> bytes:
        """
        Generate PDF report with original photo, simulation, and analysis.
        
        Args:
            report: MedicalReport domain object
            include_disclaimer: Whether to include legal disclaimer
            watermark: Optional watermark text (e.g., "PREVIEW")
            
        Returns:
            PDF file as bytes
        """
        ...
    
    def generate_batch_summary(
        self,
        reports: list[MedicalReport],
        clinic_name: str,
    ) -> bytes:
        """Generate summary PDF for batch processing."""
        ...
