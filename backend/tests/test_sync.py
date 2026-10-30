from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from sync import (
    CountRatio, DetectionModel, allocate_to_grid, calibration_holdout_error, cell_event_counts, cluster_events,
    daily_fre_mj, deming_regression, fit_count_ratio, fit_detection_model, fit_diurnal_shape, fit_frp_calibration,
    persistence_filter, static_source_mask, DiurnalShape,
)

T = datetime(2024, 3, 1, 6, 0, tzinfo=timezone.utc)


def viirs(lat, lon, frp=5.0, t=T):
    return {"lat": lat, "lon": lon, "frp": frp, "sensor": "viirs_snpp", "acq_datetime": t, "scan_km": 0.4, "track_km": 0.4}


def test_one_modis_fire_and_several_viirs_pixels_each_count_one_event():
    v = [viirs(10 + 0.002 * i, 20.0) for i in range(5)]
    m = [{"lat": 10.004, "lon": 20.0, "frp": 25.0, "sensor": "modis", "acq_datetime": T, "scan_km": 1.0, "track_km": 1.0}]
    clusters = cluster_events(v + m)
    assert len(clusters) == 2
    assert sum(cell_event_counts(clusters).values()) == 2


def test_far_apart_detections_and_separate_overpasses_stay_separate():
    rows = [viirs(10, 20), viirs(10.5, 20), viirs(10, 20, t=datetime(2024, 3, 1, 9, tzinfo=timezone.utc))]
    assert len(cluster_events(rows)) == 3


def test_regridding_conserves_frp():
    rows = [viirs(10.0499, 20.0499, 7.0), viirs(10.0, 20.0, 3.0)]
    cells = allocate_to_grid(rows, 0.1)
    assert sum(c["frp"] for c in cells.values()) == pytest.approx(10.0)


def test_deming_recovers_slope_with_noisy_x():
    rng = np.random.default_rng(1)
    truth = rng.uniform(1, 5, 4000)
    x = truth + rng.normal(0, 0.3, truth.size)
    y = 0.5 + 1.2 * truth + rng.normal(0, 0.3, truth.size)
    a, b = deming_regression(x, y)
    assert b == pytest.approx(1.2, abs=0.05)


def test_frp_calibration_holdout_error_small_on_synthetic_pairs():
    rng = np.random.default_rng(2)
    modis = np.exp(rng.uniform(0.5, 4, 600))
    viirs_ = np.exp(0.3 + 0.9 * np.log(modis) + rng.normal(0, 0.1, modis.size))
    cal = fit_frp_calibration(modis[:400], viirs_[:400])
    assert cal.b == pytest.approx(0.9, abs=0.05)
    err = calibration_holdout_error(cal, modis[400:], viirs_[400:])
    assert err["median_abs_pct_error"] < 15 and abs(err["log_bias"]) < 0.05


def test_count_ratio_poisson_mle():
    r = fit_count_ratio([10, 20, 30], [50, 100, 150])
    assert r.ratio == 5.0 and r.scale(4)[0] == 20.0
    with pytest.raises(ValueError):
        fit_count_ratio([0, 0], [3, 4])


def test_detection_model_small_dim_fires_are_missed_more():
    rng = np.random.default_rng(3)
    frp = np.exp(rng.uniform(0, 4, 3000))
    area = np.full(3000, 1.0)
    p = 1 / (1 + np.exp(-(-4 + 1.5 * np.log(frp))))
    det = rng.random(3000) < p
    m = fit_detection_model(frp, area, det)
    assert m.probability(1.0, 1.0) < m.probability(50.0, 1.0)
    assert m.inflate(2, 1.0, 1.0) > 2


def test_diurnal_fit_and_daily_energy_scale_terra_to_aqua():
    truth = DiurnalShape(base=2.0, peak=20.0, h=14.0, sigma=2.5)
    hours = np.arange(0, 24, 1 / 6)
    shape = fit_diurnal_shape(hours, [truth.at(h) for h in hours])
    assert shape.h == pytest.approx(14.0, abs=0.1)
    # Terra at 10:30 and Aqua at 13:30 observing the same day's burn must give the same daily energy.
    terra = daily_fre_mj(truth.at(10.5), 10.5, shape)
    aqua = daily_fre_mj(truth.at(13.5), 13.5, shape)
    assert terra == pytest.approx(aqua, rel=0.02)


def test_persistence_filter_drops_one_or_two_frame_blips():
    glint, fire = (1.0, 1.0), (2.0, 2.0)
    frames = [{glint, fire}, {glint, fire}, {fire}, {fire}]
    assert persistence_filter(frames, 3) == {fire}


def test_static_mask_by_type_and_by_recurrence():
    rows = [{"lat": 1.0, "lon": 1.0, "type": 2, "acq_datetime": T}]
    rows += [{"lat": 5.0, "lon": 5.0, "type": 0, "acq_datetime": datetime(y, 1, 1, tzinfo=timezone.utc)} for y in range(2000, 2010)]
    rows += [{"lat": 9.0, "lon": 9.0, "type": 0, "acq_datetime": T}]
    mask = static_source_mask(rows, years_total=10)
    assert (1.0, 1.0) in mask and (5.0, 5.0) in mask and (9.0, 9.0) not in mask
