from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Iterable, List, Optional

import cv2
import mediapipe as mp
import numpy as np

from app.core.metrics import (
    LEFT_EYE_INDICES,
    RIGHT_EYE_INDICES,
    Point,
    calculate_ear,
)
from app.core.model_manager import DEFAULT_MODEL_PATH, ModelDownloadError, ensure_face_landmarker_model


class DetectorInitializationError(RuntimeError):
    """Raised when neither MediaPipe backend can be initialized."""


@dataclass(frozen=True)
class DetectionResult:
    success: bool
    message: str
    image_width: int = 0
    image_height: int = 0
    landmarks: Optional[List[Point]] = None
    left_eye_points: Optional[List[Point]] = None
    right_eye_points: Optional[List[Point]] = None
    ear_left: float = 0.0
    ear_right: float = 0.0
    ear_avg: float = 0.0


class MediaPipeFaceMeshDetector:
    """Detect facial landmarks and calculate EAR for both eyes.

    MediaPipe <= 0.10.14 exposes the legacy ``solutions.face_mesh`` API.
    Current MediaPipe releases use the Tasks Face Landmarker API. Supporting
    both keeps the project usable on Python 3.10-3.13 without duplicating the
    fatigue-analysis logic.
    """

    def __init__(
        self,
        max_num_faces: int = 1,
        refine_landmarks: bool = True,
        min_detection_confidence: float = 0.45,
        min_tracking_confidence: float = 0.45,
        static_image_mode: bool = False,
        max_frame_width: int = 480,
        model_path: Path | str = DEFAULT_MODEL_PATH,
    ):
        self.max_frame_width = max_frame_width
        self._backend = ""
        self._detector = None
        self._last_timestamp_ms = 0

        try:
            solutions = getattr(mp, "solutions", None)
            if solutions is not None and hasattr(solutions, "face_mesh"):
                self._backend = "legacy"
                self._detector = solutions.face_mesh.FaceMesh(
                    static_image_mode=static_image_mode,
                    max_num_faces=max_num_faces,
                    refine_landmarks=refine_landmarks,
                    min_detection_confidence=min_detection_confidence,
                    min_tracking_confidence=min_tracking_confidence,
                )
            else:
                self._backend = "tasks"
                self._detector = self._create_tasks_detector(
                    max_num_faces=max_num_faces,
                    min_detection_confidence=min_detection_confidence,
                    min_tracking_confidence=min_tracking_confidence,
                    model_path=model_path,
                )
        except (ModelDownloadError, OSError, RuntimeError, ValueError) as exc:
            raise DetectorInitializationError(str(exc)) from exc

    @staticmethod
    def _create_tasks_detector(
        *,
        max_num_faces: int,
        min_detection_confidence: float,
        min_tracking_confidence: float,
        model_path: Path | str,
    ):
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as exc:
            raise DetectorInitializationError(
                "Instalasi MediaPipe tidak menyediakan Face Landmarker. "
                "Pasang ulang dependensi melalui `pip install -r requirements.txt`."
            ) from exc

        verified_model = ensure_face_landmarker_model(model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(verified_model)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=max_num_faces,
            min_face_detection_confidence=min_detection_confidence,
            min_face_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        return vision.FaceLandmarker.create_from_options(options)

    def detect(self, frame_bgr: np.ndarray) -> DetectionResult:
        if frame_bgr is None:
            return DetectionResult(False, "Frame kamera kosong atau tidak valid.")
        if not isinstance(frame_bgr, np.ndarray) or frame_bgr.ndim != 3 or frame_bgr.shape[2] < 3:
            return DetectionResult(
                False,
                "Format frame tidak valid. Frame harus berupa gambar berwarna BGR.",
            )

        frame_bgr = self._resize_for_realtime(frame_bgr)
        image_height, image_width = frame_bgr.shape[:2]
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        if self._backend == "legacy":
            raw_result = self._detector.process(frame_rgb)
            if not raw_result.multi_face_landmarks:
                return DetectionResult(
                    False,
                    "Wajah tidak terdeteksi.",
                    image_width=image_width,
                    image_height=image_height,
                )
            normalized_landmarks = raw_result.multi_face_landmarks[0].landmark
        else:
            timestamp_ms = max(int(monotonic() * 1000), self._last_timestamp_ms + 1)
            self._last_timestamp_ms = timestamp_ms
            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=np.ascontiguousarray(frame_rgb),
            )
            raw_result = self._detector.detect_for_video(mp_image, timestamp_ms)
            if not raw_result.face_landmarks:
                return DetectionResult(
                    False,
                    "Wajah tidak terdeteksi.",
                    image_width=image_width,
                    image_height=image_height,
                )
            normalized_landmarks = raw_result.face_landmarks[0]

        pixel_landmarks = self._convert_landmarks_to_pixels(
            normalized_landmarks,
            image_width=image_width,
            image_height=image_height,
        )
        required_max_index = max(max(LEFT_EYE_INDICES), max(RIGHT_EYE_INDICES))
        if len(pixel_landmarks) <= required_max_index:
            return DetectionResult(
                False,
                "Jumlah landmark tidak mencukupi untuk mengambil area mata.",
                image_width=image_width,
                image_height=image_height,
                landmarks=pixel_landmarks,
            )

        left_eye_points = [pixel_landmarks[index] for index in LEFT_EYE_INDICES]
        right_eye_points = [pixel_landmarks[index] for index in RIGHT_EYE_INDICES]
        ear_left = calculate_ear(left_eye_points)
        ear_right = calculate_ear(right_eye_points)

        return DetectionResult(
            success=True,
            message="Wajah dan landmark mata berhasil terdeteksi.",
            image_width=image_width,
            image_height=image_height,
            landmarks=pixel_landmarks,
            left_eye_points=left_eye_points,
            right_eye_points=right_eye_points,
            ear_left=ear_left,
            ear_right=ear_right,
            ear_avg=(ear_left + ear_right) / 2.0,
        )

    def _resize_for_realtime(self, frame_bgr: np.ndarray) -> np.ndarray:
        height, width = frame_bgr.shape[:2]
        if self.max_frame_width <= 0 or width <= self.max_frame_width:
            return frame_bgr

        scale = self.max_frame_width / width
        return cv2.resize(
            frame_bgr,
            (self.max_frame_width, max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    @staticmethod
    def _convert_landmarks_to_pixels(
        normalized_landmarks: Iterable,
        *,
        image_width: int,
        image_height: int,
    ) -> List[Point]:
        return [
            (float(landmark.x) * image_width, float(landmark.y) * image_height)
            for landmark in normalized_landmarks
        ]

    def close(self) -> None:
        if self._detector is not None:
            self._detector.close()
            self._detector = None
