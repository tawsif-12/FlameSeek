"""Eras measured from the data, not from hardcoded dates.

Per platform and month:
  lst_median  median local solar time of daytime detections in |lat| <= lat_band
              (exact to 1 minute, from a minute histogram filled while the raw files are split)
  reference   the platform's measured early-archive LST (median of the first three years in
              data/processed/drift_by_year.csv) when that file exists, else its nominal
              crossing time from config (a specification, not a date)
  drifted     |lst_median - reference| > drift_threshold_min (None when too few detections)
Per month:
  era_sensor  "multi_sensor" when any VIIRS platform has detections that month, else "MODIS_only"
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.config import ROOT

VIIRS = ("S-NPP", "NOAA-20", "NOAA-21")


def references(cfg: dict) -> dict:
    nominal = dict(cfg["eras"]["nominal_lst"])
    ref = {p: (float(v), "nominal design crossing time") for p, v in nominal.items()}
    f = ROOT / "data" / "processed" / "drift_by_year.csv"
    if f.exists():
        t = pd.read_csv(f).set_index("year").sort_index()
        for p in nominal:
            if p in t.columns and t[p].notna().sum() >= 3:
                s = t[p].dropna()
                ref[p] = (float(s.iloc[:3].median()),
                          f"measured early-archive median {int(s.index[0])}-{int(s.index[2])} (drift_by_year.csv)")
    return ref


def _median_from_hist(h: np.ndarray) -> float:
    c = np.cumsum(h)
    return float(np.searchsorted(c, c[-1] / 2.0)) / 60.0 if c[-1] else np.nan


def measure(hist: dict, presence: dict, cfg: dict) -> pd.DataFrame:
    e = cfg["eras"]
    ref = references(cfg)
    months = sorted({m for _, m in presence})
    rows = []
    for (p, m), n_rows in sorted(presence.items()):
        if not isinstance(p, str):
            continue
        h = hist.get((p, m))
        n_day = int(h.sum()) if h is not None else 0
        lst = _median_from_hist(h) if n_day else np.nan
        r, src = ref.get(p, (np.nan, "none"))
        dev = (lst - r) * 60 if np.isfinite(lst) and np.isfinite(r) else np.nan
        drifted = (bool(abs(dev) > e["drift_threshold_min"]) if n_day >= e["min_day_detections"] and np.isfinite(dev)
                   else None)
        rows.append({"platform": p, "month": m, "n_rows": int(n_rows), "n_day_lst": n_day,
                     "lst_median_h": lst, "reference_h": r, "reference_source": src,
                     "deviation_min": dev, "drifted": drifted})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    viirs_months = set(df.loc[df["platform"].isin(VIIRS) & (df["n_rows"] > 0), "month"])
    df["era_sensor"] = df["month"].map(lambda m: "multi_sensor" if m in viirs_months else "MODIS_only")
    del months
    return df


def flag_rows(det: pd.DataFrame, era_records: list[dict]) -> pd.Series:
    """drifted_era per detection: MODIS rows take their platform-month measurement
    (True/False, or <NA> when it could not be measured); VIIRS rows are <NA>."""
    out = pd.Series(pd.NA, index=det.index, dtype="boolean")
    if not era_records:
        return out
    look = {(r["platform"], r["month"]): r["drifted"] for r in era_records}
    month = det["acq_datetime_utc"].dt.strftime("%Y-%m")
    is_m = det["sensor"].eq("MODIS").fillna(False)
    vals = [look.get((p, m)) for p, m in zip(det.loc[is_m, "platform"], month[is_m])]
    out[is_m] = pd.array([pd.NA if v is None else bool(v) for v in vals], dtype="boolean")
    return out


def summary(era_records: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(era_records)
    if df.empty:
        return df
    return df[["platform", "month", "n_day_lst", "lst_median_h", "reference_h", "deviation_min", "drifted",
               "era_sensor", "reference_source"]]
