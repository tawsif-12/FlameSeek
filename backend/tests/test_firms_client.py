from __future__ import annotations

from datetime import date

import pytest
import firms_client

from firms_client import FirmsAPIError, _normalize_confidence, _require_firms_key, _source_for_sensor, firms_key_configured


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


def test_placeholder_map_key_fails_locally_with_setup_instructions(monkeypatch):
    monkeypatch.setattr(firms_client, "FIRMS_MAP_KEY", "DEMO_KEY")
    assert not firms_key_configured()
    with pytest.raises(FirmsAPIError) as error:
        _require_firms_key()
    assert error.value.status_code == 503
    assert "backend/.env" in error.value.message
