from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import List, Optional

from app.core.metrics import percentile, remove_outliers_iqr, safe_mean


@dataclass(frozen=True)
class CalibrationResult:
    success: bool
    baseline_ear: float
    ear_threshold: float
    sample_count: int
    duration_seconds: float
    message: str


class EyeCalibrationManager:
    """Mengumpulkan EAR mata terbuka untuk baseline personal."""

    def __init__(
        self,
        duration_seconds: float = 8.0,
        min_samples: int = 30,
        threshold_ratio: float = 0.75,
    ):
        self.duration_seconds = max(float(duration_seconds), 1.0)
        self.min_samples = max(int(min_samples), 10)
        self.threshold_ratio = float(threshold_ratio)
        self.started_at: Optional[float] = None
        self.ear_samples: List[float] = []

    def start(self, timestamp: Optional[float] = None) -> None:
        self.started_at = float(monotonic() if timestamp is None else timestamp)
        self.ear_samples = []

    def reset(self, timestamp: Optional[float] = None) -> None:
        self.start(timestamp)

    def add_sample(self, ear: float, timestamp: Optional[float] = None) -> None:
        if self.started_at is None:
            self.start(timestamp)
        if ear > 0:
            self.ear_samples.append(float(ear))

    def elapsed_seconds(self, timestamp: Optional[float] = None) -> float:
        if self.started_at is None:
            return 0.0
        now = float(monotonic() if timestamp is None else timestamp)
        return max(0.0, now - self.started_at)

    def progress(self, timestamp: Optional[float] = None) -> float:
        time_progress = self.elapsed_seconds(timestamp) / self.duration_seconds
        sample_progress = len(self.ear_samples) / self.min_samples
        return min(max(min(time_progress, sample_progress), 0.0), 1.0)

    def is_complete(self, timestamp: Optional[float] = None) -> bool:
        return (
            self.elapsed_seconds(timestamp) >= self.duration_seconds
            and len(self.ear_samples) >= self.min_samples
        )

    def get_result(self, timestamp: Optional[float] = None) -> CalibrationResult:
        duration = self.elapsed_seconds(timestamp)
        sample_count = len(self.ear_samples)

        if sample_count < self.min_samples:
            return CalibrationResult(
                success=False,
                baseline_ear=0.0,
                ear_threshold=0.0,
                sample_count=sample_count,
                duration_seconds=duration,
                message="Kalibrasi belum cukup. Pastikan wajah terlihat jelas dan mata terbuka normal.",
            )

        clean_samples = remove_outliers_iqr(self.ear_samples)
        if len(clean_samples) >= 5:
            cutoff = percentile(clean_samples, 40)
            open_samples = [value for value in clean_samples if value >= cutoff]
        else:
            open_samples = clean_samples

        baseline_ear = safe_mean(open_samples, default=0.0)
        if baseline_ear <= 0:
            return CalibrationResult(
                success=False,
                baseline_ear=0.0,
                ear_threshold=0.0,
                sample_count=sample_count,
                duration_seconds=duration,
                message="Kalibrasi gagal karena nilai EAR tidak valid.",
            )

        return CalibrationResult(
            success=True,
            baseline_ear=baseline_ear,
            ear_threshold=baseline_ear * self.threshold_ratio,
            sample_count=sample_count,
            duration_seconds=duration,
            message="Kalibrasi berhasil.",
        )
