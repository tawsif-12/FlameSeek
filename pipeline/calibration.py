"""Step 6B-D: matched pairs, FRP calibration and the MODIS detection-probability curve.

Every FRP value used here is an event's FRP summed WITHIN one overpass (one
platform, one acquisition time), taken from the event-overpass table. Nothing
is ever summed across overpasses. Terra is never paired with VIIRS.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import odr  # noqa: E402

from pipeline.events import window_by_platform  # noqa: E402
from pipeline.figures import INK, INK2, SURFACE, _style  # noqa: E402


# ------------------------------------------------------- overpass table ------
def enrich_overpasses(ov: pd.DataFrame, det: pd.DataFrame, deg: float) -> pd.DataFrame:
    """Event-overpass rows plus day/night, mean position and grid cell, from the detections."""
    from pipeline.grid import cell_id, cell_index
    ov = ov.copy()
    ov["acq_datetime_utc"] = pd.to_datetime(ov["acq_datetime_utc"], utc=True)
    d = det.copy()
    d["acq_datetime_utc"] = pd.to_datetime(d["acq_datetime_utc"], utc=True)
    g = (d.groupby(["fire_id", "platform", "acq_datetime_utc"])
          .agg(daynight=("daynight", "first"), lat=("latitude", "mean"), lon=("longitude", "mean"))
          .reset_index())
    ov = ov.merge(g, on=["fire_id", "platform", "acq_datetime_utc"], how="left")
    ix, iy = cell_index(ov["lon"].to_numpy(), ov["lat"].to_numpy(), deg)
    ov["cell_id"] = cell_id(ix, iy)
    return ov


# ------------------------------------------------------------- pairs ---------
def build_pairs(ov: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """One pair per Aqua event-overpass: the nearest S-NPP/NOAA-20 overpass of the
    same event inside that platform's window. FRP = sum within each overpass."""
    e = cfg["events"]
    if "Terra" in e["matched_pair_modis"]:
        raise ValueError("Terra must never be paired with VIIRS")
    win = window_by_platform(cfg)
    a = ov[ov["platform"].isin(e["matched_pair_modis"])]
    v = ov[ov["platform"].isin(e["matched_pair_viirs"])]
    keep = ["fire_id", "platform", "acq_datetime_utc", "frp_sum_mw", "n_detections", "daynight"]
    p = a[keep].merge(v[keep], on="fire_id", suffixes=("_modis", "_viirs"))
    if p.empty:
        return p
    p["dt_min"] = (p["acq_datetime_utc_viirs"] - p["acq_datetime_utc_modis"]).dt.total_seconds() / 60
    p["window_min"] = p["platform_viirs"].map(win).astype(float)
    p = p[p["dt_min"].abs() <= p["window_min"]]
    p = p.loc[p.groupby(["fire_id", "acq_datetime_utc_modis"])["dt_min"].apply(lambda s: s.abs().idxmin())]
    p = p[(p["frp_sum_mw_modis"] > 0) & (p["frp_sum_mw_viirs"] > 0)]  # log10 needs FRP > 0
    return p.reset_index(drop=True)


# ---------------------------------------------------------------- ODR --------
def _odr_fit(x, y):
    m = odr.ODR(odr.RealData(x, y), odr.Model(lambda b, x: b[0] + b[1] * x), beta0=[0.0, 1.0]).run()
    return m.beta


def fit_odr(pairs: pd.DataFrame, cfg: dict, label: str) -> dict:
    c = cfg["calibration"]
    n = len(pairs)
    if n < c["min_pairs"]:
        return {"subset": label, "n": n, "fitted": False,
                "reason": f"only {n} pairs (< {c['min_pairs']})"}
    x = np.log10(pairs["frp_sum_mw_modis"].to_numpy())
    y = np.log10(pairs["frp_sum_mw_viirs"].to_numpy())
    a, b = _odr_fit(x, y)
    rng = np.random.default_rng(c["seed"])
    boot = np.array([_odr_fit(x[i], y[i]) for i in (rng.integers(0, n, n) for _ in range(c["bootstrap"]))])
    lo, hi = (1 - c["ci"]) / 2 * 100, (1 + c["ci"]) / 2 * 100
    resid = y - (a + b * x)
    return {"subset": label, "n": n, "fitted": True, "a": float(a), "b": float(b),
            "a_lo": float(np.percentile(boot[:, 0], lo)), "a_hi": float(np.percentile(boot[:, 0], hi)),
            "b_lo": float(np.percentile(boot[:, 1], lo)), "b_hi": float(np.percentile(boot[:, 1], hi)),
            "resid_sd_log10": float(resid.std(ddof=2)), "median_ratio_viirs_over_modis":
                float(np.median(10 ** (y - x)))}


def calibrate(pairs: pd.DataFrame, cfg: dict) -> list[dict]:
    out = [fit_odr(pairs, cfg, "all")]
    for dn, name in (("D", "day"), ("N", "night")):
        sub = pairs[pairs["daynight_modis"] == dn]
        out.append(fit_odr(sub, cfg, name))
    return out


# ------------------------------------------------- detection probability -----
def detection_sample(ov: pd.DataFrame, overpasses: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Every VIIRS event-overpass that lies inside a computed Aqua overpass within the
    platform's window, labelled detected=1 if an Aqua detection of the same event was
    acquired at that Aqua overpass (within match_tolerance_min), else 0."""
    c, tol = cfg["calibration"], pd.Timedelta(minutes=cfg["overpasses"]["match_tolerance_min"])
    win = window_by_platform(cfg)
    v = ov[ov["platform"].isin(c["detection_curve_viirs"]) & (ov["frp_sum_mw"] > 0)].copy()
    v["window_min"] = v["platform"].map(win).astype(float)
    aq = overpasses[overpasses["platform"].astype(str) == "Aqua"][
        ["cell_id", "overpass_time_utc", "pixel_area_km2", "scan_angle_deg"]].copy()
    aq["cell_id"] = aq["cell_id"].astype(str)
    v["cell_id"] = v["cell_id"].astype(str)
    v["acq_datetime_utc"] = v["acq_datetime_utc"].astype("datetime64[ns, UTC]")
    aq["overpass_time_utc"] = aq["overpass_time_utc"].astype("datetime64[ns, UTC]")
    v = v.sort_values("acq_datetime_utc")
    aq = aq.sort_values("overpass_time_utc")
    m = pd.merge_asof(v, aq, left_on="acq_datetime_utc", right_on="overpass_time_utc", by="cell_id",
                      direction="nearest")
    m["dt_aqua_min"] = (m["acq_datetime_utc"] - m["overpass_time_utc"]).dt.total_seconds() / 60
    m = m[m["dt_aqua_min"].abs() <= m["window_min"]].copy()
    # Aqua detections of the same event at that Aqua overpass.
    adet = ov[ov["platform"] == "Aqua"][["fire_id", "acq_datetime_utc", "frp_sum_mw"]].rename(
        columns={"acq_datetime_utc": "t_aqua_det", "frp_sum_mw": "frp_aqua_mw"})
    j = m[["fire_id", "overpass_time_utc"]].reset_index().merge(adet, on="fire_id")
    j = j[(j["t_aqua_det"] - j["overpass_time_utc"]).abs() <= tol]
    hit = j.groupby("index")["frp_aqua_mw"].max()
    m["detected"] = m.index.isin(hit.index).astype(int)
    m["frp_aqua_mw"] = hit.reindex(m.index)
    return m.rename(columns={"frp_sum_mw": "frp_viirs_mw", "pixel_area_km2": "a_modis_km2",
                             "scan_angle_deg": "aqua_scan_angle_deg"}).reset_index(drop=True)


def _logit(sample):
    import statsmodels.api as sm
    X = sm.add_constant(np.c_[np.log10(sample["frp_viirs_mw"]), np.log10(sample["a_modis_km2"])])
    return sm.Logit(sample["detected"].to_numpy(), X).fit(disp=0)


def f50(b0, b1, b2, area):
    """FRP (MW) where P = 0.5: b0 + b1 log10 F - b2 log10 A = 0."""
    return 10 ** ((-b0 + b2 * np.log10(area)) / b1)


def fit_detection_curve(sample: pd.DataFrame, cfg: dict) -> dict:
    c = cfg["calibration"]
    n, n1 = len(sample), int(sample["detected"].sum()) if len(sample) else 0
    res = {"n": n, "n_detected": n1, "n_missed": n - n1, "fitted": False}
    if n < c["min_pairs"] or n1 == 0 or n1 == n:
        res["reason"] = (f"sample of {n} with {n1} MODIS detections: a logistic fit needs both outcomes "
                         f"and at least {c['min_pairs']} cases")
        return res
    m = _logit(sample)
    ci = np.asarray(m.conf_int(alpha=1 - c["ci"]))  # rows = coefficients, columns = (lo, hi)
    b0, b1, bA = m.params
    b2 = -bA  # model is written with "- b2 log A"
    edge = c["modis_edge_area_km2"]
    rng = np.random.default_rng(c["seed"])
    boots = []
    for _ in range(c["bootstrap"]):
        s = sample.iloc[rng.integers(0, n, n)]
        if 0 < s["detected"].sum() < n:
            try:
                bb = _logit(s).params
                boots.append([bb[0], bb[1], -bb[2]])
            except Exception:  # perfect separation in a resample
                pass
    boots = np.array(boots)
    lo, hi = (1 - c["ci"]) / 2 * 100, (1 + c["ci"]) / 2 * 100

    def band(area):
        v = f50(boots[:, 0], boots[:, 1], boots[:, 2], area)
        v = v[np.isfinite(v) & (boots[:, 1] > 0)]
        return (float(np.percentile(v, lo)), float(np.percentile(v, hi))) if len(v) else (np.nan, np.nan)

    res.update({"fitted": True, "b0": float(b0), "b1": float(b1), "b2": float(b2),
                "b0_ci": [float(ci[0, 0]), float(ci[0, 1])], "b1_ci": [float(ci[1, 0]), float(ci[1, 1])],
                "b2_ci": [float(-ci[2, 1]), float(-ci[2, 0])],
                "pvalues": [float(p) for p in m.pvalues], "pseudo_r2": float(m.prsquared),
                "f50_nadir_mw": float(f50(b0, b1, b2, 1.0)), "f50_nadir_ci": band(1.0),
                "f50_edge_mw": float(f50(b0, b1, b2, edge)), "f50_edge_ci": band(edge),
                "edge_area_km2": edge, "n_boot_ok": int(len(boots)), "boot": boots})
    return res


def p_det(F, area, b0, b1, b2):
    return 1 / (1 + np.exp(-(b0 + b1 * np.log10(F) - b2 * np.log10(area))))


def plot_detection_curve(sample: pd.DataFrame, fit: dict, cfg: dict, out) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.4), facecolor=SURFACE)
    _style(ax)
    ax.set_xscale("log")
    if fit.get("fitted"):
        F = np.logspace(np.log10(max(sample["frp_viirs_mw"].min(), 0.1)),
                        np.log10(sample["frp_viirs_mw"].max()), 200)
        bt = fit["boot"]
        for area, color, name in ((1.0, "#2a78d6", "nadir, A = 1 km²"),
                                  (fit["edge_area_km2"], "#eb6834", f"swath edge, A = {fit['edge_area_km2']} km²")):
            curves = np.array([p_det(F, area, *b) for b in bt])
            ax.fill_between(F, np.percentile(curves, 5, axis=0), np.percentile(curves, 95, axis=0),
                            color=color, alpha=0.18, linewidth=0)
            ax.plot(F, p_det(F, area, fit["b0"], fit["b1"], fit["b2"]), color=color, linewidth=2, label=name)
    # Binned observed detection rate (all pixel areas pooled), for reference.
    bins = np.logspace(np.log10(sample["frp_viirs_mw"].min()), np.log10(sample["frp_viirs_mw"].max()), 12)
    g = sample.groupby(pd.cut(sample["frp_viirs_mw"], bins), observed=True)["detected"].agg(["mean", "size"])
    mids = [np.sqrt(iv.left * iv.right) for iv in g.index]
    ax.scatter(mids, g["mean"], s=np.clip(g["size"], 8, 80), color=INK2, zorder=3,
               label="observed share (marker size = n)")
    ax.axhline(0.5, color=INK2, linewidth=0.8, linestyle=":")
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel("VIIRS event FRP at the overpass (MW, log scale)", color=INK2, fontsize=8.5)
    ax.set_ylabel("P(Aqua MODIS detects)", color=INK2, fontsize=8.5)
    ax.set_title(f"MODIS (Aqua) detection probability, n = {len(sample):,} VIIRS event-overpasses; "
                 f"bands = 90% bootstrap", color=INK, fontsize=9.5, loc="left")
    leg = ax.legend(fontsize=8, frameon=False, loc="lower right")
    for t in leg.get_texts():
        t.set_color(INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


# ------------------------------------------------- sync-window calibration ---
def deming(x, y, delta: float = 1.0):
    """Deming regression of y on x. delta = var(error in y) / var(error in x) (stated, not fitted).
    delta = 1 is orthogonal regression. Returns (intercept, slope)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    mx, my = x.mean(), y.mean()
    sxx, syy, sxy = ((x - mx) ** 2).mean(), ((y - my) ** 2).mean(), ((x - mx) * (y - my)).mean()
    b = (syy - delta * sxx + np.sqrt((syy - delta * sxx) ** 2 + 4 * delta * sxy ** 2)) / (2 * sxy)
    return float(my - b * mx), float(b)


def fit_sync(pairs: pd.DataFrame, cfg: dict) -> dict:
    """Calibration for a sync window (Part 2.3):
      - pairs with abs(dt) <= sync_max_dt_min (15 min),
      - truncation filter: both FRP >= trunc_frp_mw, so pairs are not selected by whether the
        coarser sensor could see the fire (a lower-truncated sample biases the slope),
      - Deming regression with the stated error-variance ratio,
      - slope bounds from OLS(y|x) and the inverse of OLS(x|y) (any errors-in-variables slope
        lies between them), and ODR for comparison,
      - bootstrap intervals."""
    c = cfg["calibration"]
    p = pairs[(pairs["dt_min"].abs() <= c["sync_max_dt_min"])
              & (pairs["frp_sum_mw_modis"] >= c["trunc_frp_mw"]) & (pairs["frp_sum_mw_viirs"] >= c["trunc_frp_mw"])]
    n = len(p)
    out = {"n_input": len(pairs), "n": n, "sync_max_dt_min": c["sync_max_dt_min"],
           "trunc_frp_mw": c["trunc_frp_mw"], "deming_delta": c["deming_error_ratio"]}
    if n < c["min_pairs"]:
        return {**out, "fitted": False, "reason": f"only {n} pairs after the 15-min and truncation filters"}
    x = np.log10(p["frp_sum_mw_modis"].to_numpy())
    y = np.log10(p["frp_sum_mw_viirs"].to_numpy())
    a, b = deming(x, y, c["deming_error_ratio"])
    b_ols = np.polyfit(x, y, 1)[0]
    b_inv = 1 / np.polyfit(y, x, 1)[0]
    a_odr, b_odr = _odr_fit(x, y)
    rng = np.random.default_rng(c["seed"])
    boot = np.array([deming(x[i], y[i], c["deming_error_ratio"])
                     for i in (rng.integers(0, n, n) for _ in range(c["bootstrap"]))])
    lo, hi = (1 - c["ci"]) / 2 * 100, (1 + c["ci"]) / 2 * 100
    return {**out, "fitted": True, "a": a, "b": b,
            "a_ci": [float(np.percentile(boot[:, 0], lo)), float(np.percentile(boot[:, 0], hi))],
            "b_ci": [float(np.percentile(boot[:, 1], lo)), float(np.percentile(boot[:, 1], hi))],
            "b_bounds_ols": sorted([float(b_ols), float(b_inv)]), "odr": {"a": float(a_odr), "b": float(b_odr)}}
