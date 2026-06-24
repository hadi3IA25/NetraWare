import pytest

from app.core.fatigue_engine import EyeFatigueEngine, FatigueConfig


def build_engine(**overrides) -> EyeFatigueEngine:
    values = dict(
        ear_threshold_ratio=0.75,
        eye_open_threshold_ratio=0.84,
        min_blink_duration_seconds=0.06,
        max_blink_duration_seconds=0.80,
        min_closed_frames_for_blink=2,
        min_seconds_between_blinks=0.12,
        perclos_window_seconds=60,
        perclos_warmup_seconds=10,
        perclos_min_closed_seconds=0.15,
        blink_window_seconds=60,
        blink_rate_warmup_seconds=15,
        reminder_interval_minutes=20,
        alert_cooldown_seconds=60,
        alert_grace_period_seconds=12,
    )
    values.update(overrides)
    engine = EyeFatigueEngine(FatigueConfig(**values))
    engine.set_baseline(0.30)
    engine.start_monitoring(timestamp=1000.0)
    return engine


def perform_blink(engine: EyeFatigueEngine, start: float):
    engine.update(0.30, timestamp=start)
    engine.update(0.10, timestamp=start + 0.10)
    engine.update(0.10, timestamp=start + 0.17)
    return engine.update(0.30, timestamp=start + 0.28)


def test_single_closed_frame_is_not_counted_as_blink():
    engine = build_engine()
    engine.update(0.30, timestamp=1000.0)
    engine.update(0.10, timestamp=1000.10)
    result = engine.update(0.30, timestamp=1000.14)

    assert result.blink_count_total == 0
    assert result.blink_event is False


def test_valid_close_open_episode_is_counted_once():
    engine = build_engine()
    result = perform_blink(engine, 1000.0)

    assert result.blink_count_total == 1
    assert result.blink_event is True
    assert result.is_eye_closed is False


def test_long_closure_is_not_misclassified_as_normal_blink():
    engine = build_engine()
    engine.update(0.30, timestamp=1000.0)
    engine.update(0.10, timestamp=1000.1)
    engine.update(0.10, timestamp=1001.0)
    result = engine.update(0.30, timestamp=1001.2)

    assert result.blink_count_total == 0


def test_hysteresis_keeps_eye_closed_around_threshold():
    engine = build_engine()
    engine.update(0.30, timestamp=1000.0)
    first = engine.update(0.10, timestamp=1000.1)
    middle = engine.update(0.24, timestamp=1000.17)  # above close, below open threshold
    result = engine.update(0.30, timestamp=1000.28)

    assert first.is_eye_closed is True
    assert middle.is_eye_closed is True
    assert result.blink_count_total == 1


def test_blink_rate_waits_for_warmup_and_uses_observed_duration():
    engine = build_engine()
    perform_blink(engine, 1000.0)
    early = perform_blink(engine, 1002.0)
    ready = engine.update(0.30, timestamp=1015.0)

    assert early.blink_rate_ready is False
    assert early.blink_rate_per_minute == 0.0
    assert ready.blink_rate_ready is True
    assert ready.blink_rate_per_minute == pytest.approx(8.0, abs=0.01)


def test_perclos_is_zero_during_initial_warmup():
    engine = build_engine()
    engine.update(0.10, timestamp=1000.1)
    engine.update(0.10, timestamp=1001.0)
    result = engine.update(0.10, timestamp=1002.0)

    assert result.perclos_ready is False
    assert result.perclos == 0.0
    assert result.should_alert is False


def test_time_weighted_perclos_after_warmup():
    engine = build_engine()
    engine.update(0.30, timestamp=1000.0)
    engine.update(0.10, timestamp=1005.0)
    engine.update(0.10, timestamp=1005.2)
    engine.update(0.10, timestamp=1009.0)
    result = engine.update(0.10, timestamp=1010.0)

    assert result.perclos_ready is True
    assert result.perclos == pytest.approx(0.48, abs=0.01)


def test_missing_detection_cancels_open_closure_episode():
    engine = build_engine()
    engine.update(0.10, timestamp=1000.1)
    engine.update(0.10, timestamp=1000.3)
    missing = engine.update_missing(timestamp=1000.4)
    reopened = engine.update(0.30, timestamp=1000.5)

    assert missing.status == "TIDAK_TERDETEKSI"
    assert missing.current_eye_closed_seconds == 0.0
    assert reopened.blink_count_total == 0
