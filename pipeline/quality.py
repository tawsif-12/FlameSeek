"""Step 2: quality control and false-positive filtering.

Every row that is set aside keeps a reason code in `flags`, so the filtering
can be audited. Three tables come out:
  clean   - nominal/high confidence rows used for harmonization
  lowconf - low-confidence rows (p_conf 0.3), otherwise valid, stored separately
  removed - rows that failed a sanity check (blank, duplicate, outside bbox, ...)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Reason codes. Codes in HARD_REMOVE exclude a row from harmonization.
HARD_REMOVE = {"missing_time", "missing_coords", "missing_frp", "negative_frp", "outside_study_area",
               "invalid_scan_track", "unknown_sensor", "sensor_platform_mismatch",
               "duplicate_detection", "modis_type_1_volcano", "modis_type_2_static_land",
               "modis_type_3_offshore", "urt_duplicate_of_nrt"}

DUP_KEY = ["sensor", "platform", "acq_datetime_utc", "latitude", "longitude",
           "frp_mw", "scan_km", "track_km", "bt_k", "bt_bg_k"]


def detect_bbox(det: pd.DataFrame, pad: float) -> list[float]:
    """Outer bounds of all valid detections, padded and rounded outward to 0.1 deg."""
    ok = det.dropna(subset=["latitude", "longitude"])
    lon0, lon1 = ok["longitude"].min() - pad, ok["longitude"].max() + pad
    lat0, lat1 = ok["latitude"].min() - pad, ok["latitude"].max() + pad
    r = lambda v, f: float(f(v * 10) / 10)  # noqa: E731
    return [max(r(lon0, np.floor), -180.0), max(r(lat0, np.floor), -90.0),
            min(r(lon1, np.ceil), 180.0), min(r(lat1, np.ceil), 90.0)]


def add_flags(det: pd.DataFrame, cfg: dict, bbox: list[float]) -> pd.DataFrame:
    df = det.copy()
    codes: list[pd.Series] = []

    def flag(mask: pd.Series, code: str) -> None:
        codes.append(pd.Series(np.where(mask.fillna(False), code, ""), index=df.index))

    # 6. Sanity checks.
    flag(df["acq_datetime_utc"].isna(), "missing_time")
    flag(df["latitude"].isna() | df["longitude"].isna(), "missing_coords")
    flag(df["frp_mw"].isna(), "missing_frp")
    flag(df["frp_mw"] < 0, "negative_frp")
    lon0, lat0, lon1, lat1 = bbox
    inside = df["longitude"].between(lon0, lon1) & df["latitude"].between(lat0, lat1)
    flag(df["latitude"].notna() & ~inside, "outside_study_area")
    flag(~(df["scan_km"] > 0) | ~(df["track_km"] > 0), "invalid_scan_track")
    flag(df["sensor"].isna() | df["platform"].isna() | ~df["sensor"].isin(["MODIS", "VIIRS"]),
         "unknown_sensor")
    flag(df["sensor_platform_mismatch"], "sensor_platform_mismatch")

    # Exact duplicates (same platform, time, position and values) appear when the
    # same FIRMS export sits in two files. Keep the first copy only.
    dup = df.duplicated(subset=DUP_KEY, keep="first") & df["acq_datetime_utc"].notna()
    flag(dup, "duplicate_detection")

    # 2. Source type (archive data only; NRT files have no `type` column).
    if "type" in df.columns:
        t = pd.to_numeric(df["type"], errors="coerce")
        is_m = df["sensor"] == "MODIS"
        flag(is_m & (t == 1), "modis_type_1_volcano")
        flag(is_m & (t == 2), "modis_type_2_static_land")
        flag(is_m & (t == 3), "modis_type_3_offshore")

    # 1. Confidence (stored separately rather than deleted).
    flag(df["p_conf"].isna(), "missing_confidence")
    flag(df["p_conf"].round(3) == cfg["confidence"]["p_conf"]["low"], "low_confidence")

    # Row-wise join without DataFrame.apply: on a zero-row day apply returns a DataFrame, not a Series.
    table = pd.concat(codes, axis=1)
    df["flags"] = pd.Series([";".join(c for c in row if c) for row in table.itertuples(index=False)],
                            index=df.index, dtype=object)
    return df


def run(det: pd.DataFrame, cfg: dict, bbox=None, partial=None, coverage=None, quiet=False) -> dict:
    """Window-level facts (bbox, partial days, coverage) can be passed in: a single day
    cannot judge them, so the day-by-day pipeline computes them once per window."""
    bbox = bbox or cfg.get("study_bbox") or detect_bbox(det, cfg.get("study_bbox_pad_deg", 0.1))
    df = add_flags(det, cfg, bbox)
    keep_p = set(np.round(cfg["quality"]["keep_p_conf"], 3))

    # A4. URT copies of NRT detections (kept NRT, dropped URT, logged).
    dup_of = urt_near_duplicates(df, cfg["quality"])
    df["dup_of_det_id"] = dup_of
    hit = dup_of.notna()
    df.loc[hit, "flags"] = (df.loc[hit, "flags"] + ";urt_duplicate_of_nrt").str.lstrip(";")

    # A5. Partial days (kept, but excluded from daily statistics).
    if partial is None or coverage is None:
        partial, coverage = partial_days(df, cfg["quality"])
    df["partial_day"] = df["utc_date"].isin(partial)

    # Explicit bool dtype: an empty object Series would be read as a column list by df[...].
    has_hard = pd.Series([bool(set(s.split(";")) & HARD_REMOVE) if s else False for s in df["flags"]],
                         index=df.index, dtype=bool)
    removed = df[has_hard].copy()
    rest = df[~has_hard]
    clean = rest[rest["p_conf"].round(3).isin(keep_p)].copy()
    lowconf = rest[~rest["p_conf"].round(3).isin(keep_p)].copy()

    reason_counts = (df.loc[df["flags"] != "", "flags"].str.split(";").explode().value_counts().to_dict())
    not_applied = {
        "persistent_hotspot_mask": "needs multi-year history (>30% of years rule); data covers only a few days",
        "nightfire_flare_mask": "disabled in config; no VIIRS Nightfire flare list available",
        "transient_filter": "needs Himawari detections within +/-30 min; no Himawari data in this run",
        "modis_type_filter": ("applied" if "type" in df.columns
                              else "NRT files have no `type` column; cannot drop volcano/static/offshore"),
    }
    if not quiet:
        print(f"[Step 2] clean={len(clean)}  low-confidence={len(lowconf)}  removed={len(removed)}  "
              f"bbox={bbox}")
        print(f"         reason codes: {reason_counts}")
        print(f"         URT near-duplicates of NRT rows: {int(hit.sum())}; partial UTC days: {partial or 'none'}")
    return {"clean": clean, "lowconf": lowconf, "removed": removed, "bbox": bbox,
            "reason_counts": reason_counts, "not_applied": not_applied,
            "n_urt_rows": int(df["version"].astype(str).str.contains("URT").sum()),
            "n_urt_duplicates": int(hit.sum()), "partial_days": partial, "coverage": coverage,
            "day_counts": df.groupby("utc_date").size().to_dict()}


def urt_near_duplicates(df: pd.DataFrame, q: dict) -> pd.Series:
    """det_id of the NRT row each URT row duplicates (same platform, |Δt| <= urt_dup_max_dt_min,
    distance <= urt_dup_max_dist_m), else NaN. Ultra-real-time (URT) rows are early copies that
    FIRMS later re-issues as NRT, so the NRT row is kept."""
    from sklearn.neighbors import BallTree
    out = pd.Series(np.nan, index=df.index)
    ver = df["version"].astype(str)
    ok = df["latitude"].notna() & df["longitude"].notna() & df["acq_datetime_utc"].notna()
    urt, nrt = df[ok & ver.str.contains("URT")], df[ok & ~ver.str.contains("URT")]
    r = q["urt_dup_max_dist_m"] / 6_371_008.8
    max_dt = pd.Timedelta(minutes=q["urt_dup_max_dt_min"])
    for plat, u in urt.groupby("platform"):
        n = nrt[nrt["platform"] == plat]
        if n.empty:
            continue
        tree = BallTree(np.radians(n[["latitude", "longitude"]].to_numpy()), metric="haversine")
        neigh, dist = tree.query_radius(np.radians(u[["latitude", "longitude"]].to_numpy()), r=r,
                                        return_distance=True, sort_results=True)
        for ui, (nb, _) in enumerate(zip(neigh, dist)):
            if len(nb) == 0:
                continue
            dt = (n["acq_datetime_utc"].iloc[nb] - u["acq_datetime_utc"].iloc[ui]).abs()
            good = np.flatnonzero((dt <= max_dt).to_numpy())
            if len(good):
                out.loc[u.index[ui]] = n["det_id"].iloc[nb[good[0]]]
    return out


def partial_days(df: pd.DataFrame, q: dict) -> tuple[list[str], dict]:
    """UTC dates whose detection count is below partial_day_min_share x the median of the
    other dates (only the first and last dates are tested: a download cut-off truncates
    the ends). Returns the dates and the fully covered UTC interval."""
    counts = df.dropna(subset=["acq_datetime_utc"]).groupby("utc_date").size().sort_index()
    partial = []
    if len(counts) >= 3:
        for d in (counts.index[0], counts.index[-1]):
            others = counts.drop(d)
            if counts[d] < q["partial_day_min_share"] * others.median():
                partial.append(d)
    full = [d for d in counts.index if d not in partial]
    coverage = {"start_utc": pd.Timestamp(full[0], tz="UTC") if full else None,
                "end_utc": pd.Timestamp(full[-1], tz="UTC") + pd.Timedelta(days=1) if full else None}
    return sorted(set(partial)), coverage
