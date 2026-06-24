from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import monitoring, report
from app.database.db import Base, get_db
from app.main import app


class FakeDetector:
    def close(self):
        return None

    def detect(self, _frame):
        from app.core.detector import DetectionResult

        eye = [(10.0, 20.0), (12.0, 18.0), (16.0, 18.0), (18.0, 20.0), (16.0, 22.0), (12.0, 22.0)]
        return DetectionResult(
            success=True,
            message="ok",
            image_width=32,
            image_height=32,
            left_eye_points=eye,
            right_eye_points=eye,
            ear_left=0.30,
            ear_right=0.30,
            ear_avg=0.30,
        )


def encoded_test_frame() -> str:
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


def test_pages_health_and_monitoring_session(tmp_path: Path, monkeypatch):
    test_engine = create_engine(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    TestingSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(test_engine)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    monitoring.active_sessions.clear()
    monkeypatch.setattr(monitoring, "MediaPipeFaceMeshDetector", FakeDetector)
    monkeypatch.setattr(report, "REPORT_DIR", tmp_path / "reports")

    try:
        with TestClient(app) as client:
            root = client.get("/")
            assert root.status_code == 200
            assert "NetraWare" in root.text
            dashboard = client.get("/dashboard")
            assert dashboard.status_code == 200
            assert 'id="audioEnabled"' in dashboard.text
            assert 'id="audioVolume"' in dashboard.text
            dashboard_script = client.get("/assets/js/dashboard.js")
            assert dashboard_script.status_code == 200
            assert "playAlertSound" in dashboard_script.text
            assert "AudioContext" in dashboard_script.text
            assert "client-metric" in dashboard_script.text
            browser_monitor_script = client.get("/assets/js/browser-eye-monitor.js")
            assert browser_monitor_script.status_code == 200
            assert "FaceLandmarker" in browser_monitor_script.text
            assert client.get("/assets/js/api.js").status_code == 200
            assert client.get("/api").json()["version"] == "5.4.0"
            assert client.get("/api/health").json()["status"] == "healthy"
            assert client.get("/api/history/sessions").status_code == 404

            user = client.post(
                "/api/monitoring/users",
                json={"user_code": "TEST-001", "consent_given": True},
            )
            assert user.status_code == 200

            started = client.post(
                "/api/monitoring/session/start",
                json={"user_code": "TEST-001", "calibration_duration_seconds": 3},
            )
            assert started.status_code == 200
            code = started.json()["session_code"]

            frame = client.post(
                f"/api/monitoring/frame/{code}",
                json={"image_base64": encoded_test_frame()},
            )
            assert frame.status_code == 200
            assert frame.json()["phase"] == "CALIBRATING"
            assert frame.json()["eye_state"] == "KALIBRASI"

            # Paksa kalibrasi selesai agar pengujian mencakup transaksi metrik
            # pertama. Regresi versi 2.2 terjadi persis pada tahap ini.
            active = monitoring.active_sessions[code]
            active.calibration.duration_seconds = 0
            active.calibration.min_samples = 1

            calibrated = client.post(
                f"/api/monitoring/frame/{code}",
                json={"image_base64": encoded_test_frame()},
            )
            assert calibrated.status_code == 200
            assert calibrated.json()["phase"] == "CALIBRATION_DONE"

            monitoring_frame = client.post(
                f"/api/monitoring/frame/{code}",
                json={"image_base64": encoded_test_frame(), "save_interval_seconds": 0.25},
            )
            assert monitoring_frame.status_code == 200
            assert monitoring_frame.json()["phase"] == "MONITORING"
            assert monitoring_frame.json()["storage_ok"] is True

            resumed = client.post(f"/api/monitoring/resume/{code}")
            paused = client.post(f"/api/monitoring/pause/{code}")
            assert resumed.status_code == 200
            assert paused.status_code == 200
            assert resumed.json()["is_calibrated"] is True
            assert paused.json()["is_paused"] is True

            ended = client.post(f"/api/monitoring/session/end/{code}")
            assert ended.status_code == 200
            assert ended.json()["session"]["final_status"] == "NORMAL"

            csv_response = client.get(f"/api/report/{code}/csv")
            assert csv_response.status_code == 200
            assert csv_response.headers["content-type"].startswith("text/csv")
            assert len(csv_response.content) > 100

            pdf_response = client.get(f"/api/report/{code}/pdf")
            assert pdf_response.status_code == 200
            assert pdf_response.headers["content-type"] == "application/pdf"
            assert pdf_response.content.startswith(b"%PDF")
            assert len(pdf_response.content) > 1_000
    finally:
        monitoring.active_sessions.clear()
        app.dependency_overrides.clear()
        test_engine.dispose()
