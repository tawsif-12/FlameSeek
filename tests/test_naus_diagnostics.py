"""Northern Australia diurnal diagnostics helpers (D71)."""
import numpy as np
import pandas as pd

from pipeline import naus_diagnostics as nd


def test_satellite_zenith_is_zero_below_the_satellite():
    zen, _ = nd.satellite_angles(np.array([140.7]), np.array([0.0]))
    assert zen[0] < 1e-6


def test_satellite_is_north_east_of_northern_australia():
    zen, az = nd.satellite_angles(np.array([130.0]), np.array([-15.0]))
    assert 0 < zen[0] < 40 and 0 < az[0] < 90


def test_glint_angle_zero_at_specular_geometry_and_large_otherwise():
    assert nd.glint_angle_deg(30.0, 100.0, 30.0, 280.0) < 1e-6
    assert nd.glint_angle_deg(30.0, 100.0, 30.0, 100.0) > 59


def _fires(rows):
    base = dict(frp_mw=10.0, daynight="N", lst_h=19.0, glint_deg=np.nan, reference_match=False,
                location_confirmed=False, longitude=130.0, latitude=-15.0)
    return pd.DataFrame([{**base, **r} for r in rows])


def test_persistent_location_needs_repeats_days_and_no_confirmation():
    t = pd.to_datetime(["2026-10-29 10:00", "2026-10-30 10:00", "2026-10-30 11:00"], utc=True)
    f = _fires([dict(pixel_id=1, acq_datetime_utc=x) for x in t] +
               [dict(pixel_id=2, acq_datetime_utc=x, location_confirmed=True) for x in t] +
               [dict(pixel_id=3, acq_datetime_utc=t[0]), dict(pixel_id=3, acq_datetime_utc=t[0]),
                dict(pixel_id=3, acq_datetime_utc=t[0])])
    assert nd.persistent_locations(f).index.tolist() == [1]


def test_top_unmatched_locations_ignore_matched_detections():
    t = pd.Timestamp("2026-10-29 10:00", tz="UTC")
    f = _fires([dict(acq_datetime_utc=t, reference_match=True)] * 5 +
               [dict(acq_datetime_utc=t, longitude=131.0)] * 2)
    top = nd.top_unmatched_locations(f)
    assert len(top) == 1 and top.n_unmatched.iloc[0] == 2 and abs(top.longitude.iloc[0] - 131.0) < 1e-9


def test_summary_flags_unfitted_model():
    assert nd.summarize({"fitted": False, "reason": "x", "sample_size": 3}) == {"fitted": False, "reason": "x", "n_points": 3}


def test_time_match_is_unit_safe_for_microsecond_columns():
    from pipeline import himawari as hw
    q = pd.DataFrame(dict(latitude=[-15.0, -15.0], longitude=[130.0, 130.0],
                          acq_datetime_utc=pd.to_datetime(["2026-10-30 10:00", "2026-10-30 10:00"], utc=True).as_unit("us")))
    r = pd.DataFrame(dict(latitude=[-15.0], longitude=[130.0],
                          acq_datetime_utc=pd.to_datetime(["2026-10-30 11:30"], utc=True).as_unit("us")))
    assert not nd.time_match(q, r, 60, 2).any()
    assert nd.time_match(q, r, 90, 2).all()
    # D72: the shared helper is unit-safe (it treated microseconds as nanoseconds before).
    assert not hw.nearby(q, r, 60, 2).any()
    ns = q.assign(acq_datetime_utc=q.acq_datetime_utc.dt.as_unit("ns"))
    assert not hw.nearby(ns, r, 60, 2).any() and hw.nearby(ns, r, 90, 2).all()
