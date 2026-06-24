import pytest

from app.core.fatigue_engine import EyeFatigueEngine, FatigueConfig


def build_engine() -> EyeFatigueEngine:
    config = FatigueConfig(
        reminder_interval_minutes=1,
        alert_cooldown_seconds=60,
        alert_grace_period_seconds=12,
        perclos_warmup_seconds=10,
        blink_rate_warmup_seconds=15,
    )
    engine = EyeFatigueEngine(config)
    engine.set_baseline(0.30)
    engine.start_monitoring(timestamp=1000.0)
    return engine


def test_no_alert_immediately_after_monitoring_starts():
    engine = build_engine()
    engine.update(0.10, timestamp=1000.1)
    engine.update(0.10, timestamp=1002.2)
    result = engine.update(0.10, timestamp=1003.0)

    assert result.status == "NORMAL"
    assert result.should_alert is False
    assert "awal" in result.message.lower()


def test_rest_reminder_after_duration_limit():
    engine = build_engine()
    result = engine.update(0.30, timestamp=1061.0)

    assert result.status == "PERLU_ISTIRAHAT"
    assert result.should_alert is True
    assert "istirahat" in result.message.lower()


def test_alert_cooldown_prevents_repetition():
    engine = build_engine()
    first = engine.update(0.30, timestamp=1061.0)
    second = engine.update(0.30, timestamp=1062.0)

    assert first.should_alert is True
    assert second.status == "PERLU_ISTIRAHAT"
    assert second.should_alert is False


def test_alert_can_return_after_cooldown():
    engine = build_engine()
    first = engine.update(0.30, timestamp=1061.0)
    second = engine.update(0.30, timestamp=1122.0)

    assert first.should_alert is True
    assert second.should_alert is True


def test_long_eye_closure_alerts_after_initial_grace_period():
    engine = build_engine()
    engine.update(0.30, timestamp=1012.0)
    engine.update(0.10, timestamp=1013.0)
    engine.update(0.10, timestamp=1014.0)
    result = engine.update(0.10, timestamp=1015.1)

    assert result.current_eye_closed_seconds >= 2.0
    assert result.status == "PERLU_ISTIRAHAT"
    assert result.should_alert is True


def test_mark_rest_taken_resets_duration_and_windows():
    engine = build_engine()
    before = engine.update(0.30, timestamp=1061.0)
    engine.mark_rest_taken(timestamp=1062.0)
    after = engine.update(0.30, timestamp=1070.0)

    assert before.status == "PERLU_ISTIRAHAT"
    assert after.duration_since_last_rest_seconds == pytest.approx(8.0)
    assert after.status != "PERLU_ISTIRAHAT"
    assert after.perclos_ready is False
    assert after.perclos == 0.0


def test_invalid_ear_is_not_detected_and_never_alerts():
    engine = build_engine()
    result = engine.update(0.0, timestamp=1020.0)

    assert result.status == "TIDAK_TERDETEKSI"
    assert result.should_alert is False
    assert result.fatigue_score == 0.0


def test_pause_gap_is_not_counted_and_temporal_evidence_restarts():
    engine = build_engine()
    engine.update(0.30, timestamp=1005.0)
    engine.pause_monitoring(timestamp=1005.0)
    engine.resume_monitoring(timestamp=1105.0)
    result = engine.update(0.30, timestamp=1106.0)

    assert result.screen_duration_seconds == pytest.approx(6.0)
    assert result.duration_since_last_rest_seconds == pytest.approx(6.0)
    assert result.perclos_ready is False
    assert result.blink_rate_ready is False
    assert result.status == "NORMAL"
