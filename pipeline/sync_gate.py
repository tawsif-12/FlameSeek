"""Synchronization gate for calibration windows (decisions.md D68).

A window qualifies for a synchronized FRP calibration only when both hold:
  (a) no-drift evidence: the median local solar time of the window's daytime Aqua
      detections is within `aqua_lst_tolerance_min` of `aqua_nominal_lst_h` (13:30);
  (b) enough sample: at least `min_pairs` Aqua-S-NPP event-overpass pairs with
      |dt| <= calibration.sync_max_dt_min after the truncation filter
      (both FRP >= calibration.trunc_frp_mw).
The same rule and thresholds apply to every window.
"""
from __future__ import annotations

import pandas as pd

from pipeline import calibration


def aqua_daytime_lst(det: pd.DataFrame) -> dict:
    """Median local solar time (h) of daytime Aqua detections (lst_h from Phase 1 ingest)."""
    d = det[det["platform"].astype(str).eq("Aqua") & det["daynight"].eq("D")]["lst_h"].dropna()
    return {"n": int(len(d)), "median_lst_h": float(d.median()) if len(d) else None}


def snpp_pairs(ov_enriched: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Aqua-S-NPP pairs built exactly as calibration.build_pairs, restricted to S-NPP."""
    c = {**cfg, "events": {**cfg["events"], "matched_pair_viirs": ["S-NPP"]}}
    return calibration.build_pairs(ov_enriched, c)


def filtered(pairs: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """The fit_sync sample filter: |dt| <= sync_max_dt_min and both FRP >= trunc_frp_mw."""
    c = cfg["calibration"]
    if pairs.empty:
        return pairs
    return pairs[(pairs["dt_min"].abs() <= c["sync_max_dt_min"])
                 & (pairs["frp_sum_mw_modis"] >= c["trunc_frp_mw"])
                 & (pairs["frp_sum_mw_viirs"] >= c["trunc_frp_mw"])]


def evaluate(det: pd.DataFrame, ov_enriched: pd.DataFrame, cfg: dict) -> dict:
    g = cfg["sync_gate"]
    lst = aqua_daytime_lst(det)
    nominal, tol = g["aqua_nominal_lst_h"], g["aqua_lst_tolerance_min"]
    offset = None if lst["median_lst_h"] is None else (lst["median_lst_h"] - nominal) * 60
    a_pass = offset is not None and abs(offset) <= tol
    pairs = snpp_pairs(ov_enriched, cfg)
    n_pairs = int(len(filtered(pairs, cfg)))
    b_pass = n_pairs >= g["min_pairs"]
    return {
        "window": cfg["window"]["name"],
        "rule": (f"(a) |median daytime Aqua LST - {nominal} h| <= {tol} min AND "
                 f"(b) >= {g['min_pairs']} Aqua-S-NPP pairs with |dt| <= "
                 f"{cfg['calibration']['sync_max_dt_min']} min and both FRP >= "
                 f"{cfg['calibration']['trunc_frp_mw']} MW"),
        "a_no_drift": {"n_aqua_day": lst["n"], "median_lst_h": lst["median_lst_h"],
                       "offset_min": offset, "tolerance_min": tol, "pass": bool(a_pass)},
        "b_sample": {"n_pairs_all_dt": int(len(pairs)), "n_pairs_filtered": n_pairs,
                     "min_pairs": g["min_pairs"], "pass": bool(b_pass)},
        "synchronized": bool(a_pass and b_pass),
    }


def old_rule(nearest: pd.DataFrame) -> dict:
    """The replaced D61 rule (median |Aqua - S-NPP dt| over shared events <= 20 min).
    Recorded for comparison only; it no longer decides anything (D68)."""
    s = nearest[nearest["platform"].eq("S-NPP")]["dt_min"].abs().dropna()
    med = float(s.median()) if len(s) else None
    return {"rule": "median |Aqua - S-NPP dt| over shared events <= 20 min (replaced by D68)",
            "n_pairs": int(len(s)), "median_abs_dt_min": med, "synchronized": med is not None and med <= 20}
