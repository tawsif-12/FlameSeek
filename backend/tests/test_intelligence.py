from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np

from changepoint import detect_monthly_change_points, pelt_mean_shift
from events import reconstruct_events
from geo import AOI, footprint_cell_fractions, location_uncertainty_km
from harmonize import anomaly_category, build_harmonized_series, robust_scale
from quality import classify_observation


T0 = datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc)


def _det(lat, lon, hours=0.0, sensor="viirs_snpp", frp=20.0, conf=90.0, daynight="N"):
    return {"lat": lat, "lon": lon, "acq_datetime": T0 + timedelta(hours=hours), "confidence_pct": conf, "frp": frp, "sensor": sensor, "satellite": "N", "daynight": daynight}


# --- Footprints and AOI ------------------------------------------------------------------


def test_footprint_fractions_sum_to_one_and_modis_spans_more_cells_than_viirs():
    modis = footprint_cell_fractions({"lat": 10.0, "lon": 20.0, "sensor": "modis", "scan_km": 1.8, "track_km": 1.3}, 0.01)
    viirs = footprint_cell_fractions({"lat": 10.0, "lon": 20.0, "sensor": "viirs_snpp", "scan_km": 0.4, "track_km": 0.4}, 0.01)
    assert abs(sum(f for *_, f in modis) - 1) < 1e-9
    assert abs(sum(f for *_, f in viirs) - 1) < 1e-9
    assert len(modis) > len(viirs)


def test_location_uncertainty_grows_with_pixel_size():
    small = location_uncertainty_km({"sensor": "viirs_snpp", "scan_km": 0.39, "track_km": 0.36})
    large = location_uncertainty_km({"sensor": "modis", "scan_km": 2.5, "track_km": 1.5})
    assert large > small


def test_radius_aoi_filters_by_distance():
    aoi = AOI.from_payload({"center": [20.0, 10.0], "radius_km": 10})
    assert aoi.contains(10.05, 20.0)
    assert not aoi.contains(10.2, 20.0)


def test_polygon_aoi_filters_points():
    square = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    aoi = AOI.from_payload({"geometry": square})
    assert aoi.contains(0.5, 0.5)
    assert not aoi.contains(1.5, 0.5)


# --- Events ---------------------------------------------------------------------------------


def test_nearby_detections_across_overpasses_form_one_event():
    rows = [_det(10.0, 20.0, 0), _det(10.003, 20.002, 12, sensor="modis"), _det(10.006, 20.004, 24), _det(12.0, 22.0, 1)]
    events = reconstruct_events(rows, reference_time=T0 + timedelta(hours=25))
    sizes = sorted(e["observation_count"] for e in events)
    assert sizes == [1, 3]
    big = next(e for e in events if e["observation_count"] == 3)
    assert big["sensor_families"] == ["MODIS", "VIIRS"]
    assert big["association_confidence"] is not None
    assert big["behaviour"]["label_type"] == "Inferred Fire Behaviour State"


def test_detections_far_apart_in_time_are_separate_events():
    rows = [_det(10.0, 20.0, 0), _det(10.0, 20.0, 100)]
    assert len(reconstruct_events(rows, reference_time=T0 + timedelta(hours=101))) == 2


def test_new_event_is_onset():
    events = reconstruct_events([_det(10.0, 20.0, 0)], reference_time=T0 + timedelta(hours=3))
    assert events[0]["behaviour"]["state"] == "Onset"


def test_expanding_event_detected():
    rows = [_det(10.0, 20.0, 0), _det(10.001, 20.001, 1), _det(10.0, 20.0, 12)]
    rows += [_det(10.0 + 0.004 * i, 20.0 + 0.004 * j, 36) for i in range(4) for j in range(4)]
    events = reconstruct_events(rows, reference_time=T0 + timedelta(hours=38))
    assert events[0]["behaviour"]["state"] in {"Expanding", "Intensifying"}


# --- Observation quality ----------------------------------------------------------------------


def test_cloudy_day_without_detections_is_unknown_not_no_fire():
    obs = classify_observation(["modis", "viirs_snpp"], [], 90.0)
    assert obs["display"] == "UNKNOWN"
    assert classify_observation(["modis", "viirs_snpp"], [], 10.0)["status"] == "valid_no_fire"


def test_missing_sensors_is_insufficient_observation():
    assert classify_observation([], [], 10.0)["display"] == "INSUFFICIENT OBSERVATION"


def test_substantial_single_sensor_detection_is_ambiguous_when_other_sensor_available():
    rows = [_det(10, 20, 0, sensor="viirs_snpp") for _ in range(4)]
    assert classify_observation(["modis", "viirs_snpp"], rows, 5.0)["display"] == "AMBIGUOUS"
    both = rows + [_det(10, 20, 0, sensor="modis")]
    assert classify_observation(["modis", "viirs_snpp"], both, 5.0)["status"] == "reliable_multi_sensor"


# --- Harmonization and anomalies -------------------------------------------------------------------


def test_robust_scale_resists_outliers():
    med, scale = robust_scale([1, 1, 2, 2, 2, 3, 3, 100])
    assert med == 2
    assert scale < 5


def test_anomaly_categories():
    assert anomaly_category(0.5) == "Normal"
    assert anomaly_category(2.5) == "Above Normal"
    assert anomaly_category(4) == "Unusual"
    assert anomaly_category(6) == "Highly Unusual"


def test_harmonized_series_has_uncertainty_and_observation_fields():
    rows = [_det(10.0, 20.0, 0, sensor="modis"), _det(10.0, 20.0, 1)]
    daily, cal = build_harmonized_series(rows, T0.date(), T0.date() + timedelta(days=1), ["modis", "viirs_snpp"])
    assert daily[0]["harmonized_low"] <= daily[0]["harmonized_activity"] <= daily[0]["harmonized_high"]
    assert daily[0]["observation"]["status"] == "reliable_multi_sensor"
    assert cal["status"] == "prior"


# --- Change points -------------------------------------------------------------------------


def test_pelt_finds_a_level_shift():
    series = [0.0] * 30 + [3.0] * 30
    assert pelt_mean_shift(series, penalty=2.0, min_size=5) == [30]


def test_monthly_change_point_on_step_series():
    monthly = [{"year": 2010 + i // 12, "month": i % 12 + 1, "harmonized_activity": 5 if i < 60 else 60} for i in range(120)]
    result = detect_monthly_change_points(monthly)
    assert result["status"] == "ok"
    assert result["change_points"] and result["change_points"][0]["direction"] == "increase"
    assert "Statistically detected" in result["change_points"][0]["description"]


# --- NLP -----------------------------------------------------------------------------------------
