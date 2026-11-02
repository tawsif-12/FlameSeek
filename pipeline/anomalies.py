"""Step 9: weekly anomalies with a negative-binomial baseline, and the Pettitt change test.

For each cell, year and week:
  1. Baseline = the same cell's values in weeks w-2..w+2 (circular) of all OTHER years
     (about 5 x (years-1) values; the evaluated year is left out).
  2. Method of moments: mean mu, variance v. If v > mu: negative binomial with
     k = mu^2 / (v - mu); else the Poisson limit.
  3. Tail probability P(X >= x) of the observed value x, converted to
     z_equiv = Phi^-1(1 - P(X >= x)).
  4. Anomaly when z_equiv >= z_min (2.0) and x >= min_events (3).
Values are treated as counts (rounded).

Pettitt test: non-parametric single change point in a series (e.g. annual totals),
K = max |U_t|, p ≈ 2 exp(-6 K^2 / (n^3 + n^2)).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from pipeline.calendar import insufficient, to_matrix


def tail_prob(x, mu, var):
    """P(X >= x) under NB (var > mu) or Poisson (var <= mu)."""
    x, mu, var = np.asarray(x, float), np.asarray(mu, float), np.asarray(var, float)
    p = np.ones_like(x)
    pos = mu > 0
    nb = pos & (var > mu)
    k = np.where(nb, mu ** 2 / np.maximum(var - mu, 1e-12), np.inf)
    xm1 = np.maximum(x - 1, -1)
    p[nb] = stats.nbinom.sf(xm1[nb], k[nb], k[nb] / (k[nb] + mu[nb]))
    po = pos & ~nb
    p[po] = stats.poisson.sf(xm1[po], mu[po])
    p[~pos] = np.where(x[~pos] > 0, 0.0, 1.0)  # zero baseline: any fire is a tail event
    return np.clip(p, 1e-300, 1.0)


def detect(weekly: pd.DataFrame, cfg: dict) -> dict:
    bad = insufficient(weekly, cfg["history"]["min_years_anomaly"], "anomalies")
    if bad:
        return bad
    ls = cfg["later_steps"]
    win, z_min, min_ev = ls["anomaly_baseline_window_weeks"], ls["anomaly_z_equiv_min"], ls["anomaly_min_events"]
    M, cells, years = to_matrix(weekly)
    M = np.rint(M)
    C, Y, W = M.shape
    # Pooled window sums per (cell, year, week): sum over weeks w-win..w+win.
    shifts = [np.roll(M, s, axis=2) for s in range(-win, win + 1)]
    S1 = sum(shifts)
    S2 = sum(s ** 2 for s in shifts)
    T1, T2 = S1.sum(axis=1, keepdims=True), S2.sum(axis=1, keepdims=True)
    n = (2 * win + 1) * (Y - 1)
    mu = (T1 - S1) / n                                      # leave the evaluated year out
    var = ((T2 - S2) - n * mu ** 2) / max(n - 1, 1)
    p = tail_prob(M, mu, var)
    z = stats.norm.ppf(1 - p)
    z = np.where(np.isfinite(z), z, 38.0)
    flag = (z >= z_min) & (M >= min_ev)
    ci, yi, wi = np.indices(M.shape)
    out = pd.DataFrame({"cell_id": np.array(cells)[ci.ravel()], "year": np.array(years)[yi.ravel()],
                        "week": wi.ravel() + 1, "value": M.ravel(), "baseline_mean": mu.ravel(),
                        "baseline_var": var.ravel(), "tail_prob": p.ravel(), "z_equiv": z.ravel(),
                        "anomaly_flag": flag.ravel()})
    return {"status": "ok", "table": out, "n_flags": int(flag.sum()), "n_cell_weeks": int(flag.size)}


def pettitt(series, years=None, cfg: dict | None = None) -> dict:
    x = np.asarray(series, float)
    n = len(x)
    if cfg is not None and n < cfg["history"]["min_years_changepoint"]:
        return {"status": "insufficient_history", "what": "changepoint", "years_available": n,
                "years_required": cfg["history"]["min_years_changepoint"]}
    sgn = np.sign(x[None, :] - x[:, None])          # sgn[i, j] = sign(x_j - x_i)
    U = np.array([sgn[:t + 1, t + 1:].sum() for t in range(n - 1)])
    t = int(np.abs(U).argmax())
    K = float(np.abs(U).max())
    p = float(min(1.0, 2 * np.exp(-6 * K ** 2 / (n ** 3 + n ** 2))))
    yrs = list(years) if years is not None else list(range(n))
    return {"status": "ok", "K": K, "p_value": p, "last_before_change": yrs[t], "first_after_change": yrs[t + 1],
            "mean_before": float(x[:t + 1].mean()), "mean_after": float(x[t + 1:].mean())}
