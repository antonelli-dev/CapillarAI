"""OpenCV-based implementation of DonorAnalyzerPort (CPU-only)."""
import logging
from typing import Optional

import cv2
import numpy as np

from app.domain.report import DonorAnalysis, DonorViability
from app.ports.donor_analyzer import DonorAnalyzerPort

logger = logging.getLogger(__name__)


class OpenCVDonorAnalyzer(DonorAnalyzerPort):
    """
    Analyze donor area using computer vision (OpenCV + MediaPipe).
    No GPU required - runs entirely on CPU.
    
    Algorithm:
    1. Detect scalp region
    2. Calculate hair density via texture analysis
    3. Estimate grafts based on area and density
    4. Compare with recipient needs
    """
    
    def __init__(
        self,
        grafts_per_cm2_dense: float = 80.0,  # FUE grafts per cm² in dense donor
        min_viable_density: float = 4.0,  # Score out of 10
    ):
        self.grafts_per_cm2_dense = grafts_per_cm2_dense
        self.min_viable_density = min_viable_density
    
    def analyze(
        self,
        donor_image: np.ndarray,
        recipient_area_cm2: Optional[float] = None,
    ) -> DonorAnalysis:
        """
        Analyze donor area image.
        
        Args:
            donor_image: BGR image of donor area
            recipient_area_cm2: Optional recipient area for match calculation
            
        Returns:
            DonorAnalysis with density, grafts, recommendation
        """
        # 1. Preprocess
        gray = cv2.cvtColor(donor_image, cv2.COLOR_BGR2GRAY)
        
        # 2. Detect scalp/skin region (exclude background)
        scalp_mask = self._segment_scalp(gray)
        
        # 3. Calculate hair density via texture analysis
        density_score = self._calculate_density_score(gray, scalp_mask)
        
        # 4. Estimate available area
        scalp_pixels = np.sum(scalp_mask > 0)
        # Assume typical donor area is ~150-200 cm²
        # Use pixel density as proxy if we don't have calibration
        estimated_area_cm2 = self._estimate_area_cm2(donor_image.shape, scalp_pixels)
        
        # 5. Calculate grafts
        # Industry: 60-100 grafts/cm² in dense donor area
        density_factor = density_score / 10.0
        estimated_grafts = int(
            estimated_area_cm2 * self.grafts_per_cm2_dense * density_factor
        )
        
        # 6. Determine viability
        recommendation = self._determine_viability(
            density_score,
            estimated_grafts,
            recipient_area_cm2,
        )
        
        # 7. Calculate confidence based on image quality
        confidence = self._calculate_confidence(gray, scalp_mask)
        
        # 8. Estimate hair caliber (optional, simplified)
        hair_caliber = self._estimate_hair_caliber(gray, scalp_mask)
        
        return DonorAnalysis(
            density_score=density_score,
            estimated_grafts=estimated_grafts,
            coverage_area_cm2=estimated_area_cm2,
            hair_caliber_mm=hair_caliber,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=self._generate_reasoning(
                density_score, estimated_grafts, recommendation
            ),
        )
    
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
        if recipient_area_cm2 <= 0:
            return 0.0
        
        # Required grafts: 20-30 per cm² for good coverage
        required_grafts = recipient_area_cm2 * 25
        
        if donor_analysis.estimated_grafts <= 0:
            return 0.0
        
        ratio = donor_analysis.estimated_grafts / required_grafts
        
        # Score: 1.0 = exactly enough, >1.0 = surplus, <1.0 = deficit
        if ratio >= 1.5:
            return 1.0  # Excellent
        elif ratio >= 1.0:
            return 0.8 + (ratio - 1.0) * 0.4  # 0.8-1.0
        elif ratio >= 0.6:
            return 0.5 + (ratio - 0.6) * 0.75  # 0.5-0.8
        else:
            return max(0.0, ratio / 1.2)  # 0.0-0.5
    
    def _segment_scalp(self, gray: np.ndarray) -> np.ndarray:
        """Segment scalp region from background."""
        # Adaptive threshold to handle different lighting
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Otsu's thresholding for bimodal distribution (scalp vs background)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Morphological operations to clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        clean = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        clean = cv2.morphologyEx(clean, cv2.MORPH_OPEN, kernel)
        
        return clean
    
    def _calculate_density_score(self, gray: np.ndarray, mask: np.ndarray) -> float:
        """Calculate hair density score (0-10) via texture analysis."""
        # Focus on scalp region only
        scalp_region = cv2.bitwise_and(gray, gray, mask=mask)
        
        # Local Binary Pattern (simplified) - texture complexity
        # High frequency = lots of hair follicles = high density
        laplacian = cv2.Laplacian(scalp_region, cv2.CV_64F)
        variance = np.var(laplacian[mask > 0])
        
        # Normalize to 0-10 scale
        # Typical variance ranges: 50 (bald/smooth) to 2000+ (dense)
        score = min(10.0, max(0.0, variance / 200))
        
        return round(score, 1)
    
    def _estimate_area_cm2(self, shape: tuple, scalp_pixels: int) -> float:
        """Estimate physical area from pixel count."""
        # Heuristic: typical phone photo of donor area at arm's length
        # covers ~100-200 cm². We'll estimate based on standard framing.
        
        # Assume image covers roughly 150 cm² of scalp
        # This is a simplification - in production, you'd calibrate
        total_pixels = shape[0] * shape[1]
        scalp_ratio = scalp_pixels / total_pixels
        
        # Estimate: full image ~200 cm² at typical distance
        estimated_cm2 = 200 * scalp_ratio
        
        return max(50.0, min(250.0, estimated_cm2))  # Clamp to realistic range
    
    def _determine_viability(
        self,
        density_score: float,
        estimated_grafts: int,
        recipient_area_cm2: Optional[float],
    ) -> DonorViability:
        """Determine viability recommendation."""
        if density_score < self.min_viable_density:
            return DonorViability.NOT_RECOMMENDED
        
        if recipient_area_cm2:
            required = recipient_area_cm2 * 25
            
            if estimated_grafts >= required * 1.5:
                return DonorViability.VIABLE_SINGLE_SESSION
            elif estimated_grafts >= required * 0.8:
                return DonorViability.VIABLE_MULTIPLE_SESSIONS
            elif estimated_grafts >= required * 0.5:
                return DonorViability.MARGINAL
            else:
                return DonorViability.NOT_RECOMMENDED
        
        # No recipient area provided - generic assessment
        if density_score >= 7.0 and estimated_grafts > 3000:
            return DonorViability.VIABLE_SINGLE_SESSION
        elif density_score >= 5.0:
            return DonorViability.MARGINAL
        else:
            return DonorViability.NOT_RECOMMENDED
    
    def _calculate_confidence(self, gray: np.ndarray, mask: np.ndarray) -> float:
        """Calculate analysis confidence based on image quality."""
        scores = []
        
        # 1. Image clarity (blur detection)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        clarity_score = min(1.0, laplacian_var / 500)
        scores.append(clarity_score)
        
        # 2. Lighting uniformity
        mean_val = np.mean(gray[mask > 0])
        std_val = np.std(gray[mask > 0])
        lighting_score = 1.0 - min(1.0, std_val / 100)
        scores.append(lighting_score)
        
        # 3. Scalp coverage in frame
        coverage = np.sum(mask > 0) / mask.size
        coverage_score = min(1.0, coverage * 3)  # Ideal: 30%+ of frame
        scores.append(coverage_score)
        
        return round(sum(scores) / len(scores), 2)
    
    def _estimate_hair_caliber(self, gray: np.ndarray, mask: np.ndarray) -> Optional[float]:
        """Estimate hair thickness in mm (very approximate)."""
        # This would require calibration and more sophisticated analysis
        # Return None for now - requires specialist input
        return None
    
    def _generate_reasoning(
        self,
        density_score: float,
        estimated_grafts: int,
        recommendation: DonorViability,
    ) -> str:
        """Generate human-readable reasoning."""
        reasonings = {
            DonorViability.VIABLE_SINGLE_SESSION: (
                f"Excellent donor area. Density score {density_score:.1f}/10 indicates "
                f"robust supply (~{estimated_grafts:,} grafts available). "
                f"Adequate for full coverage in single session."
            ),
            DonorViability.VIABLE_MULTIPLE_SESSIONS: (
                f"Good donor area with {density_score:.1f}/10 density. "
                f"~{estimated_grafts:,} grafts available. May require 2 sessions "
                f"for optimal coverage."
            ),
            DonorViability.MARGINAL: (
                f"Moderate donor density ({density_score:.1f}/10). "
                f"Limited graft supply (~{estimated_grafts:,}). Careful planning required. "
                f"May need FUT or beard/body hair supplementation."
            ),
            DonorViability.NOT_RECOMMENDED: (
                f"Insufficient donor area. Density score {density_score:.1f}/10 is below "
                f"recommended threshold ({self.min_viable_density}/10). "
                f"Transplant may yield poor results."
            ),
        }
        return reasonings.get(recommendation, "Analysis complete.")
