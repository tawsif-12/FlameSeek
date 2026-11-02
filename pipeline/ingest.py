"""Step 1: clean and standardize.

Merges every FIRMS CSV in data/raw/ into one table where every row is a
detection in the same units, whatever sensor produced it. Raw files are only
read, never written.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.inspect_raw import PLATFORM_CODES, parse_acq_date, read_firms_csv

SENSOR_OF_PLATFORM = {"Terra": "MODIS", "Aqua": "MODIS",
                      "S-NPP": "VIIRS", "NOAA-20": "VIIRS", "NOAA-21": "VIIRS"}


def load_raw(raw_dir: Path) -> pd.DataFrame:
    """1. Merge all files. Keeps the source file and row so every detection is traceable."""
    frames = []
    for f in sorted(Path(raw_dir).glob("*.csv")):
        df = read_firms_csv(f)
        df["source_file"] = f.name
        df["source_row"] = np.arange(len(df)) + 2  # +2: header line and 1-based numbering
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No FIRMS CSV files in {raw_dir}")
    return pd.concat(frames, ignore_index=True, sort=False)


def confidence_to_p(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """6. Map VIIRS l/n/h and MODIS 0-100 onto one probability scale (0.3/0.6/0.9)."""
    c = cfg["confidence"]
    p = c["p_conf"]
    raw = df["confidence"].astype(str).str.strip().str.lower()
    out = pd.Series(np.nan, index=df.index)

    viirs = df["sensor"] == "VIIRS"
    out[viirs] = raw[viirs].map({code: p[cls] for code, cls in c["viirs_codes"].items()})

    modis = df["sensor"] == "MODIS"
    num = pd.to_numeric(raw[modis], errors="coerce")
    out[modis] = np.select([num >= c["modis_high_min"], num >= c["modis_nominal_min"], num >= 0],
                           [p["high"], p["nominal"], p["low"]], default=np.nan)
    return out


def standardize(raw: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = raw.copy()

    # 2. Sensor from the `instrument` column (never the file name); platform from `satellite`.
    df["sensor"] = df["instrument"].astype(object).str.strip().str.upper()
    df["platform"] = df["satellite"].astype(object).str.strip().map(PLATFORM_CODES)
    mismatch = df["platform"].map(SENSOR_OF_PLATFORM).ne(df["sensor"]) & df["platform"].notna()
    df["sensor_platform_mismatch"] = mismatch.fillna(False)

    # 3. Unified brightness. Columns missing from a file come through as NaN after the merge.
    for col in ("bright_ti4", "bright_ti5", "brightness", "bright_t31"):
        if col not in df:
            df[col] = np.nan
    is_v = (df["sensor"] == "VIIRS").fillna(False).to_numpy(bool)
    df["bt_k"] = np.where(is_v, df["bright_ti4"], df["brightness"])
    df["bt_bg_k"] = np.where(is_v, df["bright_ti5"], df["bright_t31"])

    # 4. Time: acq_date + acq_time (HHMM, UTC).
    date = parse_acq_date(df["acq_date"])
    hhmm = pd.to_numeric(df["acq_time"], errors="coerce")
    df["acq_datetime_utc"] = (date + pd.to_timedelta(hhmm // 100, unit="h")
                              + pd.to_timedelta(hhmm % 100, unit="m")).dt.tz_localize("UTC")

    # 5. Local solar time from the actual timestamp: lst = (h_UTC + lon/15) mod 24.
    h_utc = df["acq_datetime_utc"].dt.hour + df["acq_datetime_utc"].dt.minute / 60.0
    df["lst_h"] = (h_utc + df["longitude"] / 15.0) % 24
    local_dt = df["acq_datetime_utc"].dt.tz_localize(None) + pd.to_timedelta(df["longitude"] / 15.0, unit="h")
    df["local_solar_date"] = local_dt.dt.strftime("%Y-%m-%d")
    df["utc_date"] = df["acq_datetime_utc"].dt.strftime("%Y-%m-%d")

    df["p_conf"] = confidence_to_p(df, cfg)
    df["conf_class"] = df["p_conf"].map({v: k for k, v in cfg["confidence"]["p_conf"].items()})
    df["drifted_era"] = drifted_era(df, cfg)

    df = df.rename(columns={"frp": "frp_mw", "scan": "scan_km", "track": "track_km"})
    df.insert(0, "det_id", np.arange(len(df)))
    keep = ["det_id", "sensor", "platform", "acq_datetime_utc", "utc_date", "local_solar_date", "lst_h",
            "latitude", "longitude", "bt_k", "bt_bg_k", "p_conf", "conf_class", "confidence",
            "frp_mw", "scan_km", "track_km", "daynight", "version", "type", "drifted_era",
            "sensor_platform_mismatch", "source_file", "source_row"]
    return df[[c for c in keep if c in df.columns]]


def drifted_era(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """MODIS rows: True when the detection year is at or after its platform's first drifted
    year (config drift.first_drift_year, from run_phase2b.py), else False. VIIRS rows: <NA>.
    If no drift year is configured for a platform, its rows stay <NA> (unknown, not False)."""
    first = (cfg.get("drift") or {}).get("first_drift_year") or {}
    out = pd.Series(pd.NA, index=df.index, dtype="boolean")
    year = df["acq_datetime_utc"].dt.year
    for plat in ("Terra", "Aqua"):
        m = (df["platform"] == plat).fillna(False) & year.notna()
        y0 = first.get(plat)
        if y0 is not None:
            out[m] = (year[m] >= int(y0)).to_numpy()
    return out


def run(cfg: dict) -> pd.DataFrame:
    raw = load_raw(cfg["paths"]["raw_dir"])
    det = standardize(raw, cfg)
    print(f"[Step 1] merged {len(raw)} raw rows from "
          f"{raw['source_file'].nunique()} files -> standardized table")
    return det
