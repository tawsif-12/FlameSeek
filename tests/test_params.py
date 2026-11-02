"""Versioned params files and the sync-window (Deming) calibration."""
import numpy as np
import pandas as pd

from pipeline import calibration as cal
from pipeline import params


def test_params_versions_and_status(cfg, tmp_path):
    c = {**cfg, "params": {"dir": str(tmp_path / "params")}}
    base = {"source_window": {"window": "w"}, "era": {"aqua_drifted": True}, "sample_size": 10,
            "fit_method": "x", "values": {"a": 1.0}, "intervals": None}
    p1 = params.write("calibration", {**base, "status": "provisional"}, c)
    p2 = params.write("calibration", {**base, "status": "validated-sync-window"}, c)
    assert p1.name == "calibration_v1.json" and p2.name == "calibration_v2.json"
    assert params.load("calibration", cfg=c)["version"] == 2
    assert params.load("calibration", statuses=["provisional"], cfg=c)["version"] == 1
    params.set_status("calibration", 1, "drift-affected", "superseded", c)
    d = params.load("calibration", 1, cfg=c)
    assert d["status"] == "drift-affected" and d["status_history"][0]["from"] == "provisional"


def test_deming_recovers_slope_with_errors_in_both(cfg):
    rng = np.random.default_rng(3)
    true = rng.uniform(0.5, 3, 400)                        # log10 FRP
    x = true + rng.normal(0, 0.15, 400)                    # MODIS, with error
    y = -0.2 + 1.1 * true + rng.normal(0, 0.15, 400)       # VIIRS, with error
    a, b = cal.deming(x, y, delta=1.1 ** 2)                # stated error ratio
    b_ols = np.polyfit(x, y, 1)[0]
    assert abs(b - 1.1) < 0.05
    assert abs(b_ols - 1.1) > abs(b - 1.1)                 # OLS is attenuated by the x errors


def test_fit_sync_filters(cfg):
    rng = np.random.default_rng(4)
    n = 120
    f = 10 ** rng.uniform(0.5, 3, n)
    pairs = pd.DataFrame({"frp_sum_mw_modis": f, "frp_sum_mw_viirs": f * 0.8,
                          "dt_min": rng.uniform(-40, 40, n)})
    r = cal.fit_sync(pairs, cfg)
    kept = pairs[(pairs["dt_min"].abs() <= 15) & (pairs["frp_sum_mw_modis"] >= 10) & (pairs["frp_sum_mw_viirs"] >= 10)]
    assert r["n"] == len(kept)
    assert r["fitted"] and abs(r["b"] - 1.0) < 1e-6
    assert r["b_bounds_ols"][0] <= r["b"] + 1e-9 <= r["b_bounds_ols"][1] + 2e-9
