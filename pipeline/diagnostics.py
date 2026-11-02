"""Phase 2, Part A: diagnostics on the Phase 1 outputs, run before any calibration.

A1 "both" events by MODIS platform combination and by VIIRS platform
A2 Aqua-VIIRS time differences per VIIRS platform (histogram, median, shares)
A3 MODIS_only events by Terra/Aqua and day/night
A6 fire events in candidate pilot boxes
(A4 URT near-duplicates and A5 partial days live in pipeline/quality.py,
because they change which detections reach Steps 3-5.)
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.figures import GRID, INK, INK2, PLATFORM_COLORS, SURFACE, _style  # noqa: E402

VIIRS = ["S-NPP", "NOAA-20", "NOAA-21"]


def both_breakdown(ev: pd.DataFrame) -> dict:
    b = ev[ev["sensor_flag"] == "both"]
    plats = b["platforms_seen"].str.split(";")
    has_t = plats.apply(lambda p: "Terra" in p)
    has_a = plats.apply(lambda p: "Aqua" in p)
    combo = np.select([has_t & has_a, has_a, has_t], ["Terra+Aqua+VIIRS", "Aqua+VIIRS", "Terra+VIIRS"], "?")
    by_combo = pd.Series(combo).value_counts().reindex(
        ["Terra+VIIRS", "Aqua+VIIRS", "Terra+Aqua+VIIRS"], fill_value=0)
    by_viirs = {p: int(plats.apply(lambda s, p=p: p in s).sum()) for p in VIIRS}
    viirs_set = plats.apply(lambda s: "+".join(p for p in VIIRS if p in s)).value_counts()
    return {"n": len(b), "by_combo": by_combo.to_dict(), "by_viirs_platform": by_viirs,
            "by_viirs_set": viirs_set.to_dict()}


def aqua_viirs_dt(ov: pd.DataFrame) -> pd.DataFrame:
    """For every Aqua overpass of an event, the nearest overpass of each VIIRS platform
    of the same event. dt_min = VIIRS time - Aqua time (minutes, signed)."""
    ov = ov.copy()
    ov["acq_datetime_utc"] = pd.to_datetime(ov["acq_datetime_utc"], utc=True)
    a = ov[ov["platform"] == "Aqua"][["fire_id", "acq_datetime_utc"]]
    v = ov[ov["platform"].isin(VIIRS)][["fire_id", "platform", "acq_datetime_utc"]]
    m = a.merge(v, on="fire_id", suffixes=("_aqua", "_viirs"))
    m["dt_min"] = (m["acq_datetime_utc_viirs"] - m["acq_datetime_utc_aqua"]).dt.total_seconds() / 60
    m["abs_dt"] = m["dt_min"].abs()
    idx = m.groupby(["fire_id", "acq_datetime_utc_aqua", "platform"])["abs_dt"].idxmin()
    return m.loc[idx].reset_index(drop=True)


def dt_stats(nearest: pd.DataFrame) -> dict:
    out = {}
    for p in VIIRS:
        d = nearest.loc[nearest["platform"] == p, "abs_dt"]
        out[p] = {"n": int(len(d)), "median_abs_min": float(d.median()) if len(d) else np.nan,
                  **{f"share_le_{w}": float((d <= w).mean()) if len(d) else np.nan for w in (30, 45, 60)}}
    return out


def plot_dt_hist(nearest: pd.DataFrame, out, windows: dict | None = None) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14, 3.8), facecolor=SURFACE, sharey=False)
    bins = np.arange(-180, 185, 5)
    for ax, p in zip(axes, VIIRS):
        _style(ax)
        ax.grid(axis="x", visible=False)
        d = nearest.loc[nearest["platform"] == p, "dt_min"]
        inside = d[(d >= -180) & (d <= 180)]
        ax.hist(inside, bins=bins, color=PLATFORM_COLORS[p], edgecolor=SURFACE, linewidth=0.6)
        for w, ls in ((30, ":"), (60, "--")):
            for s in (-w, w):
                ax.axvline(s, color=INK2, linewidth=0.8, linestyle=ls)
        if windows and p in windows:
            ax.axvspan(-windows[p], windows[p], color=GRID, alpha=0.5, zorder=0)
        med = d.abs().median() if len(d) else np.nan
        ax.set_title(f"{p}: n={len(d):,}, median |Δt|={med:.1f} min", color=INK, fontsize=9.5, loc="left")
        ax.set_xlabel("VIIRS time − Aqua time (min), 5-min bins", color=INK2, fontsize=8)
        if len(d) > len(inside):
            ax.text(0.98, 0.95, f"{len(d) - len(inside):,} beyond ±180 min", transform=ax.transAxes,
                    ha="right", va="top", fontsize=7.5, color=INK2)
    axes[0].set_ylabel("Aqua overpasses (nearest VIIRS overpass)", color=INK2, fontsize=8)
    fig.suptitle("Aqua–VIIRS time difference within the same fire event. Dotted ±30 min, dashed ±60 min; "
                 "shaded = chosen window", color=INK, fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def choose_window(nearest: pd.DataFrame, platform: str, base: int, cap: int) -> dict:
    """Smallest window (multiple of 5 min, <= cap) covering the main peak of |Δt|.

    Main peak = the mode 5-min bin of |Δt| in 0-180 min plus the contiguous bins
    around it holding at least half the mode's count (full width at half max).
    """
    d = nearest.loc[nearest["platform"] == platform, "abs_dt"]
    bins = np.arange(0, 185, 5)
    h, _ = np.histogram(d[d <= 180], bins=bins)
    if h.sum() == 0:
        return {"window_min": base, "peak_bin": None, "peak_upper": None, "reason": "no data"}
    k = int(h.argmax())
    hi = k
    while hi + 1 < len(h) and h[hi + 1] >= 0.5 * h[k]:
        hi += 1
    peak_upper = int(bins[hi + 1])
    if peak_upper <= base:
        w, why = base, f"main peak ends at {peak_upper} min, inside the default {base} min"
    elif peak_upper <= cap:
        w, why = peak_upper, f"main peak extends to {peak_upper} min; widened from {base}"
    else:
        w, why = cap, (f"main peak extends to {peak_upper} min, beyond the {cap} min maximum; "
                       f"capped at {cap} (pairs are the peak's leading edge only)")
    return {"window_min": int(w), "peak_bin": f"{bins[k]}-{bins[k + 1]} min", "peak_count": int(h[k]),
            "peak_upper": peak_upper, "reason": why}


def modis_only_breakdown(ev: pd.DataFrame, det: pd.DataFrame) -> dict:
    mo = ev[ev["sensor_flag"] == "MODIS_only"]
    plats = mo["platforms_seen"]
    by_plat = plats.map({"Terra": "Terra only", "Aqua": "Aqua only", "Aqua;Terra": "Terra+Aqua"}).value_counts()
    dn = (det[det["fire_id"].isin(mo["fire_id"])].groupby("fire_id")["daynight"]
          .agg(lambda s: "".join(sorted(set(s)))).map({"D": "day", "N": "night", "DN": "day+night"}))
    tab = pd.crosstab(plats.map({"Terra": "Terra", "Aqua": "Aqua", "Aqua;Terra": "Terra+Aqua"}).values,
                      dn.reindex(mo["fire_id"]).values)
    return {"n": len(mo), "by_platform": by_plat.to_dict(), "by_daynight": dn.value_counts().to_dict(),
            "table": tab}


def pilot_boxes(ev: pd.DataFrame, boxes: dict) -> pd.DataFrame:
    rows = []
    for name, (x0, y0, x1, y1) in boxes.items():
        e = ev[ev["centroid_lon"].between(x0, x1) & ev["centroid_lat"].between(y0, y1)]
        n_both = int((e["sensor_flag"] == "both").sum())
        rows.append({"box": name, "bbox": [x0, y0, x1, y1], "events": len(e), "both": n_both,
                     "share_both": n_both / len(e) if len(e) else np.nan,
                     "with_aqua": int(e["platforms_seen"].str.contains("Aqua").sum()),
                     "detections": int(e["n_detections"].sum())})
    return pd.DataFrame(rows)
