from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import monotonic
from typing import Deque, Optional, Tuple

from app.core.metrics import clamp


@dataclass(frozen=True)
class FatigueConfig:
    """Konfigurasi analisis indikasi kelelahan mata.

    Threshold EAR dibuat personal dari baseline kalibrasi. Nilai default sengaja
    lebih konservatif daripada versi lama agar variasi kecil pada landmark tidak
    langsung dianggap sebagai mata tertutup.
    """

    ear_threshold_ratio: float = 0.68
    eye_open_threshold_ratio: float = 0.75

    min_blink_duration_seconds: float = 0.06
    max_blink_duration_seconds: float = 0.80
    min_closed_frames_for_blink: int = 2
    min_seconds_between_blinks: float = 0.12

    perclos_window_seconds: float = 60.0
    perclos_warmup_seconds: float = 10.0
    perclos_min_closed_seconds: float = 0.15

    blink_window_seconds: float = 60.0
    blink_rate_warmup_seconds: float = 15.0

    reminder_interval_minutes: float = 20.0
    alert_cooldown_seconds: float = 5.0
    alert_grace_period_seconds: float = 12.0
    long_eye_closure_seconds: float = 2.0


@dataclass(frozen=True)
class FatigueResult:
    ear: float
    ear_threshold: float
    is_eye_closed: bool
    eye_state: str
    blink_event: bool
    blink_count_total: int
    blink_rate_per_minute: float
    blink_rate_ready: bool
    perclos: float
    perclos_ready: bool
    screen_duration_seconds: float
    duration_since_last_rest_seconds: float
    current_eye_closed_seconds: float
    fatigue_score: float
    status: str
    message: str
    should_alert: bool


class EyeFatigueEngine:
    """State machine EAR, blink, PERCLOS, durasi layar, dan status peringatan.

    Seluruh durasi dihitung dengan satu domain waktu yang konsisten. Pada backend,
    timestamp berasal dari ``time.monotonic()`` sehingga perubahan jam perangkat
    atau timestamp browser tidak membuat durasi melonjak.
    """

    def __init__(self, config: Optional[FatigueConfig] = None):
        self.config = config or FatigueConfig()

        self.baseline_ear: Optional[float] = None
        self.ear_threshold: Optional[float] = None
        self.eye_open_threshold: Optional[float] = None

        self.session_started_at: Optional[float] = None
        self.last_rest_at: Optional[float] = None
        self.last_alert_at: Optional[float] = None
        self.last_update_at: Optional[float] = None
        self.evidence_started_at: Optional[float] = None
        self.paused_at: Optional[float] = None

        self.total_blink_count = 0
        self.last_blink_at: Optional[float] = None
        self.blink_timestamps: Deque[float] = deque()

        # (timestamp, sustained_closed). Nilai sustained_closed baru bernilai 1
        # setelah penutupan mata melewati durasi minimum PERCLOS. Blink singkat
        # tidak langsung menaikkan PERCLOS.
        self.eye_state_window: Deque[Tuple[float, int]] = deque()

        self.was_eye_closed = False
        self.closed_started_at: Optional[float] = None
        self.current_eye_closed_seconds = 0.0
        self.closed_frame_count = 0

    def set_baseline(self, baseline_ear: float) -> None:
        if baseline_ear <= 0:
            raise ValueError("Baseline EAR harus lebih besar dari 0.")

        self.baseline_ear = float(baseline_ear)
        self.ear_threshold = self.baseline_ear * self.config.ear_threshold_ratio
        self.eye_open_threshold = self.baseline_ear * self.config.eye_open_threshold_ratio

    def start_monitoring(self, timestamp: Optional[float] = None) -> None:
        """Memulai timer dan membersihkan seluruh evidence sesi.

        Fungsi ini dipanggil setelah kalibrasi selesai. Dengan demikian waktu
        menunggu izin kamera atau proses kalibrasi tidak dihitung sebagai durasi
        penggunaan layar.
        """

        now = self._resolve_timestamp(timestamp)
        self.session_started_at = now
        self.last_rest_at = now
        self.last_alert_at = None
        self.last_update_at = now
        self.evidence_started_at = now
        self.paused_at = None

        self.total_blink_count = 0
        self.last_blink_at = None
        self.blink_timestamps.clear()
        self.eye_state_window.clear()
        self._reset_eye_closure()

    def mark_rest_taken(self, timestamp: Optional[float] = None) -> None:
        now = self._resolve_timestamp(timestamp)
        self._ensure_started(now)
        self.resume_monitoring(timestamp=now)
        self.last_rest_at = now
        self.last_alert_at = None
        self._reset_temporal_evidence(now)

    def pause_monitoring(self, timestamp: Optional[float] = None) -> None:
        now = self._resolve_timestamp(timestamp)
        if self.session_started_at is None or self.paused_at is not None:
            return
        self.paused_at = now
        self._reset_eye_closure()

    def resume_monitoring(self, timestamp: Optional[float] = None) -> None:
        now = self._resolve_timestamp(timestamp)
        if self.paused_at is None:
            return

        pause_duration = max(0.0, now - self.paused_at)
        if self.session_started_at is not None:
            self.session_started_at += pause_duration
        if self.last_rest_at is not None:
            self.last_rest_at += pause_duration
        if self.last_alert_at is not None:
            self.last_alert_at += pause_duration

        self.paused_at = None
        self.last_update_at = now
        self._reset_temporal_evidence(now)

    def update(self, ear: float, timestamp: Optional[float] = None) -> FatigueResult:
        now = self._resolve_timestamp(timestamp)
        self._ensure_started(now)
        self.resume_monitoring(timestamp=now)

        if ear <= 0:
            return self.update_missing(timestamp=now)

        if self.ear_threshold is None or self.eye_open_threshold is None:
            self.set_baseline(ear)

        blink_event, is_eye_closed = self._update_eye_state(ear=ear, timestamp=now)
        sustained_closed = (
            is_eye_closed
            and self.current_eye_closed_seconds >= self.config.perclos_min_closed_seconds
        )

        self.eye_state_window.append((now, 1 if sustained_closed else 0))
        self._prune_old_samples(now)

        screen_duration = self._screen_duration(now)
        duration_since_last_rest = self._duration_since_rest(now)

        perclos_ready = self._perclos_ready(now)
        perclos = self._calculate_recent_perclos(now) if perclos_ready else 0.0

        blink_rate_ready = self._evidence_duration(now) >= self.config.blink_rate_warmup_seconds
        blink_rate = self._calculate_recent_blink_rate(now) if blink_rate_ready else 0.0

        fatigue_score = self._calculate_fatigue_score(
            blink_rate_per_minute=blink_rate,
            blink_rate_ready=blink_rate_ready,
            perclos=perclos,
            perclos_ready=perclos_ready,
            duration_since_last_rest_seconds=duration_since_last_rest,
            current_eye_closed_seconds=self.current_eye_closed_seconds,
        )

        status, message = self._determine_status(
            fatigue_score=fatigue_score,
            screen_duration_seconds=screen_duration,
            duration_since_last_rest_seconds=duration_since_last_rest,
            current_eye_closed_seconds=self.current_eye_closed_seconds,
            perclos_ready=perclos_ready,
        )
        should_alert = self._should_send_alert(status=status, timestamp=now)
        self.last_update_at = now

        return FatigueResult(
            ear=float(ear),
            ear_threshold=self.ear_threshold or 0.0,
            is_eye_closed=is_eye_closed,
            eye_state="TERTUTUP" if is_eye_closed else "TERBUKA",
            blink_event=blink_event,
            blink_count_total=self.total_blink_count,
            blink_rate_per_minute=blink_rate,
            blink_rate_ready=blink_rate_ready,
            perclos=perclos,
            perclos_ready=perclos_ready,
            screen_duration_seconds=screen_duration,
            duration_since_last_rest_seconds=duration_since_last_rest,
            current_eye_closed_seconds=self.current_eye_closed_seconds,
            fatigue_score=fatigue_score,
            status=status,
            message=message,
            should_alert=should_alert,
        )

    def update_missing(self, timestamp: Optional[float] = None) -> FatigueResult:
        """Menghasilkan respons aman saat wajah/mata tidak terdeteksi.

        Episode mata tertutup dibatalkan. Tanpa langkah ini, kehilangan wajah saat
        mata sedang dianggap tertutup dapat membuat durasi penutupan terus terbawa
        dan memicu peringatan palsu ketika wajah muncul kembali.
        """

        now = self._resolve_timestamp(timestamp)
        self._ensure_started(now)
        self.resume_monitoring(timestamp=now)
        self._reset_eye_closure()
        self._prune_old_samples(now)
        self.last_update_at = now

        return FatigueResult(
            ear=0.0,
            ear_threshold=self.ear_threshold or 0.0,
            is_eye_closed=False,
            eye_state="TIDAK_TERDETEKSI",
            blink_event=False,
            blink_count_total=self.total_blink_count,
            blink_rate_per_minute=(
                self._calculate_recent_blink_rate(now)
                if self._evidence_duration(now) >= self.config.blink_rate_warmup_seconds
                else 0.0
            ),
            blink_rate_ready=self._evidence_duration(now) >= self.config.blink_rate_warmup_seconds,
            perclos=(self._calculate_recent_perclos(now) if self._perclos_ready(now) else 0.0),
            perclos_ready=self._perclos_ready(now),
            screen_duration_seconds=self._screen_duration(now),
            duration_since_last_rest_seconds=self._duration_since_rest(now),
            current_eye_closed_seconds=0.0,
            fatigue_score=0.0,
            status="TIDAK_TERDETEKSI",
            message="Wajah atau mata tidak terdeteksi dengan jelas.",
            should_alert=False,
        )

    def _update_eye_state(self, ear: float, timestamp: float) -> Tuple[bool, bool]:
        close_threshold = self.ear_threshold or 0.0
        open_threshold = self.eye_open_threshold or close_threshold

        if self.was_eye_closed:
            is_closed_now = ear < open_threshold
        else:
            is_closed_now = ear <= close_threshold

        blink_event = False

        if is_closed_now:
            if not self.was_eye_closed:
                self.was_eye_closed = True
                self.closed_started_at = timestamp
                self.closed_frame_count = 1
                self.current_eye_closed_seconds = 0.0
            else:
                self.closed_frame_count += 1
                if self.closed_started_at is not None:
                    self.current_eye_closed_seconds = max(0.0, timestamp - self.closed_started_at)
            return blink_event, True

        if self.was_eye_closed and self.closed_started_at is not None:
            closure_duration = max(0.0, timestamp - self.closed_started_at)
            blink_event = self._register_blink_if_valid(timestamp, closure_duration)

        self._reset_eye_closure()
        return blink_event, False

    def _register_blink_if_valid(self, timestamp: float, closure_duration: float) -> bool:
        if self.closed_frame_count < self.config.min_closed_frames_for_blink:
            return False
        if closure_duration < self.config.min_blink_duration_seconds:
            return False
        if closure_duration > self.config.max_blink_duration_seconds:
            return False
        if (
            self.last_blink_at is not None
            and timestamp - self.last_blink_at < self.config.min_seconds_between_blinks
        ):
            return False

        self.total_blink_count += 1
        self.last_blink_at = timestamp
        self.blink_timestamps.append(timestamp)
        return True

    def _reset_eye_closure(self) -> None:
        self.was_eye_closed = False
        self.closed_started_at = None
        self.current_eye_closed_seconds = 0.0
        self.closed_frame_count = 0

    def _prune_old_samples(self, timestamp: float) -> None:
        perclos_limit = timestamp - self.config.perclos_window_seconds
        blink_limit = timestamp - self.config.blink_window_seconds

        # Pertahankan satu sampel tepat sebelum batas agar integrasi waktu pada
        # sisi kiri window tetap memiliki state yang valid.
        while len(self.eye_state_window) > 1 and self.eye_state_window[1][0] < perclos_limit:
            self.eye_state_window.popleft()

        while self.blink_timestamps and self.blink_timestamps[0] < blink_limit:
            self.blink_timestamps.popleft()

    def _calculate_recent_blink_rate(self, timestamp: float) -> float:
        if not self.blink_timestamps:
            return 0.0

        evidence_start = self.evidence_started_at if self.evidence_started_at is not None else timestamp
        observation_start = max(evidence_start, timestamp - self.config.blink_window_seconds)
        observation_seconds = max(timestamp - observation_start, 1e-6)
        return round((len(self.blink_timestamps) / observation_seconds) * 60.0, 3)

    def _perclos_ready(self, timestamp: float) -> bool:
        return (
            self._evidence_duration(timestamp) >= self.config.perclos_warmup_seconds
            and len(self.eye_state_window) >= 2
        )

    def _calculate_recent_perclos(self, timestamp: float) -> float:
        if len(self.eye_state_window) < 2:
            return 0.0

        evidence_start = self.evidence_started_at if self.evidence_started_at is not None else timestamp
        window_start = max(evidence_start, timestamp - self.config.perclos_window_seconds)
        samples = list(self.eye_state_window)

        closed_seconds = 0.0
        observed_seconds = 0.0

        for index, (sample_time, state) in enumerate(samples):
            next_time = samples[index + 1][0] if index + 1 < len(samples) else timestamp
            interval_start = max(sample_time, window_start)
            interval_end = min(next_time, timestamp)
            interval = max(0.0, interval_end - interval_start)
            observed_seconds += interval
            if state == 1:
                closed_seconds += interval

        if observed_seconds <= 0:
            return 0.0

        return round(clamp(closed_seconds / observed_seconds, 0.0, 1.0), 4)

    def _calculate_fatigue_score(
        self,
        *,
        blink_rate_per_minute: float,
        blink_rate_ready: bool,
        perclos: float,
        perclos_ready: bool,
        duration_since_last_rest_seconds: float,
        current_eye_closed_seconds: float,
    ) -> float:
        score = 0.0

        if perclos_ready:
            score += clamp(perclos / 0.40, 0.0, 1.0) * 45.0

        score += clamp(
            current_eye_closed_seconds / max(self.config.long_eye_closure_seconds, 0.1),
            0.0,
            1.0,
        ) * 25.0

        minutes_since_rest = duration_since_last_rest_seconds / 60.0
        # Tidak memberi penalti pada menit awal. Kontribusi durasi meningkat dari
        # setengah interval reminder hingga batas reminder.
        duration_start = self.config.reminder_interval_minutes * 0.5
        duration_span = max(self.config.reminder_interval_minutes - duration_start, 0.1)
        score += clamp((minutes_since_rest - duration_start) / duration_span, 0.0, 1.0) * 20.0

        if blink_rate_ready:
            if blink_rate_per_minute < 8:
                score += clamp((8 - blink_rate_per_minute) / 8, 0.0, 1.0) * 10.0
            elif blink_rate_per_minute > 30:
                score += clamp((blink_rate_per_minute - 30) / 20, 0.0, 1.0) * 10.0

        return round(clamp(score, 0.0, 100.0), 2)

    def _determine_status(
        self,
        *,
        fatigue_score: float,
        screen_duration_seconds: float,
        duration_since_last_rest_seconds: float,
        current_eye_closed_seconds: float,
        perclos_ready: bool,
    ) -> Tuple[str, str]:
        if screen_duration_seconds < self.config.alert_grace_period_seconds:
            return "NORMAL", "Mengumpulkan data awal monitoring."

        if current_eye_closed_seconds >= self.config.long_eye_closure_seconds:
            return "PERLU_ISTIRAHAT", "Mata terdeteksi tertutup cukup lama. Segera istirahat sejenak."

        if duration_since_last_rest_seconds / 60.0 >= self.config.reminder_interval_minutes:
            return "PERLU_ISTIRAHAT", "Waktu penggunaan layar sudah mencapai batas. Istirahat dan terapkan aturan 20-20-20."

        if fatigue_score >= 70:
            return "PERLU_ISTIRAHAT", "Indikasi kelelahan mata cukup tinggi. Disarankan beristirahat."

        if fatigue_score >= 40:
            return "WASPADA", "Terdapat tanda awal kelelahan mata. Alihkan pandangan dari layar sesaat."

        if not perclos_ready:
            return "NORMAL", "Monitoring aktif; data PERCLOS sedang dikumpulkan."

        return "NORMAL", "Kondisi mata terpantau normal."

    def _should_send_alert(self, status: str, timestamp: float) -> bool:
        if status != "PERLU_ISTIRAHAT":
            return False
        if self._screen_duration(timestamp) < self.config.alert_grace_period_seconds:
            return False
        if (
            self.last_alert_at is not None
            and timestamp - self.last_alert_at < self.config.alert_cooldown_seconds
        ):
            return False

        self.last_alert_at = timestamp
        return True

    def _ensure_started(self, timestamp: float) -> None:
        if self.session_started_at is None:
            self.session_started_at = timestamp
        if self.last_rest_at is None:
            self.last_rest_at = timestamp
        if self.evidence_started_at is None:
            self.evidence_started_at = timestamp

    def _reset_temporal_evidence(self, timestamp: float) -> None:
        self.evidence_started_at = timestamp
        self.blink_timestamps.clear()
        self.eye_state_window.clear()
        self.last_blink_at = None
        self._reset_eye_closure()

    def _evidence_duration(self, timestamp: float) -> float:
        if self.evidence_started_at is None:
            return 0.0
        return max(0.0, timestamp - self.evidence_started_at)

    def _screen_duration(self, timestamp: float) -> float:
        if self.session_started_at is None:
            return 0.0
        return max(0.0, timestamp - self.session_started_at)

    def _duration_since_rest(self, timestamp: float) -> float:
        if self.last_rest_at is None:
            return 0.0
        return max(0.0, timestamp - self.last_rest_at)

    @staticmethod
    def _resolve_timestamp(timestamp: Optional[float]) -> float:
        return float(monotonic() if timestamp is None else timestamp)
