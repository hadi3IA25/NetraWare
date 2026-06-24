from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


def _mean(values: Iterable[float]) -> float:
    numbers = [float(value) for value in values]
    return sum(numbers) / len(numbers) if numbers else 0.0


def calculate_metric_summary(metrics: list[Any]) -> dict[str, Any]:
    """Calculate one consistent summary for reports and session completion.

    Blink-rate and PERCLOS samples collected during their warm-up periods are
    excluded from their means. Treating warm-up placeholders as real zeroes
    would bias the scientific output downward.
    """

    if not metrics:
        return {
            "total_metric_records": 0,
            "total_duration_seconds": 0.0,
            "total_blink_count": 0,
            "avg_ear": 0.0,
            "avg_blink_rate": 0.0,
            "avg_perclos": 0.0,
            "avg_fatigue_score": 0.0,
            "max_fatigue_score": 0.0,
            "status_distribution": {},
            "final_status": "TANPA_DATA",
        }

    ready_blink_rates = [
        item.blink_rate_per_minute for item in metrics if item.blink_rate_ready
    ]
    ready_perclos = [item.perclos for item in metrics if item.perclos_ready]

    return {
        "total_metric_records": len(metrics),
        "total_duration_seconds": float(metrics[-1].screen_duration_seconds),
        "total_blink_count": int(metrics[-1].blink_count_total),
        "avg_ear": _mean(item.ear_avg for item in metrics),
        "avg_blink_rate": _mean(ready_blink_rates),
        "avg_perclos": _mean(ready_perclos),
        "avg_fatigue_score": _mean(item.fatigue_score for item in metrics),
        "max_fatigue_score": max(float(item.fatigue_score) for item in metrics),
        "status_distribution": dict(Counter(item.status for item in metrics)),
        "final_status": metrics[-1].status,
    }
