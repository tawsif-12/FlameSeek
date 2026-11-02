"""D68 gate, D69 fallback opportunities, archived TLE selection and the Space-Track script."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import observed_opportunities as oo
from pipeline import overpasses, sync_gate, tle_archive
from pipeline.config import ROOT, load_settings


def _det(lst_h, n=50):
    return pd.DataFrame(dict(platform=["Aqua"] * n, daynight=["D"] * n, lst_h=[lst_h] * n))


def _pairs(n, dt_min=5.0, frp=50.0, viirs="S-NPP"):
    t = pd.Timestamp("2016-10-30 08:00", tz="UTC")
    rows = []
    for i in range(n):
        base = dict(fire_id=f"f{i}", n_detections=1, daynight="D")
        rows.append({**base, "platform": "Aqua", "acq_datetime_utc": t, "frp_sum_mw": frp})
        rows.append({**base, "platform": viirs, "acq_datetime_utc": t + pd.Timedelta(minutes=dt_min), "frp_sum_mw": frp})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def cfg16():
    return load_settings(window="sync_2016")


def test_gate_passes_only_with_both_parts(cfg16):
    ok = sync_gate.evaluate(_det(13.6), _pairs(100), cfg16)
    assert ok["a_no_drift"]["pass"] and ok["b_sample"]["pass"] and ok["synchronized"]
    drifted = sync_gate.evaluate(_det(15.75), _pairs(300), cfg16)
    assert not drifted["a_no_drift"]["pass"] and not drifted["synchronized"]
    small = sync_gate.evaluate(_det(13.5), _pairs(99), cfg16)
    assert not small["b_sample"]["pass"] and not small["synchronized"]


def test_gate_sample_uses_15_min_truncation_and_snpp_only(cfg16):
    assert sync_gate.evaluate(_det(13.5), _pairs(150, dt_min=16), cfg16)["b_sample"]["n_pairs_filtered"] == 0
    assert sync_gate.evaluate(_det(13.5), _pairs(150, frp=5), cfg16)["b_sample"]["n_pairs_filtered"] == 0
    assert sync_gate.evaluate(_det(13.5), _pairs(150, viirs="NOAA-20"), cfg16)["b_sample"]["n_pairs_filtered"] == 0


def test_gate_thresholds_are_the_stated_ones(cfg16):
    g = cfg16["sync_gate"]
    assert (g["aqua_nominal_lst_h"], g["aqua_lst_tolerance_min"], g["min_pairs"]) == (13.5, 30, 100)
    assert cfg16["calibration"]["sync_max_dt_min"] == 15


@pytest.mark.parametrize("sensor,alt,nadir,eta", [("MODIS", 705, 1.0, 35.0), ("VIIRS", 829, 0.375, 50.0)])
def test_pixel_size_inversion_brackets_true_distance(sensor, alt, nadir, eta):
    scan, track = overpasses.pixel_size_km(np.array([eta]), alt, nadir, sensor)
    size = (scan if sensor == "MODIS" else track)[0]
    lo, hi = oo.distance_interval(np.array([size]), 0.01, sensor, alt, nadir)
    truth = oo.ground_distance_km(eta, alt)
    assert lo[0] <= truth <= hi[0]


def test_ground_distance_inverts_scan_angle():
    theta = 600 / overpasses.R_KM
    eta = overpasses.scan_angle_deg(theta, 705)
    assert abs(oo.ground_distance_km(eta, 705) - 600) < 1e-6


def test_passes_split_on_gap_and_length():
    t = pd.to_datetime(["2016-10-30 08:00", "2016-10-30 08:03", "2016-10-30 08:08", "2016-10-30 09:40"], utc=True)
    ids = oo.split_passes(pd.DataFrame({"acq_datetime_utc": t}), gap_min=20, max_min=6)
    assert ids.tolist() == [0, 0, 1, 2]


def test_lower_bound_label_is_stated():
    assert oo.LABEL == "detection-conditioned opportunities – lower bound on O_s"


AQUA_L1 = "1 27424U 02022A   16305.50000000  .00000100  00000-0  32000-4 0  9990"
AQUA_L2 = "2 27424  98.2000 245.0000 0001000  90.0000 270.0000 14.57100000 77770"


def test_tle_epoch_and_selection(tmp_path, monkeypatch, cfg16):
    assert tle_archive.tle_epoch(AQUA_L1) == pd.Timestamp("2016-10-31 12:00", tz="UTC")
    folder = tmp_path / "data/raw/tle/2016"
    folder.mkdir(parents=True)
    (folder / "x.3le").write_text(f"0 AQUA\n{AQUA_L1}\n{AQUA_L2}\n")
    monkeypatch.setattr(tle_archive, "ROOT", tmp_path)
    sel = tle_archive.select(cfg16)
    assert "Aqua" in sel["tles"] and not sel["complete"]
    assert set(sel["missing"]) == {"Terra", "S-NPP"}


def test_tle_far_from_window_is_rejected(tmp_path, monkeypatch, cfg16):
    far = AQUA_L1.replace("16305.50000000", "16200.50000000")
    folder = tmp_path / "data/raw/tle/2016"
    folder.mkdir(parents=True)
    (folder / "x.tle").write_text(f"{far}\n{AQUA_L2}\n")
    monkeypatch.setattr(tle_archive, "ROOT", tmp_path)
    assert "Aqua" in tle_archive.select(cfg16)["missing"]


def test_fetch_script_needs_env_credentials_and_writes_nothing(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SPACETRACK_")}
    r = subprocess.run([sys.executable, str(ROOT / "tools/fetch_spacetrack_tle.py"), "--start", "2016-10-26",
                        "--end", "2016-11-06", "--out-dir", str(tmp_path)], env=env, capture_output=True, text=True)
    assert r.returncode == 2 and "SPACETRACK_USER" in r.stderr
    assert not any(tmp_path.iterdir())


def test_fetch_script_has_no_credential_output():
    src = (ROOT / "tools/fetch_spacetrack_tle.py").read_text(encoding="utf-8")
    for bad in ("print(user", "print(password", "print(body", "{password}", "{user}"):
        assert bad not in src
