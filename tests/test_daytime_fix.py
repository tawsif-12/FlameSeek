"""D73: optional daytime fix in himawari.contextual; default behaviour unchanged."""
import numpy as np

from pipeline import himawari as hw
from pipeline.config import load_settings


def _scene(sza):
    n = 41
    frame = {"b07": np.full((n, n), 300.0, np.float32), "b14": np.full((n, n), 300.0, np.float32),
             "b15": np.full((n, n), 293.0, np.float32), "radiance": np.full((n, n), 1.0, np.float32),
             "sza_deg": np.full((n, n), sza, np.float32)}
    geom = {"vza_deg": np.full((n, n), 20.0), "land": np.ones((n, n), bool), "pixel_area_km2": np.full((n, n), 4.0)}
    return frame, geom


def _settings():
    return load_settings()["himawari"]


def test_split_window_gt5_not_used_by_day_with_fix_but_used_at_night():
    s, const = _settings(), {"sigma_over_a": 1.0}
    frame, geom = _scene(30.0)  # B14-B15 = 7 K, clear by reflectance
    fix = {"reflectance": np.full(frame["b07"].shape, 0.2, np.float32), "reflectance_max": 0.35,
           "sza_max_deg": 80.0, "delta_cap_k": None}
    assert hw.contextual(frame, geom, s, const)["cloud"].all()
    assert not hw.contextual(frame, geom, s, const, day_fix=fix)["cloud"].any()
    night, g = _scene(120.0)
    a = hw.contextual(night, g, s, const)["cloud"]
    b = hw.contextual(night, g, s, const, day_fix={**fix, "reflectance": np.full(night["b07"].shape, np.nan)})["cloud"]
    assert (a == b).all()


def test_bright_reflectance_is_cloud_and_missing_reflectance_is_unknown():
    s, const = _settings(), {"sigma_over_a": 1.0}
    frame, geom = _scene(30.0)
    r = np.full(frame["b07"].shape, 0.6, np.float32)
    r[0, 0] = np.nan
    res = hw.contextual(frame, geom, s, const, day_fix={"reflectance": r, "reflectance_max": 0.35,
                                                        "sza_max_deg": 80.0, "delta_cap_k": None})
    assert res["status"][5, 5] == 2 and res["status"][0, 0] == 4


def test_delta_cap_only_lowers_the_daytime_bar():
    s, const = _settings(), {"sigma_over_a": 1.0}
    frame, geom = _scene(30.0)
    rng = np.random.default_rng(0)
    frame["b07"] = (300 + rng.normal(0, 1, frame["b07"].shape)).astype(np.float32)
    frame["b14"] = (285 + rng.normal(0, 4, frame["b07"].shape)).astype(np.float32)  # noisy delta background
    frame["b15"] = frame["b14"] - 2
    frame["b07"][20, 20], frame["b14"][20, 20] = 325.0, 290.0
    base = {"reflectance": np.full(frame["b07"].shape, 0.2, np.float32), "reflectance_max": 0.35, "sza_max_deg": 80.0}
    uncapped = hw.contextual(frame, geom, s, const, day_fix={**base, "delta_cap_k": None})["fire"]
    capped = hw.contextual(frame, geom, s, const, day_fix={**base, "delta_cap_k": 6})["fire"]
    assert capped.sum() >= uncapped.sum() and capped[20, 20]
