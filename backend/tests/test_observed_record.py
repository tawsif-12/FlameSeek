from datetime import date, datetime, timezone

from observed_record import summarize_records


def test_records_use_source_platform_and_utc_dates_without_guessing():
    rows = [
        {"sensor": "modis", "satellite": "Terra", "acq_datetime": "2026-11-01T10:30:00Z"},
        {"sensor": "modis", "acq_datetime": "2026-11-01T13:30:00Z"},
        {"sensor": "viirs_snpp", "acq_datetime": datetime(2026, 11, 1, 12, tzinfo=timezone.utc)},
        {"sensor": "viirs_snpp", "acq_datetime": "2026-11-02T00:15:00+02:00"},
    ]
    daily = [
        {"date": date(2026, 11, 1), "modis_count": 2, "viirs_count": 2, "observation": {"cloud_cover_pct": 15}},
        {"date": date(2026, 11, 2), "modis_count": 0, "viirs_count": 0, "observation": {"cloud_cover_pct": None}},
        {"date": date(2026, 11, 3), "modis_count": 0, "viirs_count": 1, "observation": {"cloud_cover_pct": float("nan")}},
    ]
    result = summarize_records(rows, daily, [{"sensor": "modis"}])
    platforms = {p["id"]: p for p in result["platforms"]}
    assert platforms["terra"]["detections"] == 1
    assert platforms["modis_unknown"]["detections"] == 1
    assert "aqua" not in platforms
    assert platforms["snpp"]["detections"] == 2
    assert platforms["snpp"]["detection_days"] == 1
    assert result["days"] == {"both_families_detected": 1, "one_family_detected": 1, "no_detections_in_retrieved_records": 1}
    assert result["cloud_proxy_days"] == 1
    assert result["failed_download_chunks"] == 1
    assert result["coverage_status"] == "unavailable"
    assert all("sensitivity_per_look" not in p for p in platforms.values())


def test_empty_records_do_not_invent_coverage_or_satellite_values():
    result = summarize_records([], [], [])
    assert result["platforms"] == []
    assert result["total_days"] == 0
    assert result["coverage_status"] == "unavailable"
    assert result["cloud_proxy_days"] == 0
