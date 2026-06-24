from types import SimpleNamespace

import numpy as np

from app.core.detector import MediaPipeFaceMeshDetector


def test_convert_landmarks_to_pixel_coordinates():
    landmarks = [SimpleNamespace(x=0.25, y=0.5), SimpleNamespace(x=1.0, y=0.0)]
    points = MediaPipeFaceMeshDetector._convert_landmarks_to_pixels(
        landmarks,
        image_width=400,
        image_height=200,
    )
    assert points == [(100.0, 100.0), (400.0, 0.0)]


def test_resize_preserves_small_frame_and_reduces_large_frame():
    detector = MediaPipeFaceMeshDetector.__new__(MediaPipeFaceMeshDetector)
    detector.max_frame_width = 480

    small = np.zeros((200, 300, 3), dtype=np.uint8)
    large = np.zeros((720, 1280, 3), dtype=np.uint8)

    assert detector._resize_for_realtime(small) is small
    resized = detector._resize_for_realtime(large)
    assert resized.shape == (270, 480, 3)
