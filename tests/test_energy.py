"""Total FRP must be equal before and after gridding."""
import numpy as np
import pandas as pd

from conftest import INTERIM, PROCESSED, real_outputs
from pipeline import events, footprints, grid


def test_energy_conserved_synthetic(cfg, make_detections):
    # A MODIS swath-edge pixel (4.8 x 2 km) sitting on a 0.1 deg cell corner must be
    # split across cells by overlap, and the FRP total must not change.
    det = make_detections([
        {"latitude": 23.80, "longitude": 90.40, "instrument": "MODIS", "satellite": "Aqua",
         "confidence": "85", "scan": 4.8, "track": 2.0, "frp": 120.0, "brightness": 340.0,
         "bright_t31": 295.0, "bright_ti4": None, "bright_ti5": None},
        {"latitude": 23.801, "longitude": 90.401, "frp": 7.5},
        {"latitude": 23.849, "longitude": 90.499, "frp": 3.25, "acq_time": 1910, "daynight": "N"},
    ])
    fp = footprints.run(det, cfg)
    ev = events.run(fp, cfg)
    gr = grid.run(ev["detections"], cfg)
    assert np.isclose(gr["energy"]["frp_before_mw"], 130.75)
    assert np.isclose(gr["energy"]["frp_after_mw"], 130.75, rtol=1e-12)
    # The edge pixel lands in more than one cell (assignment by overlap, not centroid).
    pieces = gr["pieces"]
    assert pieces.loc[pieces["frp_mw"] == 120.0, "cell_id"].nunique() > 1
    # Weights of every footprint sum to one.
    assert np.allclose(pieces.groupby("det_id")["w"].sum(), 1.0)


@real_outputs
def test_energy_conserved_real_outputs():
    det = pd.read_parquet(PROCESSED / "detections_clean.parquet")
    gov = pd.read_csv(INTERIM / "grid_overpass.csv")
    assert np.isclose(det["frp_mw"].sum(), gov["frp_mw"].sum(), rtol=1e-9)
