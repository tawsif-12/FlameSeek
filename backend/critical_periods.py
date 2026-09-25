"""Critical-period extraction from a daily anomaly series."""

from __future__ import annotations

from statistics import mean
from typing import Any

from config import ANOMALY_THRESHOLD


def find_critical_periods(daily_series: list[dict[str, Any]], threshold: float = ANOMALY_THRESHOLD) -> list[dict[str, Any]]:
    periods = []
    active_run: list[dict[str, Any]] = []

    def flush() -> None:
        if not active_run:
            return
        periods.append(
            {
                "start_date": active_run[0]["date"],
                "end_date": active_run[-1]["date"],
                "duration_days": len(active_run),
                "max_anomaly": max(row["anomaly_score"] for row in active_run),
                "avg_hotspot_count": round(mean(row["hotspot_count"] for row in active_run), 2),
                "total_hotspots": sum(row["hotspot_count"] for row in active_run),
            }
        )
        active_run.clear()

    for row in daily_series:
        if row["anomaly_score"] > threshold:
            active_run.append(row)
        else:
            flush()
    flush()

    return sorted(periods, key=lambda row: row["max_anomaly"], reverse=True)

