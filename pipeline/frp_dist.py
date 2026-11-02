"""Step 6E: FRP distribution of VIIRS events and the share of fires MODIS can see.

Data: VIIRS event FRP per overpass (summed within one overpass, never across).
For day and night separately:
  - F_min by the Clauset KS method: the candidate x_min with the smallest
    Kolmogorov-Smirnov distance D between data and fitted power law. Candidates
    are log-spaced between the 1st and 99th percentile, so the search stays fast
    on ~10^5 values (decisions.md).
  - alpha by maximum likelihood (powerlaw package).
  - power law vs lognormal above F_min by normalised log-likelihood ratio R and p.
pi_MODIS = ∫ P_det(F, A) f(F) dF is evaluated two ways:
  - "empirical": the mean of P_det over all VIIRS event-overpass FRP values (no tail model);
  - "power-law tail": f = fitted power law above F_min (the procedure's formula).
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import integrate  # noqa: E402

from pipeline.calibration import p_det  # noqa: E402
from pipeline.figures import INK, INK2, SURFACE, _style  # noqa: E402


def fit_one(frp: np.ndarray, n_candidates: int) -> dict:
    import powerlaw
    x = np.asarray(frp, float)
    x = x[np.isfinite(x) & (x > 0)]
    if len(x) < 50:
        return {"n": len(x), "fitted": False, "reason": "fewer than 50 values"}
    cands = np.unique(np.quantile(x, np.linspace(0.01, 0.99, n_candidates)))
    Ds = []
    for xm in cands:
        if (x >= xm).sum() < 50:
            Ds.append(np.inf)
            continue
        f = powerlaw.Fit(x, xmin=float(xm), verbose=False)
        Ds.append(f.power_law.D)
    best = float(cands[int(np.argmin(Ds))])
    fit = powerlaw.Fit(x, xmin=best, verbose=False)
    R, p = fit.distribution_compare("power_law", "lognormal", normalized_ratio=True)
    n_tail = int((x >= best).sum())
    return {"n": len(x), "fitted": True, "fit": fit, "xmin": best, "alpha": float(fit.power_law.alpha),
            "alpha_se": float(fit.power_law.sigma), "D": float(fit.power_law.D), "n_tail": n_tail,
            "tail_share": n_tail / len(x), "R": float(R), "p": float(p),
            "lognormal_mu": float(fit.lognormal.mu), "lognormal_sigma": float(fit.lognormal.sigma),
            "better": ("power law" if R > 0 else "lognormal") if p < 0.1 else "inconclusive (p >= 0.1)"}


def pi_modis(frp: np.ndarray, res: dict, curve: dict, areas: dict) -> dict:
    out = {}
    if not curve.get("fitted"):
        return {"reason": "detection curve not fitted"}
    b = (curve["b0"], curve["b1"], curve["b2"])
    for name, A in areas.items():
        out[f"empirical_{name}"] = float(np.mean(p_det(frp[frp > 0], A, *b)))
        if res.get("fitted"):
            a, xm = res["alpha"], res["xmin"]
            pdf = lambda F: (a - 1) / xm * (F / xm) ** (-a)  # noqa: E731
            val, _ = integrate.quad(lambda F: p_det(F, A, *b) * pdf(F), xm, np.inf, limit=200)
            out[f"powerlaw_tail_{name}"] = float(val)
    return out


def plot(results: dict, out) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), facecolor=SURFACE)
    for ax, (label, r) in zip(axes, results.items()):
        _style(ax)
        if not r.get("fitted"):
            ax.text(0.5, 0.5, f"{label}: not fitted ({r.get('reason')})", transform=ax.transAxes,
                    ha="center", color=INK2)
            continue
        f = r["fit"]
        f.plot_ccdf(ax=ax, color=INK2, linewidth=0, marker=".", markersize=2, label="VIIRS data (above F_min)")
        f.power_law.plot_ccdf(ax=ax, color="#2a78d6", linewidth=2, label=f"power law, α = {r['alpha']:.2f}")
        f.lognormal.plot_ccdf(ax=ax, color="#eb6834", linewidth=2, linestyle="--", label="lognormal")
        ax.set_title(f"{label}: n = {r['n']:,}, F_min = {r['xmin']:.1f} MW ({r['tail_share']:.0%} of "
                     f"events above); R = {r['R']:.2f}, p = {r['p']:.3f}", color=INK, fontsize=9, loc="left")
        ax.set_xlabel("Event FRP per overpass (MW)", color=INK2, fontsize=8.5)
        ax.set_ylabel("P(FRP ≥ x | FRP ≥ F_min)", color=INK2, fontsize=8.5)
        leg = ax.legend(fontsize=8, frameon=False)
        for t in leg.get_texts():
            t.set_color(INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def run(ov: pd.DataFrame, curve: dict, cfg: dict) -> dict:
    v = ov[(ov["sensor"] == "VIIRS") & (ov["frp_sum_mw"] > 0)]
    n_c = cfg["calibration"]["frp_dist_xmin_candidates"]
    results = {name: fit_one(v.loc[v["daynight"] == dn, "frp_sum_mw"].to_numpy(), n_c)
               for dn, name in (("D", "day"), ("N", "night"))}
    areas = {"nadir": 1.0, "edge": cfg["calibration"]["modis_edge_area_km2"]}
    pis = {name: pi_modis(v.loc[v["daynight"] == dn, "frp_sum_mw"].to_numpy(), results[name], curve, areas)
           for dn, name in (("D", "day"), ("N", "night"))}
    pis["all"] = pi_modis(v["frp_sum_mw"].to_numpy(), {}, curve, areas)
    for k, r in results.items():
        if r.get("fitted"):
            print(f"[Step 6E] {k}: n={r['n']:,} F_min={r['xmin']:.2f} MW alpha={r['alpha']:.3f} "
                  f"R={r['R']:.2f} p={r['p']:.3g} -> {r['better']}")
    return {"fits": results, "pi": pis}
