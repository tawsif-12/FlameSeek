"""Phase 2 rules: per-overpass FRP only, no Terra, non-detections kept, windows respected."""
import numpy as np
import pandas as pd
import pytest

from conftest import INTERIM, real_outputs
from pipeline import calibration as cal
from pipeline import events, footprints
from pipeline.events import window_by_platform

T0 = pd.Timestamp("2026-10-30 10:00", tz="UTC")


def ovrow(fid, plat, minutes, frp, dn="D", cell="r1000c2000"):
    sensor = "MODIS" if plat in ("Terra", "Aqua") else "VIIRS"
    return {"fire_id": fid, "sensor": sensor, "platform": plat, "acq_datetime_utc": T0 + pd.Timedelta(minutes=minutes),
            "frp_sum_mw": frp, "n_detections": 1, "daynight": dn, "cell_id": cell}


def test_pairs_use_single_overpass_frp(cfg, make_detections):
    # One fire: two Aqua pixels at one overpass (sum 30) plus a second Aqua overpass
    # 99 min later, and an S-NPP overpass 40 min after the first Aqua overpass.
    rows = [dict(instrument="MODIS", satellite="Aqua", confidence="70", scan=1.0, track=1.0, brightness=330.0,
                 bright_t31=290.0, acq_time=1000, frp=12.0),
            dict(instrument="MODIS", satellite="Aqua", confidence="70", scan=1.0, track=1.0, brightness=330.0,
                 bright_t31=290.0, acq_time=1000, frp=18.0, latitude=23.805),
            dict(instrument="MODIS", satellite="Aqua", confidence="70", scan=1.0, track=1.0, brightness=330.0,
                 bright_t31=290.0, acq_time=1139, frp=50.0),
            dict(satellite="N", acq_time=1040, frp=25.0)]
    ev = events.run(footprints.run(make_detections(rows), cfg), cfg)
    ov = cal.enrich_overpasses(ev["overpasses"], ev["detections"].drop(columns="geometry"), 0.1)
    pairs = cal.build_pairs(ov, cfg)
    # The 11:39 Aqua overpass is 59 min after S-NPP: inside a 60-min window, so 2 pairs.
    assert set(pairs["frp_sum_mw_modis"]) <= {30.0, 50.0}
    assert 80.0 not in set(pairs["frp_sum_mw_modis"])  # never 30 + 50
    # Each pair value equals the detections' sum at exactly that platform + time.
    d = ev["detections"]
    for _, p in pairs.iterrows():
        s = d[(d["platform"] == "Aqua") & (d["acq_datetime_utc"] == p["acq_datetime_utc_modis"])]["frp_mw"].sum()
        assert np.isclose(s, p["frp_sum_mw_modis"])


def test_no_terra_in_pairs(cfg):
    ov = pd.DataFrame([ovrow("FE1", "Terra", 0, 20.0), ovrow("FE1", "S-NPP", 5, 15.0),
                       ovrow("FE2", "Aqua", 0, 20.0), ovrow("FE2", "NOAA-20", 10, 15.0)])
    pairs = cal.build_pairs(ov, cfg)
    assert "Terra" not in set(pairs["platform_modis"])
    assert list(pairs["fire_id"]) == ["FE2"]
    bad = {**cfg, "events": {**cfg["events"], "matched_pair_modis": ["Aqua", "Terra"]}}
    with pytest.raises(ValueError):
        cal.build_pairs(ov, bad)
    with pytest.raises(ValueError):
        events.matched_pairs(ov, bad)


def test_detection_sample_keeps_nondetections(cfg):
    ov = pd.DataFrame([
        ovrow("FE1", "S-NPP", 30, 40.0), ovrow("FE1", "Aqua", 3, 25.0),   # Aqua saw it -> 1
        ovrow("FE2", "S-NPP", 40, 2.0),                                   # Aqua missed it -> 0
        ovrow("FE3", "NOAA-20", 150, 9.0),                                # too far from Aqua -> excluded
    ])
    opp = pd.DataFrame({"cell_id": ["r1000c2000"], "platform": ["Aqua"], "overpass_time_utc": [T0],
                        "pixel_area_km2": [1.3], "scan_angle_deg": [20.0]})
    s = cal.detection_sample(ov, opp, cfg).set_index("fire_id")
    assert s.loc["FE1", "detected"] == 1
    assert s.loc["FE2", "detected"] == 0
    assert "FE3" not in s.index
    assert (s["a_modis_km2"] == 1.3).all()


def test_pair_dt_within_window(cfg):
    win = window_by_platform(cfg)
    assert max(win.values()) <= cfg["events"]["matched_pair_window_max_min"] <= 60
    ov = pd.DataFrame([ovrow("FE1", "Aqua", 0, 10.0)] +
                      [ovrow("FE1", "S-NPP", m, 5.0) for m in (-win["S-NPP"] - 1, -win["S-NPP"], 70)] +
                      [ovrow("FE2", "Aqua", 0, 10.0), ovrow("FE2", "NOAA-20", win["NOAA-20"] + 0.5, 5.0)])
    pairs = cal.build_pairs(ov, cfg)
    assert len(pairs) == 1 and pairs["dt_min"].iloc[0] == -win["S-NPP"]
    assert (pairs["dt_min"].abs() <= pairs["window_min"]).all()


@real_outputs
def test_real_calibration_inputs(cfg):
    path = INTERIM / "calibration_pairs.csv"
    if not path.exists():
        pytest.skip("run `python run_phase2.py` first")
    p = pd.read_csv(path)
    win = window_by_platform(cfg)
    assert "Terra" not in set(p["platform_modis"])
    assert (p["dt_min"].abs() <= p["platform_viirs"].map(win)).all()
    # Calibration FRP equals one row of the event-overpass table (one platform, one time).
    ov = pd.read_csv(INTERIM / "event_overpasses.csv")
    key = ov.set_index(["fire_id", "platform", "acq_datetime_utc"])["frp_sum_mw"]
    got = key.reindex(pd.MultiIndex.from_arrays([p["fire_id"], p["platform_modis"], p["acq_datetime_utc_modis"]]))
    assert np.allclose(got.to_numpy(), p["frp_sum_mw_modis"].to_numpy())
    s = pd.read_csv(INTERIM / "detection_curve_sample.csv")
    assert set(s["detected"].unique()) == {0, 1}
