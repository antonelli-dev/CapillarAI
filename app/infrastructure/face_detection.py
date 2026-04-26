import logging
import os

import cv2
import mediapipe as mp
import numpy as np

from app.domain.portrait import PortraitValidation

logger = logging.getLogger(__name__)

# MediaPipe 0.10+ API
from mediapipe.tasks.python.vision.face_detector import FaceDetector
from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarker
from mediapipe.tasks.python.core.base_options import BaseOptions


def _get_model_path(model_name: str) -> str:
    """Return path to bundled model, or raise if missing."""
    mp_dir = os.path.dirname(mp.__file__)
    candidates = [
        os.path.join(mp_dir, "..", "..", "mediapipe", "modules", model_name),
        os.path.join(mp_dir, "..", "mediapipe", "modules", model_name),
        os.path.join(mp_dir, "modules", model_name),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return os.path.abspath(p)
    raise RuntimeError(
        f"Model file {model_name} not found. "
        f"Install models: python -m mediapipe.tasks.python.vision.utils.download_models"
    )


class MediaPipeFaceDetector:
    def __init__(self):
        # MediaPipe 0.10+ Tasks API
        self._face_detector = None
        self._face_landmarker = None

    def _ensure_initialized(self):
        """Lazy init models on first use."""
        if self._face_detector is not None:
            return
        # Try to get model paths
        try:
            face_model = _get_model_path("face_detection_short_range.tflite")
            land_model = _get_model_path("face_landmarker_v2_with_blendshapes.task")
        except RuntimeError:
            # Fallback: use legacy API if available
            logger.warning("MediaPipe tasks models not found, falling back to legacy API")
            self._use_legacy = True
            self._init_legacy()
            return

        self._face_detector = FaceDetector.create_from_options(
            mp.tasks.vision.FaceDetectorOptions(
                base_options=BaseOptions(model_asset_path=face_model),
                min_detection_confidence=0.5,
            )
        )
        self._face_landmarker = FaceLandmarker.create_from_options(
            mp.tasks.vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=land_model),
                num_faces=1,
                min_face_detection_confidence=0.5,
            )
        )
        self._use_legacy = False

    def _init_legacy(self):
        """Initialize using legacy API for compatibility."""
        try:
            mp_face = mp.solutions.face_detection
            self._legacy_detector = mp_face.FaceDetection(
                model_selection=1,
                min_detection_confidence=0.5,
            )
            mp_mesh = mp.solutions.face_mesh
            self._legacy_mesh = mp_mesh.FaceMesh(static_image_mode=True)
        except Exception as e:
            logger.error(f"Failed to initialize MediaPipe: {e}")
            raise

    # ── Quality Checks ─────────────────────────────────────────────────────

    def is_blurry(self, image, threshold=125):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        h, w = gray.shape
        scale_factor = (h * w) / (640 * 480)
        adjusted_threshold = threshold * scale_factor
        return laplacian_var < adjusted_threshold, laplacian_var

    def is_bad_lighting(self, image, low=38, high=220):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        brightness = gray.mean()
        if brightness < low:
            return True, f"Imagen muy oscura (brightness: {brightness:.2f})"
        if brightness > high:
            return True, f"Imagen sobreexpuesta (brightness: {brightness:.2f})"
        return False, f"OK ({brightness:.2f})"

    def head_framing_ok(self, image, landmarks):
        h, w, _ = image.shape
        # landmarks: list of NormalizedLandmark
        lm = {i: (l.x, l.y, l.z) for i, l in enumerate(landmarks)}

        # Landmark 10: forehead center
        forehead_y = lm.get(10, (0, 0, 0))[1] * h
        if forehead_y < 0.025 * h:
            return False, "Aleja la cámara o inclínala: se corta la parte superior de la cabeza"

        # Landmark 152: chin center
        chin_y = lm.get(152, (0, 0, 0))[1] * h
        face_height = chin_y - forehead_y
        if face_height <= 0:
            return False, "No se pudo analizar correctamente la cara"

        top_margin = forehead_y
        if top_margin < 0.035 * face_height:
            return False, "Necesitamos ver más zona superior del cráneo (incluye frente y coronilla en el encuadre)"

        return True, "OK"

    # ── Validation ─────────────────────────────────────────────────────────

    def validate(self, image) -> PortraitValidation:
        self._ensure_initialized()

        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        if self._use_legacy:
            return self._validate_legacy(img_rgb, image)
        else:
            return self._validate_tasks(img_rgb, image)

    def _validate_tasks(self, img_rgb, image) -> PortraitValidation:
        """Validate using MediaPipe Tasks API (0.10+)."""
        from mediapipe.tasks.python.vision.core.image_processing_options import ImageProcessingOptions

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)

        # Face detection
        detect_result = self._face_detector.detect(mp_image)
        if not detect_result.detections or len(detect_result.detections) == 0:
            return PortraitValidation(False, "No se detectó rostro")

        if len(detect_result.detections) > 1:
            return PortraitValidation(False, "Debe haber solo una persona en la imagen")

        # Blur check
        blurry, blur_score = self.is_blurry(image)
        logger.debug("blur_score=%.2f", blur_score)
        if blurry:
            return PortraitValidation(False, f"Imagen borrosa (score: {blur_score:.2f})")

        # Face landmarks for pose estimation
        land_result = self._face_landmarker.detect(mp_image)
        if not land_result.face_landmarks or len(land_result.face_landmarks) == 0:
            return PortraitValidation(False, "La cara debe estar de frente")

        landmarks = land_result.face_landmarks[0]

        # Frontal face check using eye/nose landmarks
        # Landmark indices in new API: left eye outer ~33, right eye outer ~263, nose ~1
        # For new model, approximate with available landmarks
        try:
            left_eye = landmarks[33]
            right_eye = landmarks[263]
            nose = landmarks[1]

            eye_diff = abs(left_eye.x - right_eye.x)
            center = (left_eye.x + right_eye.x) / 2
            nose_offset = abs(nose.x - center)

            if nose_offset > 0.085:
                return PortraitValidation(False, "La cara debe estar de frente")
            if eye_diff < 0.075:
                return PortraitValidation(False, "La cara debe estar de frente")
        except IndexError:
            # If landmarks not available, skip pose check but continue
            pass

        # Lighting check
        bad_light, lighting_msg = self.is_bad_lighting(image)
        logger.debug("lighting=%s", lighting_msg)
        if bad_light:
            return PortraitValidation(False, lighting_msg)

        # Framing check
        frame_ok, frame_msg = self.head_framing_ok(image, landmarks)
        logger.debug("head_framing=%s", frame_msg)
        if not frame_ok:
            return PortraitValidation(False, frame_msg)

        return PortraitValidation(True, "OK")

    def _validate_legacy(self, img_rgb, image) -> PortraitValidation:
        """Validate using legacy API (0.9.x)."""
        results = self._legacy_detector.process(img_rgb)
        if not results.detections:
            return PortraitValidation(False, "No se detectó rostro")

        if len(results.detections) > 1:
            return PortraitValidation(False, "Debe haber solo una persona en la imagen")

        blurry, blur_score = self.is_blurry(image)
        logger.debug("blur_score=%.2f", blur_score)
        if blurry:
            return PortraitValidation(False, f"Imagen borrosa (score: {blur_score:.2f})")

        mesh_results = self._legacy_mesh.process(img_rgb)
        if not mesh_results.multi_face_landmarks:
            return PortraitValidation(False, "La cara debe estar de frente")

        landmarks = mesh_results.multi_face_landmarks[0]

        left_eye = landmarks.landmark[33]
        right_eye = landmarks.landmark[263]
        nose = landmarks.landmark[1]

        eye_diff = abs(left_eye.x - right_eye.x)
        center = (left_eye.x + right_eye.x) / 2
        nose_offset = abs(nose.x - center)

        if nose_offset > 0.085:
            return PortraitValidation(False, "La cara debe estar de frente")
        if eye_diff < 0.075:
            return PortraitValidation(False, "La cara debe estar de frente")

        bad_light, lighting_msg = self.is_bad_lighting(image)
        logger.debug("lighting=%s", lighting_msg)
        if bad_light:
            return PortraitValidation(False, lighting_msg)

        frame_ok, frame_msg = self.head_framing_ok(image, landmarks)
        logger.debug("head_framing=%s", frame_msg)
        if not frame_ok:
            return PortraitValidation(False, frame_msg)

        return PortraitValidation(True, "OK", landmarks=landmarks)
