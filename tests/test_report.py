from pathlib import Path

from app.core.report_generator import ReportGenerator


def sample_rows():
    return [
        {
            "elapsed_seconds": 1.0,
            "ear": 0.30,
            "blink_rate_per_minute": 0.0,
            "blink_rate_ready": False,
            "perclos": 0.0,
            "perclos_ready": False,
            "fatigue_score": 0.0,
        },
        {
            "elapsed_seconds": 16.0,
            "ear": 0.28,
            "blink_rate_per_minute": 12.0,
            "blink_rate_ready": True,
            "perclos": 0.10,
            "perclos_ready": True,
            "fatigue_score": 20.0,
        },
    ]


def test_report_summary_excludes_warmup_placeholders(tmp_path: Path):
    generator = ReportGenerator(str(tmp_path))
    summary = generator._summarize_metrics(sample_rows())

    assert summary["avg_blink_rate"] == 12.0
    assert summary["avg_perclos"] == 0.10


def test_csv_and_pdf_are_created(tmp_path: Path):
    generator = ReportGenerator(str(tmp_path))
    rows = sample_rows()

    csv_path = Path(generator.generate_csv("SESSION/01", rows))
    pdf_path = Path(
        generator.generate_pdf(
            "SESSION/01",
            {
                "user_code": "P001",
                "start_time": "16-06-2026 10:00:00",
                "end_time": "16-06-2026 10:01:00",
                "duration": "1 menit",
                "baseline_ear": "0.300",
                "final_status": "NORMAL",
            },
            rows,
        )
    )

    assert csv_path.is_file() and csv_path.stat().st_size > 50
    assert pdf_path.is_file() and pdf_path.stat().st_size > 1_000


def test_score_interpretation_rows_are_available_for_pdf_users(tmp_path: Path):
    generator = ReportGenerator(str(tmp_path))
    rows = generator._score_interpretation_rows()

    assert rows[0] == ["Rentang Skor", "Status", "Makna", "Saran Tindakan"]
    assert rows[1][0] == "0-39,99"
    assert rows[1][1] == "NORMAL"
    assert rows[2][0] == "40-69,99"
    assert rows[2][1] == "WASPADA"
    assert rows[3][0] == "70-100"
    assert rows[3][1] == "PERLU_ISTIRAHAT"
