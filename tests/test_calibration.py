from __future__ import annotations

import pytest

from app.core.calibration import EyeCalibrationManager


def test_calibration_timer_starts_on_first_valid_sample():
    manager = EyeCalibrationManager(duration_seconds=8, min_samples=10)

    assert manager.started_at is None
    assert manager.progress(timestamp=100.0) == 0.0

    manager.add_sample(0.30, timestamp=120.0)

    assert manager.started_at == pytest.approx(120.0)
    assert manager.elapsed_seconds(timestamp=121.5) == pytest.approx(1.5)


def test_calibration_requires_duration_and_minimum_samples():
    manager = EyeCalibrationManager(duration_seconds=3, min_samples=10)

    for index in range(10):
        manager.add_sample(0.30, timestamp=100.0 + index * 0.1)

    assert manager.is_complete(timestamp=102.9) is False
    assert manager.is_complete(timestamp=103.0) is True


def test_calibration_baseline_prefers_open_eye_samples():
    manager = EyeCalibrationManager(duration_seconds=3, min_samples=10)
    samples = [0.10, 0.11, 0.12, 0.28, 0.29, 0.30, 0.30, 0.31, 0.32, 0.33]

    for index, ear in enumerate(samples):
        manager.add_sample(ear, timestamp=100.0 + index * 0.4)

    result = manager.get_result(timestamp=104.0)

    assert result.success is True
    assert result.sample_count == 10
    assert result.baseline_ear > 0.28
    assert result.ear_threshold == pytest.approx(result.baseline_ear * 0.75)
