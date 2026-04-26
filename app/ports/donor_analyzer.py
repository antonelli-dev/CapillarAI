"""Port for donor area analysis (CPU-only, no GPU required)."""
from typing import Any, Optional, Protocol

import numpy as np

from app.domain.report import DonorAnalysis


class DonorAnalyzerPort(Protocol):
    """
    Analyze donor area (back of head) to estimate:
    - Hair density
    - Available grafts
    - Viability for transplant
    """
    
    def analyze(
        self,
        donor_image: np.ndarray,
        recipient_area_cm2: Optional[float] = None,
    ) -> DonorAnalysis:
        """
        Analyze donor area image.
        
        Args:
            donor_image: BGR image of donor area (coronilla/posterior)
            recipient_area_cm2: Optional recipient area for coverage calculation
            
        Returns:
            DonorAnalysis with density score, estimated grafts, recommendation
        """
        ...
    
    def calculate_match_score(
        self,
        donor_analysis: DonorAnalysis,
        recipient_area_cm2: float,
    ) -> float:
        """
        Calculate match score between donor supply and recipient demand.
        
        Returns:
            Score 0.0-1.0 indicating adequacy
        """
        ...
