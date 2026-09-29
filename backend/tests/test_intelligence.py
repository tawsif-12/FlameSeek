from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np

from changepoint import detect_monthly_change_points, pelt_mean_shift
from events import reconstruct_events
from evidence import fuse, subject_from_hotspot
from forecast import BinnedCalibrator, _select_model
from geo import AOI, footprint_cell_fractions, location_uncertainty_km
from harmonize import anomaly_category, build_harmonized_series, estimate_calibration, robust_scale
from nlp import classify_event, extract
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


def test_calibration_recovers_modis_to_viirs_ratio():
    rows_by_day = {}
    for day in range(12):
        d = date(2024, 1, 1) + timedelta(days=day)
        rows = [{"lat": 10 + 0.05 * i, "lon": 20.0, "sensor": "viirs_snpp", "scan_km": 0.375, "track_km": 0.375, "acq_datetime": d} for i in range(4)]
        rows += [{"lat": 10 + 0.05 * i, "lon": 20.0, "sensor": "modis", "scan_km": 0.375, "track_km": 0.375, "acq_datetime": d} for i in range(2)]
        rows_by_day[d] = rows
    cal = estimate_calibration(rows_by_day)
    assert cal["status"] == "calibrated"
    assert abs(cal["viirs_to_modis_factor"] - 0.5) < 0.05


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
    assert cal["status"] == "uncalibrated"


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


def test_nlp_rejects_non_combustion_fire_idioms():
    assert classify_event("Ceasefire talks resume as troops open fire near border")["event_type"] == "NOT_A_FIRE_EVENT"
    assert classify_event("Coach fired after losing streak")["is_fire_related"] is False


def test_nlp_classifies_fire_types():
    assert classify_event("Forest fire spreads near Chittagong hills")["event_type"] == "FOREST_FIRE"
    assert classify_event("Farmers continue stubble burning in Punjab")["event_type"] == "AGRICULTURAL_BURN"
    assert classify_event("Prescribed burn planned in national forest")["event_type"] == "CONTROLLED_BURN"
    assert classify_event("Gas flaring lights up the Niger Delta")["event_type"] == "GAS_FLARE"


def test_nlp_extracts_facts():
    facts = extract("Wildfire near Kalamata burns 1,200 hectares; 300 residents evacuated after lightning strike on September 1", T0, ["Kalamata"])
    assert facts["locations"]["gazetteer_matches"] == ["Kalamata"]
    assert "lightning" in facts["causes"]
    assert facts["affected_area"] and "1,200 hectares" in facts["affected_area"][0]
    assert "2026-09-01" in facts["dates_mentioned"]
    assert facts["impact"]["evacuated"] == 300


# --- Evidence fusion ----------------------------------------------------------------------------


def _fuse(regional=None, official=None, articles=None, heat=None, sufficiency=None):
    subject = subject_from_hotspot(_det(10.0, 20.0, 0, frp=40))
    if sufficiency is not None:
        subject["observation_quality"] = {"observation_sufficiency_score": sufficiency, "recent_cloud_cover_pct": 90}
    regional = regional or {"checks": [], "corroborating_sources": [], "geostationary_or_highres_match": False, "other_platform_match": False}
    official = official or {"checks": [], "matches": [], "has_official_match": False, "controlled_burn_reported": False}
    news = {"articles": articles or []}
    place = {"land_context": {"nearby_heat_sources": heat or []}}
    return fuse(subject, place, regional, official, news)


def test_strong_satellite_alone_is_not_confirmed():
    result = _fuse()
    assert result["final_status"] == "No External Corroboration Yet"
    assert "not a probability" in result["score_note"]


def test_official_report_nearby_allows_confirmed_label():
    official = {"checks": [], "matches": [{"title": "Oak Fire", "distance_km": 3, "incident_type": "WILDFIRE"}], "has_official_match": True, "controlled_burn_reported": False}
    regional = {"checks": [], "corroborating_sources": ["GOES"], "geostationary_or_highres_match": True, "other_platform_match": False}
    assert _fuse(regional=regional, official=official)["final_status"] == "Confirmed Fire"


def test_low_observation_sufficiency_is_reported_as_uncertainty():
    result = _fuse(sufficiency=20)
    assert result["observation_sufficiency"] == 20
    assert any("Observation sufficiency is only 20/100" in u for u in result["uncertainty"])


def test_unavailable_checks_are_not_reported_as_no_match():
    regional = {"checks": [{"name": "GOES", "status": "unavailable"}], "corroborating_sources": [], "geostationary_or_highres_match": False, "other_platform_match": False}
    uncertainty = _fuse(regional=regional)["uncertainty"]
    assert any("Could not be checked" in u for u in uncertainty)
    assert not any("No independent satellite detection matched" in u for u in uncertainty)


def test_known_gas_flare_nearby_marks_non_fire_source():
    heat = [{"type": "gas_flare", "name": "Flare stack", "distance_km": 0.4}]
    assert _fuse(heat=heat)["final_status"] == "Likely Non-Fire Thermal Source"


# --- Forecast model selection --------------------------------------------------------------------


def _m(brier, csi):
    return {"brier": brier, "critical_success_index": csi}


def test_ml_used_only_when_it_beats_baselines():
    temporal = {"status": "ok", "models": {"persistence": _m(0.10, 0.3), "seasonal": _m(0.12, 0.2), "wind_only": _m(0.11, 0.25), "lightgbm": _m(0.08, 0.35)}}
    spatial = {"status": "ok", "models": {"persistence": _m(0.10, 0.3), "seasonal": _m(0.12, 0.2), "wind_only": _m(0.11, 0.25), "lightgbm": _m(0.09, 0.32)}}
    assert _select_model(temporal, spatial)[0] == "lightgbm"
    spatial["models"]["lightgbm"] = _m(0.2, 0.1)
    chosen, why = _select_model(temporal, spatial)
    assert chosen == "persistence"
    assert "did not beat" in why


def test_binned_calibrator_maps_scores_to_frequencies():
    score = np.linspace(0, 1, 1000)
    y = (score > 0.5).astype(int)
    cal = BinnedCalibrator().fit(score, y, np.ones_like(score))
    assert cal.predict(np.array([0.05]))[0] < 0.1
    assert cal.predict(np.array([0.95]))[0] > 0.9
