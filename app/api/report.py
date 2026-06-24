from __future__ import annotations

import logging
import os
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.report_generator import ReportGenerator
from app.database.db import get_db
from app.database.models import MetricRecord, MonitoringSession, User
from app.utils.file_cleanup import cleanup_old_files

router = APIRouter(prefix="/report", tags=["Report"])
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = PROJECT_ROOT / "data" / "reports"
REPORT_MAX_AGE_HOURS = 24
REPORT_LOCK = Lock()
LOGGER = logging.getLogger(__name__)



def get_session_or_404(db: Session, session_code: str) -> MonitoringSession:
    session = db.query(MonitoringSession).filter_by(session_code=session_code).first()
    if not session:
        raise HTTPException(status_code=404, detail="Sesi monitoring tidak ditemukan.")
    return session


def load_metrics(db: Session, session_id: int) -> list[MetricRecord]:
    return (
        db.query(MetricRecord)
        .filter_by(session_id=session_id)
        .order_by(MetricRecord.captured_at.asc())
        .all()
    )


def format_duration(seconds: float) -> str:
    total = int(seconds or 0)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} jam {minutes} menit {seconds} detik"
    if minutes:
        return f"{minutes} menit {seconds} detik"
    return f"{seconds} detik"


def prepare_report_folder() -> ReportGenerator:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    cleanup_old_files(REPORT_DIR, max_age_hours=REPORT_MAX_AGE_HOURS)
    return ReportGenerator(output_dir=str(REPORT_DIR))


def active_report_token() -> str:
    """
    Token proteksi laporan dibaca saat request berjalan agar perubahan environment
    pada platform deployment atau pengujian tidak memerlukan import ulang modul.

    REPORT_ACCESS_TOKEN adalah nama utama. ADMIN_EXPORT_TOKEN tetap didukung
    sebagai fallback agar konfigurasi versi sebelumnya tidak langsung rusak.
    Jika keduanya kosong, endpoint laporan tetap dapat diakses hanya dengan
    session_code seperti perilaku versi lama.
    """
    return (
        os.getenv("REPORT_ACCESS_TOKEN")
        or os.getenv("ADMIN_EXPORT_TOKEN")
        or ""
    ).strip()


def verify_report_access(
    access_key: str | None = None,
    admin_key: str | None = None,
    x_report_token: str | None = None,
) -> None:
    """
    Proteksi endpoint laporan PDF dan CSV. Jika REPORT_ACCESS_TOKEN diisi,
    request wajib menyertakan salah satu dari opsi berikut:

    - query parameter ?access_key=TOKEN
    - query parameter ?admin_key=TOKEN, untuk kompatibilitas versi lama
    - header X-Report-Token: TOKEN
    """
    token = active_report_token()
    if not token:
        return

    supplied = (access_key or admin_key or x_report_token or "").strip()
    if supplied != token:
        raise HTTPException(status_code=403, detail="Akses laporan membutuhkan token yang valid.")


@router.get("/{session_code}/csv")
def download_csv_report(
    session_code: str,
    access_key: str | None = Query(default=None, description="Token akses laporan."),
    admin_key: str | None = Query(default=None, description="Token admin kompatibilitas versi lama."),
    x_report_token: str | None = Header(default=None, alias="X-Report-Token"),
    db: Session = Depends(get_db),
) -> FileResponse:
    verify_report_access(access_key=access_key, admin_key=admin_key, x_report_token=x_report_token)
    session = get_session_or_404(db, session_code)
    metrics = load_metrics(db, session.id)
    if not metrics:
        raise HTTPException(status_code=400, detail="Belum ada data metrik untuk dibuat menjadi CSV.")

    try:
        with REPORT_LOCK:
            path = prepare_report_folder().generate_csv(
                session_id=session.session_code,
                metric_rows=[metric.to_dict() for metric in metrics],
            )
    except (OSError, RuntimeError, ValueError) as exc:
        LOGGER.exception("Pembuatan CSV gagal untuk sesi %s.", session_code)
        raise HTTPException(status_code=500, detail="File CSV gagal dibuat. Periksa log aplikasi.") from exc

    return FileResponse(path, media_type="text/csv", filename=f"metrics_session_{session.session_code}.csv")


@router.get("/{session_code}/pdf")
def download_pdf_report(
    session_code: str,
    access_key: str | None = Query(default=None, description="Token akses laporan."),
    admin_key: str | None = Query(default=None, description="Token admin kompatibilitas versi lama."),
    x_report_token: str | None = Header(default=None, alias="X-Report-Token"),
    db: Session = Depends(get_db),
) -> FileResponse:
    verify_report_access(access_key=access_key, admin_key=admin_key, x_report_token=x_report_token)
    session = get_session_or_404(db, session_code)
    metrics = load_metrics(db, session.id)
    if not metrics:
        raise HTTPException(status_code=400, detail="Belum ada data metrik untuk dibuat menjadi PDF.")

    user = db.query(User).filter_by(id=session.user_id).first()
    session_info = {
        "user_code": user.user_code if user else "-",
        "start_time": session.started_at.strftime("%d-%m-%Y %H:%M:%S") if session.started_at else "-",
        "end_time": session.ended_at.strftime("%d-%m-%Y %H:%M:%S") if session.ended_at else "-",
        "duration": format_duration(session.total_duration_seconds),
        "baseline_ear": f"{session.baseline_ear:.3f}" if session.baseline_ear else "-",
        "final_status": session.final_status,
    }
    try:
        with REPORT_LOCK:
            path = prepare_report_folder().generate_pdf(
                session_id=session.session_code,
                session_info=session_info,
                metric_rows=[metric.to_dict() for metric in metrics],
            )
    except (OSError, RuntimeError, ValueError) as exc:
        LOGGER.exception("Pembuatan PDF gagal untuk sesi %s.", session_code)
        raise HTTPException(status_code=500, detail="File PDF gagal dibuat. Periksa log aplikasi.") from exc

    return FileResponse(path, media_type="application/pdf", filename=f"laporan_monitoring_{session.session_code}.pdf")
