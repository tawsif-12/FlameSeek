"""Anti-chaining caps: no event wider than 25 km or longer than 14 days."""
import numpy as np
import pandas as pd

from conftest import PROCESSED, real_outputs
from pipeline import events, footprints


def test_extent_cap_splits_chain(cfg, make_detections):
    # 120 VIIRS pixels in a line, 0.33 km apart: one linked chain about 40 km long.
    rows = [{"latitude": 23.8 + k * 0.003, "longitude": 90.4} for k in range(120)]
    ev = events.run(footprints.run(make_detections(rows), cfg), cfg)
    assert ev["stats"]["n_raw_components"] == 1
    assert ev["stats"]["n_events_split"] == 1
    assert len(ev["events"]) >= 2
    assert (ev["events"]["extent_km"] <= cfg["events"]["cap_extent_km"]).all()
    assert ev["detections"]["fire_id"].notna().all()


def test_duration_cap_splits_long_fire(cfg, make_detections):
    # The same small fire seen every day for 20 days.
    days = pd.date_range("2026-10-01", periods=20, freq="D")
    rows = [{"acq_date": d.strftime("%Y-%m-%d")} for d in days]
    ev = events.run(footprints.run(make_detections(rows), cfg), cfg)
    assert ev["stats"]["n_raw_components"] == 1
    assert ev["stats"]["n_split_by_duration"] == 1
    assert (ev["events"]["n_days"] <= cfg["events"]["cap_duration_days"]).all()
    assert len(ev["events"]) == 2


def test_halfdiagonal_link_not_fixed_500m(cfg, make_detections):
    # Two MODIS edge pixels 1.5 km apart: beyond 500 m but within the half-diagonal sum.
    m = {"instrument": "MODIS", "satellite": "Aqua", "confidence": "70", "scan": 4.0, "track": 1.8,
         "brightness": 330.0, "bright_t31": 290.0}
    rows = [{**m}, {**m, "latitude": 23.8135}]
    ev = events.run(footprints.run(make_detections(rows), cfg), cfg)
    assert len(ev["events"]) == 1


@real_outputs
def test_real_events_respect_caps(cfg):
    ev = pd.read_csv(PROCESSED / "fire_events.csv")
    assert (ev["extent_km"] <= cfg["events"]["cap_extent_km"] + 1e-9).all()
    assert (ev["n_days"] <= cfg["events"]["cap_duration_days"]).all()
    span = (pd.to_datetime(ev["end_time"]) - pd.to_datetime(ev["start_time"])).dt.days
    assert (span < cfg["events"]["cap_duration_days"] + 1).all()
    assert np.isin(ev["sensor_flag"], ["MODIS_only", "VIIRS_only", "both"]).all()
