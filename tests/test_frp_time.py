"""FRP is summed only within one overpass, never across acquisition times."""
import numpy as np
import pandas as pd

from conftest import INTERIM, PROCESSED, real_outputs
from pipeline import events, footprints


def test_overpasses_not_summed(cfg, make_detections):
    # One fire seen by two S-NPP pixels at 07:30 (sum 10 MW) and one NOAA-20 pixel
    # at 08:20 (6 MW). The event max must be 10, never 16.
    det = make_detections([
        {"frp": 4.0}, {"latitude": 23.8033, "frp": 6.0},
        {"satellite": "N20", "acq_time": 820, "latitude": 23.8015, "frp": 6.0},
    ])
    ev = events.run(footprints.run(det, cfg), cfg)
    assert len(ev["events"]) == 1
    e = ev["events"].iloc[0]
    assert e["n_overpasses"] == 2
    assert e["FRP_VIIRS_max"] == 10.0
    assert e["FRP_VIIRS_mean_overpass"] == 8.0
    ov = ev["overpasses"]
    assert sorted(ov["frp_sum_mw"]) == [6.0, 10.0]


def test_same_platform_different_times_are_separate(cfg, make_detections):
    det = make_detections([{"frp": 3.0}, {"acq_time": 912, "frp": 5.0}])
    ev = events.run(footprints.run(det, cfg), cfg)
    assert ev["events"].iloc[0]["FRP_VIIRS_max"] == 5.0


@real_outputs
def test_real_outputs_never_sum_across_time():
    det = pd.read_parquet(PROCESSED / "detections_clean.parquet")
    ov = pd.read_csv(INTERIM / "event_overpasses.csv")
    ev = pd.read_csv(PROCESSED / "fire_events.csv")
    # Each overpass row covers one platform and one acquisition time.
    per = det.groupby(["fire_id", "platform", "acq_datetime_utc"])["frp_mw"].sum()
    assert len(per) == len(ov)
    assert np.isclose(per.sum(), ov["frp_sum_mw"].sum())
    # Event FRP equals the maximum per-overpass sum, which is never above the event's
    # single-overpass maximum.
    vmax = ov[ov["sensor"] == "VIIRS"].groupby("fire_id")["frp_sum_mw"].max()
    got = ev.set_index("fire_id")["FRP_VIIRS_max"].dropna()
    assert np.allclose(got.sort_index(), vmax.loc[got.index].sort_index())
    # grid_daily: FRP per cell-day is a max over overpasses, so it never exceeds
    # the sum of all overpass values for that cell-day (and equals it only with one overpass).
    gd = pd.read_csv(PROCESSED / "grid_daily.csv")
    go = pd.read_csv(INTERIM / "grid_overpass.csv")
    mx = go.groupby(["cell_id", "date"])["frp_mw"].max()
    assert np.allclose(gd.set_index(["cell_id", "date"])["frp_max_overpass_mw"].loc[mx.index], mx)
