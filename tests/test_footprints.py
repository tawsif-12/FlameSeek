"""Footprint areas must fall inside the expected sensor ranges."""
import geopandas as gpd
import numpy as np
import pytest
import shapely
from pyproj import Transformer

from conftest import INTERIM, real_outputs
from pipeline import footprints

CASES = [  # (instrument, satellite, scan, track)
    ("VIIRS", "N", 0.375, 0.375),   # nadir
    ("VIIRS", "N20", 0.80, 0.78),   # swath edge
    ("MODIS", "Aqua", 1.0, 1.0),    # nadir
    ("MODIS", "Terra", 4.8, 2.0),   # swath edge
]


@pytest.mark.parametrize("instrument,sat,scan,track", CASES)
@pytest.mark.parametrize("lat", [0.0, 23.8, 65.0])
def test_area_in_range(cfg, make_detections, instrument, sat, scan, track, lat):
    conf = "n" if instrument == "VIIRS" else "60"
    det = make_detections([{"latitude": lat, "instrument": instrument, "satellite": sat,
                            "scan": scan, "track": track, "confidence": conf,
                            "brightness": 330.0, "bright_t31": 290.0}])
    fp = footprints.run(det, cfg)
    area = fp["footprint_area_km2"].iloc[0]
    lo, hi = cfg["footprints"]["area_range_km2"][instrument]
    assert lo <= area <= hi
    assert area == pytest.approx(scan * track, rel=2e-3)  # equals scan x track (km2)


def test_matches_explicit_aeqd(cfg, make_detections):
    """Closed-form corners equal a rectangle built in an explicit local AEQD projection."""
    det = make_detections([{"latitude": 23.8, "longitude": 90.4, "scan": 0.8, "track": 0.78}])
    fp = footprints.run(det, cfg.copy() | {"footprints": {**cfg["footprints"], "orientation": "north_up"}})
    to_ll = Transformer.from_crs("+proj=aeqd +lat_0=23.8 +lon_0=90.4 +datum=WGS84 +units=m",
                                 "EPSG:4326", always_xy=True)
    xs = np.array([-400, 400, 400, -400.0])
    ys = np.array([-390, -390, 390, 390.0])
    lon, lat = to_ll.transform(xs, ys)
    got = shapely.get_coordinates(fp.geometry.iloc[0])[:4]
    assert np.allclose(got, np.c_[lon, lat], atol=1e-8)


@real_outputs
def test_real_footprints_in_range(cfg):
    fp = gpd.read_parquet(INTERIM / "footprints.geoparquet")
    for sensor, g in fp.groupby("sensor"):
        lo, hi = cfg["footprints"]["area_range_km2"][sensor]
        assert g["footprint_area_km2"].between(lo, hi).all(), sensor
