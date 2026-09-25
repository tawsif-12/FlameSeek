from __future__ import annotations

from datetime import date, datetime, timezone

from harmonize import build_daily_series, filter_low_confidence, snap_to_grid


def test_low_confidence_filter_drops_noise():
    rows = [{"confidence_pct": 29}, {"confidence_pct": 30}, {"confidence_pct": 90}]
    assert len(filter_low_confidence(rows)) == 2


def test_multi_sensor_overlap_counts_one_active_cell():
    hotspots = [
        {"lat": 10.001, "lon": 20.001, "acq_datetime": datetime(2024, 1, 1, tzinfo=timezone.utc), "confidence_pct": 80, "frp": 10, "sensor": "modis"},
        {"lat": 10.002, "lon": 20.002, "acq_datetime": datetime(2024, 1, 1, tzinfo=timezone.utc), "confidence_pct": 90, "frp": 20, "sensor": "viirs_snpp"},
    ]
    daily = build_daily_series(hotspots, date(2024, 1, 1), date(2024, 1, 1))
    assert daily[0]["hotspot_count"] == 2
    assert daily[0]["active_cell_count"] == 1


def test_empty_result_keeps_calendar_dates():
    daily = build_daily_series([], date(2024, 1, 1), date(2024, 1, 3))
    assert len(daily) == 3
    assert all(row["hotspot_count"] == 0 for row in daily)


def test_snap_to_grid_adds_grid_coordinates():
    snapped = snap_to_grid([{"lat": 1.234, "lon": 5.678}])
    assert snapped[0]["grid_lat"] == 1.23
    assert snapped[0]["grid_lon"] == 5.68

