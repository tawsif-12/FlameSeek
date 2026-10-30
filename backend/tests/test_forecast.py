from __future__ import annotations

import numpy as np
import pytest

from forecast import (
    brier_skill_score, build_features, climatology, evaluate, fit_forecaster, grid_neighbors, leave_one_year_out_climatology,
    log_z_score, mean_pairwise_correlation, p_aoi_correlated, p_aoi_independent, predict_cells, reliability_table,
)


def synthetic(years=14, rows=3, cols=3, seed=0):
    """Fire seasons around week 16 whose intensity varies by year; a dry-year factor persists within the season."""
    rng = np.random.default_rng(seed)
    C = rows * cols
    weeks = np.arange(52)
    season = np.exp(-((weeks - 16) ** 2) / (2 * 3.0**2))
    counts = np.zeros((years, 52, C))
    for y in range(years):
        dry = rng.normal(0, 0.8)
        for c in range(C):
            lam = 1.5 * season * np.exp(dry + rng.normal(0, 0.2))
            counts[y, :, c] = rng.poisson(lam)
    return counts


def test_climatology_is_beta_smoothed_not_extreme():
    counts = np.zeros((25, 52, 1))
    counts[0, 10, 0] = 3
    p = climatology(counts, alpha=0.5, beta=0.5)
    assert 0 < p[10, 0] < 0.1
    counts[:, 10, 0] = 1
    assert climatology(counts)[10, 0] < 1.0


def test_climatology_reports_share_of_years():
    counts = np.zeros((25, 52, 1))
    counts[:19, 15, 0] = 1
    counts[:19, 14, 0] = 1
    counts[:19, 16, 0] = 1
    assert climatology(counts, alpha=0, beta=0)[15, 0] == pytest.approx(19 / 25)


def test_log_z_handles_skewed_counts():
    assert log_z_score(np.array([100.0]), np.array([np.log1p(5)]), np.array([0.5]))[0] > 3


def test_features_do_not_see_the_future():
    counts = synthetic()
    years = list(range(10))
    p = leave_one_year_out_climatology(counts, years)
    X1, _ = build_features(counts, 11, 20, 3, p)
    altered = counts.copy()
    altered[11, 21:] = 99  # everything after the origin week
    altered[12:] = 99
    X2, _ = build_features(altered, 11, 20, 3, p)
    assert np.allclose(X1, X2)


def test_p_aoi_independent_and_correlated():
    p = np.full(10, 0.2)
    assert p_aoi_independent(p) == pytest.approx(1 - 0.8**10)
    assert p_aoi_correlated(p, rho=0.0, n_sims=40000) == pytest.approx(p_aoi_independent(p), abs=0.01)
    assert p_aoi_correlated(p, rho=0.9) < p_aoi_independent(p)


def test_pairwise_correlation_detects_shared_signal():
    rng = np.random.default_rng(0)
    shared = rng.random((500, 1)) < 0.3
    assert mean_pairwise_correlation(np.repeat(shared, 4, axis=1)) > 0.99
    assert abs(mean_pairwise_correlation(rng.random((500, 4)) < 0.3)) < 0.1


def test_forecaster_beats_climatology_and_is_calibrated():
    counts = synthetic(years=16)
    nb = grid_neighbors(3, 3)
    train, calib, test = list(range(11)), 11, [12, 13, 14, 15]
    fc = fit_forecaster(counts, train, calib, leads=[1, 4], n_models=3, neighbors=nb, stride=1, n_estimators=60)
    ev = evaluate(fc, counts, test, train, neighbors=nb, stride=1)
    assert ev[1]["bss"] > 0  # persistence of a dry year is visible one week ahead
    for row in ev[1]["reliability"]:
        if row["n"] >= 40:
            assert abs(row["mean_predicted"] - row["observed_frequency"]) < 0.2

    out = predict_cells(fc, counts, 15, 12, neighbors=nb, p_by_year={15: climatology(counts, train, neighbors=nb)})
    r = out[1]
    assert np.all(r["p_low"] <= r["p"] + 1e-9) and np.all(r["p"] <= r["p_high"] + 1e-9)
    assert r["ratio_to_normal"].shape == (9,)


def test_reliability_table_bins():
    t = reliability_table(np.array([0.05, 0.05, 0.9, 0.9]), np.array([0, 0, 1, 1]))
    assert [r["n"] for r in t] == [2, 2]


def test_shap_contributions_sum_with_offset_to_logit():
    from forecast import explain, sigmoid
    counts = synthetic(years=12)
    fc = fit_forecaster(counts, list(range(9)), 9, leads=[1], n_models=2, stride=2, n_estimators=30)
    X, _ = build_features(counts, 10, 12, 1, {10: climatology(counts, list(range(9)))})
    rows = explain(fc.models[1], X)
    assert len(rows) == X.shape[0] and "z_recent_2w" in rows[0]
