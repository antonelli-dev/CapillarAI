import logging

import cv2
import mediapipe as mp

from app.domain.portrait import PortraitValidation

logger = logging.getLogger(__name__)


class MediaPipeFaceDetector:
    def __init__(self):
        self.mp_face = mp.solutions.face_detection
        self.detector = self.mp_face.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.5,
        )

        self.mp_mesh = mp.solutions.face_mesh
        self.mesh = self.mp_mesh.FaceMesh(static_image_mode=True)

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
        lm = landmarks.landmark

        forehead_y = lm[10].y * h
        if forehead_y < 0.025 * h:
            return (
                False,
                "Aleja la cámara o inclínala: se corta la parte superior de la cabeza",
            )

        chin_y = lm[152].y * h
        face_height = chin_y - forehead_y
        if face_height <= 0:
            return False, "No se pudo analizar correctamente la cara"

        top_margin = forehead_y
        if top_margin < 0.035 * face_height:
            return (
                False,
                "Necesitamos ver más zona superior del cráneo (incluye frente y coronilla en el encuadre)",
            )

        return True, "OK"

    def validate(self, image) -> PortraitValidation:
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        results = self.detector.process(img_rgb)
        if not results.detections:
            return PortraitValidation(False, "No se detectó rostro")

        if len(results.detections) > 1:
            return PortraitValidation(False, "Debe haber solo una persona en la imagen")

        blurry, blur_score = self.is_blurry(image)
        logger.debug("blur_score=%.2f", blur_score)

        if blurry:
            return PortraitValidation(
                False,
                f"Imagen borrosa (score: {blur_score:.2f})",
            )

        mesh_results = self.mesh.process(img_rgb)
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
