"""Drift history helpers and the drifted_era flag."""
import numpy as np
import pandas as pd

from pipeline import drift, ingest
from conftest import firms_rows


def _cfg_with(cfg, first):
    return {**cfg, "drift": {**cfg.get("drift", {}), "first_drift_year": first}}


def test_drifted_era_flag(cfg):
    rows = firms_rows([
        dict(instrument="MODIS", satellite="Aqua", confidence="70", brightness=330.0, bright_t31=290.0,
             acq_date="2026-10-30"),
        dict(instrument="MODIS", satellite="Aqua", confidence="70", brightness=330.0, bright_t31=290.0,
             acq_date="2015-10-30"),
        dict(instrument="MODIS", satellite="Terra", confidence="70", brightness=330.0, bright_t31=290.0,
             acq_date="2021-10-30"),
        dict(acq_date="2026-10-30"),  # VIIRS
    ])
    det = ingest.standardize(rows, _cfg_with(cfg, {"Terra": 2020, "Aqua": 2022}))
    assert det["drifted_era"].tolist()[:3] == [True, False, True]
    assert pd.isna(det["drifted_era"].iloc[3])
    # No drift year configured: unknown, never silently False.
    det2 = ingest.standardize(rows, _cfg_with(cfg, {"Terra": None, "Aqua": None}))
    assert det2["drifted_era"].isna().all()


def test_pair_dt_and_hhmm():
    t = pd.Timestamp("2015-10-29 06:00")
    df = pd.DataFrame({"platform": ["Aqua", "S-NPP", "Aqua", "S-NPP"],
                       "t": [t, t + pd.Timedelta(minutes=8), t, t + pd.Timedelta(minutes=50)],
                       "lat": [10.0, 10.003, 20.0, 20.5], "lon": [30.0, 30.0, 40.0, 40.0]})
    med, n = drift.pair_dt(df, radius_km=1.0)
    assert n == 1 and med == 8.0          # the 20.5° detection is 55 km away: not a pair
    assert drift.hhmm(13.5) == "13:30" and drift.hhmm(np.nan) == "–"
