from __future__ import annotations

from datetime import datetime, timezone

from verification import verify_hotspot


def _row(**overrides):
    row = {
        "lat": 23.7,
        "lon": 90.4,
        "acq_datetime": datetime(2026, 9, 27, 6, 30, tzinfo=timezone.utc),
        "confidence_pct": 90.0,
        "frp": 18.5,
        "sensor": "viirs_snpp",
        "satellite": "N",
        "daynight": "N",
    }
    row.update(overrides)
    return row


def test_high_confidence_night_viirs_hotspot_is_confirmed():
    verified = verify_hotspot(_row())

    assert verified["verification"]["verdict"] == "confirmed_fire"
    assert verified["verification"]["score"] >= 6
    assert "worldview.earthdata.nasa.gov" in verified["verification"]["imagery_url"]
    assert "gdeltproject.org" in verified["verification"]["news_url"]


def test_low_signal_day_hotspot_needs_false_positive_review():
    verified = verify_hotspot(_row(confidence_pct=25.0, frp=1.2, sensor="modis", daynight="D"))

    assert verified["verification"]["verdict"] == "likely_false_positive"
    assert verified["verification"]["warnings"]
