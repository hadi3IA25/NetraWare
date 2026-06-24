from __future__ import annotations

import csv
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Mapping

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Image as ReportImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


MetricRow = Mapping[str, Any]


class ReportGenerator:
    """
    Generator laporan hasil monitoring.

    Output:
    - CSV untuk data mentah
    - PDF untuk laporan ringkas hasil sesi
    """

    def __init__(self, output_dir: str = "data/reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_csv(
        self,
        session_id: str,
        metric_rows: List[MetricRow],
    ) -> str:
        """
        Membuat file CSV dari data monitoring.
        """
        safe_session_id = self._safe_filename(session_id)
        output_path = os.path.join(
            self.output_dir,
            f"metrics_session_{safe_session_id}.csv",
        )

        if not metric_rows:
            with open(output_path, "w", newline="", encoding="utf-8-sig") as file:
                file.write("Tidak ada data monitoring.\n")
            return output_path

        headers = list(metric_rows[0].keys())

        with open(output_path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader()

            for row in metric_rows:
                writer.writerow(dict(row))

        return output_path

    def generate_pdf(
        self,
        session_id: str,
        session_info: Dict[str, Any],
        metric_rows: List[MetricRow],
    ) -> str:
        """
        Membuat laporan PDF hasil monitoring.
        """
        safe_session_id = self._safe_filename(session_id)
        output_path = os.path.join(
            self.output_dir,
            f"laporan_monitoring_{safe_session_id}.pdf",
        )

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("Laporan Hasil Monitoring Kelelahan Mata", styles["Title"]))
        story.append(Spacer(1, 12))

        story.append(Paragraph("1. Informasi Sesi", styles["Heading2"]))

        info_table_data = [
            ["ID Sesi", str(session_id)],
            ["Tanggal Laporan", datetime.now().strftime("%d-%m-%Y %H:%M:%S")],
            ["Kode Pengguna", str(session_info.get("user_code", "-"))],
            ["Waktu Mulai", str(session_info.get("start_time", "-"))],
            ["Waktu Selesai", str(session_info.get("end_time", "-"))],
            ["Durasi", str(session_info.get("duration", "-"))],
            ["Baseline EAR", str(session_info.get("baseline_ear", "-"))],
            ["Status Akhir", str(session_info.get("final_status", "-"))],
        ]

        info_table = Table(info_table_data, colWidths=[140, 330])
        info_table.setStyle(self._default_table_style())
        story.append(info_table)
        story.append(Spacer(1, 16))

        summary = self._summarize_metrics(metric_rows)

        story.append(Paragraph("2. Ringkasan Hasil Monitoring", styles["Heading2"]))

        summary_table_data = [
            ["Rata-rata EAR", f"{summary['avg_ear']:.3f}"],
            ["Rata-rata Blink Rate", f"{summary['avg_blink_rate']:.2f} kedipan/menit"],
            ["Rata-rata PERCLOS", f"{summary['avg_perclos']:.2%}"],
            ["Rata-rata Skor Kelelahan", f"{summary['avg_fatigue_score']:.2f}"],
            ["Skor Kelelahan Maksimum", f"{summary['max_fatigue_score']:.2f}"],
            ["Jumlah Data", str(summary["total_rows"])],
        ]

        summary_table = Table(summary_table_data, colWidths=[180, 290])
        summary_table.setStyle(self._default_table_style())
        story.append(summary_table)
        story.append(Spacer(1, 16))

        chart_paths = []

        if metric_rows:
            ear_chart = self._build_chart(
                session_id=safe_session_id,
                metric_rows=metric_rows,
                field_name="ear",
                title="Grafik EAR Selama Monitoring",
                ylabel="EAR",
            )
            chart_paths.append(ear_chart)

            score_chart = self._build_chart(
                session_id=safe_session_id,
                metric_rows=metric_rows,
                field_name="fatigue_score",
                title="Grafik Skor Indikasi Kelelahan Mata",
                ylabel="Skor",
            )
            chart_paths.append(score_chart)

        if chart_paths:
            story.append(Paragraph("3. Grafik Monitoring", styles["Heading2"]))

            for chart_path in chart_paths:
                if os.path.exists(chart_path):
                    story.append(ReportImage(chart_path, width=450, height=250))
                    story.append(Spacer(1, 12))

        story.append(Paragraph("4. Interpretasi Skor Indikasi Kelelahan Mata", styles["Heading2"]))
        story.append(
            Paragraph(
                "Skor indikasi kelelahan mata berada pada rentang 0 sampai 100. "
                "Semakin tinggi skor, semakin besar indikasi kelelahan mata yang terdeteksi oleh sistem. "
                "Interpretasi skor pada laporan ini adalah sebagai berikut:",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 8))

        score_table = Table(self._score_interpretation_rows(styles), colWidths=[75, 95, 150, 150])
        score_table.setStyle(self._default_table_style())
        story.append(score_table)
        story.append(Spacer(1, 8))

        story.append(
            Paragraph(
                "Catatan: status PERLU_ISTIRAHAT juga dapat muncul walaupun skor belum mencapai 70 "
                "apabila mata terdeteksi tertutup cukup lama atau durasi penggunaan layar telah mencapai "
                "batas pengingat istirahat.",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 16))

        story.append(Paragraph("5. Catatan Sistem", styles["Heading2"]))
        story.append(
            Paragraph(
                "Sistem ini digunakan untuk mendeteksi indikasi kelelahan mata berdasarkan parameter visual "
                "seperti Eye Aspect Ratio, blink rate, PERCLOS, dan durasi penggunaan layar. "
                "Hasil sistem bersifat indikatif dan tidak digunakan sebagai diagnosis medis.",
                styles["Normal"],
            )
        )

        doc.build(story)

        return output_path

    def _score_interpretation_rows(self, styles: Any | None = None) -> List[List[Any]]:
        """
        Menjelaskan ambang interpretasi skor kelelahan mata pada laporan PDF.

        Ambang ini mengikuti logika status pada FatigueEngine:
        - skor < 40: NORMAL
        - skor >= 40: WASPADA
        - skor >= 70: PERLU_ISTIRAHAT
        """
        rows = [
            ["Rentang Skor", "Status", "Makna", "Saran Tindakan"],
            [
                "0-39,99",
                "NORMAL",
                "Kondisi mata masih berada pada indikasi kelelahan rendah.",
                "Monitoring dapat dilanjutkan. Tetap jaga jarak pandang dan pencahayaan.",
            ],
            [
                "40-69,99",
                "WASPADA",
                "Terdapat tanda awal kelelahan mata.",
                "Alihkan pandangan dari layar, perbanyak kedipan, dan kurangi intensitas fokus sejenak.",
            ],
            [
                "70-100",
                "PERLU_ISTIRAHAT",
                "Indikasi kelelahan mata sudah tinggi.",
                "Hentikan penggunaan layar sementara dan lakukan istirahat mata, misalnya aturan 20-20-20.",
            ],
        ]

        if styles is None:
            return rows

        normal_style = styles["Normal"]
        return [
            row if index == 0 else [row[0], row[1], Paragraph(row[2], normal_style), Paragraph(row[3], normal_style)]
            for index, row in enumerate(rows)
        ]

    def _build_chart(
        self,
        session_id: str,
        metric_rows: List[MetricRow],
        field_name: str,
        title: str,
        ylabel: str,
    ) -> str:
        """
        Membuat grafik sederhana untuk dimasukkan ke laporan PDF.
        """
        elapsed_values = [self._to_float(row.get("elapsed_seconds", 0.0)) for row in metric_rows]
        x_values = (
            elapsed_values
            if any(value > 0 for value in elapsed_values)
            else list(range(1, len(metric_rows) + 1))
        )
        y_values = [
            self._to_float(row.get(field_name, 0.0))
            for row in metric_rows
        ]

        output_path = os.path.join(
            self.output_dir,
            f"{field_name}_{session_id}.png",
        )

        figure = Figure(figsize=(8, 4))
        FigureCanvasAgg(figure)
        axes = figure.add_subplot(1, 1, 1)
        axes.plot(x_values, y_values)
        axes.set_title(title)
        axes.set_xlabel("Durasi Monitoring (detik)" if any(elapsed_values) else "Urutan Data")
        axes.set_ylabel(ylabel)
        figure.tight_layout()
        figure.savefig(output_path, dpi=150)
        figure.clear()

        return output_path

    def _summarize_metrics(self, metric_rows: List[MetricRow]) -> Dict[str, Any]:
        """
        Menghasilkan ringkasan statistik sederhana dari data monitoring.
        """
        if not metric_rows:
            return {
                "avg_ear": 0.0,
                "avg_blink_rate": 0.0,
                "avg_perclos": 0.0,
                "avg_fatigue_score": 0.0,
                "max_fatigue_score": 0.0,
                "total_rows": 0,
            }

        ears = [self._to_float(row.get("ear", 0.0)) for row in metric_rows]
        blink_rates = [
            self._to_float(row.get("blink_rate_per_minute", 0.0))
            for row in metric_rows
            if bool(row.get("blink_rate_ready", True))
        ]
        perclos_values = [
            self._to_float(row.get("perclos", 0.0))
            for row in metric_rows
            if bool(row.get("perclos_ready", True))
        ]
        fatigue_scores = [self._to_float(row.get("fatigue_score", 0.0)) for row in metric_rows]

        return {
            "avg_ear": sum(ears) / len(ears),
            "avg_blink_rate": sum(blink_rates) / len(blink_rates) if blink_rates else 0.0,
            "avg_perclos": sum(perclos_values) / len(perclos_values) if perclos_values else 0.0,
            "avg_fatigue_score": sum(fatigue_scores) / len(fatigue_scores),
            "max_fatigue_score": max(fatigue_scores),
            "total_rows": len(metric_rows),
        }

    def _default_table_style(self) -> TableStyle:
        """
        Style tabel PDF.
        """
        return TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])

    def _safe_filename(self, value: str) -> str:
        """
        Membersihkan nama file agar aman dipakai di sistem operasi.
        """
        value = str(value)
        value = re.sub(r"[^a-zA-Z0-9_-]", "_", value)
        return value[:80]

    def _to_float(self, value: Any) -> float:
        """
        Konversi aman ke float.
        """
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0