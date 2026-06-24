from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_code = Column(String(50), unique=True, index=True, nullable=False)
    consent_given = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    sessions = relationship("MonitoringSession", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_code": self.user_code,
            "consent_given": self.consent_given,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MonitoringSession(Base):
    __tablename__ = "monitoring_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_code = Column(String(100), unique=True, index=True, default=lambda: str(uuid4()), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mode = Column(String(30), default="LIVE_CAMERA", nullable=False)
    started_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    baseline_ear = Column(Float, nullable=True)
    ear_threshold = Column(Float, nullable=True)
    total_duration_seconds = Column(Float, default=0.0, nullable=False)
    total_blink_count = Column(Integer, default=0, nullable=False)
    avg_ear = Column(Float, default=0.0, nullable=False)
    avg_blink_rate = Column(Float, default=0.0, nullable=False)
    avg_perclos = Column(Float, default=0.0, nullable=False)
    avg_fatigue_score = Column(Float, default=0.0, nullable=False)
    max_fatigue_score = Column(Float, default=0.0, nullable=False)
    final_status = Column(String(50), default="BELUM_SELESAI", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="sessions")
    metrics = relationship("MetricRecord", back_populates="session", cascade="all, delete-orphan")
    alerts = relationship("AlertRecord", back_populates="session", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        fields = (
            "id", "session_code", "user_id", "mode", "baseline_ear", "ear_threshold",
            "total_duration_seconds", "total_blink_count", "avg_ear", "avg_blink_rate",
            "avg_perclos", "avg_fatigue_score", "max_fatigue_score", "final_status", "notes",
        )
        data = {field: getattr(self, field) for field in fields}
        data.update(
            started_at=self.started_at.isoformat() if self.started_at else None,
            ended_at=self.ended_at.isoformat() if self.ended_at else None,
            created_at=self.created_at.isoformat() if self.created_at else None,
        )
        return data


class MetricRecord(Base):
    __tablename__ = "metric_records"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("monitoring_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    elapsed_seconds = Column(Float, default=0.0, nullable=False)
    ear_left = Column(Float, default=0.0, nullable=False)
    ear_right = Column(Float, default=0.0, nullable=False)
    ear_avg = Column(Float, default=0.0, nullable=False)
    ear = Column(Float, default=0.0, nullable=False)
    ear_threshold = Column(Float, default=0.0, nullable=False)
    is_eye_closed = Column(Boolean, default=False, nullable=False)
    blink_count_total = Column(Integer, default=0, nullable=False)
    blink_rate_per_minute = Column(Float, default=0.0, nullable=False)
    blink_rate_ready = Column(Boolean, default=False, nullable=False)
    perclos = Column(Float, default=0.0, nullable=False)
    perclos_ready = Column(Boolean, default=False, nullable=False)
    screen_duration_seconds = Column(Float, default=0.0, nullable=False)
    duration_since_last_rest_seconds = Column(Float, default=0.0, nullable=False)
    current_eye_closed_seconds = Column(Float, default=0.0, nullable=False)
    fatigue_score = Column(Float, default=0.0, nullable=False)
    status = Column(String(50), default="NORMAL", nullable=False)
    message = Column(Text, nullable=True)
    session = relationship("MonitoringSession", back_populates="metrics")

    def to_dict(self) -> dict:
        fields = (
            "id", "session_id", "elapsed_seconds", "ear_left", "ear_right", "ear_avg", "ear",
            "ear_threshold", "is_eye_closed", "blink_count_total", "blink_rate_per_minute",
            "blink_rate_ready", "perclos", "perclos_ready", "screen_duration_seconds",
            "duration_since_last_rest_seconds", "current_eye_closed_seconds", "fatigue_score",
            "status", "message",
        )
        data = {field: getattr(self, field) for field in fields}
        data["captured_at"] = self.captured_at.isoformat() if self.captured_at else None
        return data


class AlertRecord(Base):
    __tablename__ = "alert_records"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("monitoring_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    alert_type = Column(String(50), default="REST_REMINDER", nullable=False)
    message = Column(Text, nullable=False)
    fatigue_score_at_alert = Column(Float, default=0.0, nullable=False)
    is_acknowledged = Column(Boolean, default=False, nullable=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    session = relationship("MonitoringSession", back_populates="alerts")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "alert_type": self.alert_type,
            "message": self.message,
            "fatigue_score_at_alert": self.fatigue_score_at_alert,
            "is_acknowledged": self.is_acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        }
