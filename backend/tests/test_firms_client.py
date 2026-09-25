from __future__ import annotations

from datetime import date

from firms_client import _normalize_confidence, _source_for_sensor


def test_viirs_confidence_mapping():
    assert _normalize_confidence("l", "viirs_snpp") == 25.0
    assert _normalize_confidence("n", "viirs_noaa20") == 60.0
    assert _normalize_confidence("h", "viirs_noaa21") == 90.0


def test_modis_confidence_is_numeric():
    assert _normalize_confidence("72", "modis") == 72.0


def test_historical_dates_use_science_processing_sources():
    assert _source_for_sensor("modis", date(2024, 8, 1)) == "MODIS_SP"
    assert _source_for_sensor("viirs_snpp", date(2024, 8, 1)) == "VIIRS_SNPP_SP"


def test_recent_dates_use_nrt_sources():
    assert _source_for_sensor("modis", date(2026, 8, 1)) == "MODIS_NRT"
