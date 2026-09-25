from __future__ import annotations

from datetime import date

from critical_periods import find_critical_periods


def test_contiguous_critical_days_are_grouped():
    daily = [
        {"date": date(2024, 1, 1), "anomaly_score": 0.2, "hotspot_count": 1},
        {"date": date(2024, 1, 2), "anomaly_score": 2.1, "hotspot_count": 10},
        {"date": date(2024, 1, 3), "anomaly_score": 3.1, "hotspot_count": 20},
        {"date": date(2024, 1, 4), "anomaly_score": 0.1, "hotspot_count": 0},
    ]
    periods = find_critical_periods(daily)
    assert len(periods) == 1
    assert periods[0]["duration_days"] == 2
    assert periods[0]["total_hotspots"] == 30

