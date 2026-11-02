"""Synthetic weekly fire counts with known truth (15 years, many cells).

Per cell: a seasonal cycle (Gaussian bump around a known peak week, circular), negative-
binomial noise, a known step change (all cells x step_factor from step_year on), and a
number of planted anomalies (value = 4 x expected + 15) at known (cell, year, week).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def circ_dist(a, b, n=52):
    d = np.abs(np.asarray(a) - np.asarray(b)) % n
    return np.minimum(d, n - d)


def simulate(n_cells=30, years=range(2011, 2026), seed=7, step_year=2019, step_factor=1.6,
             n_anomalies=5, dispersion_k=5.0):
    rng = np.random.default_rng(seed)
    years = list(years)
    peak = rng.integers(1, 53, n_cells)
    amp = rng.uniform(6, 14, n_cells)
    width = rng.uniform(3, 5, n_cells)
    base = 0.3
    weeks = np.arange(1, 53)
    mu = base + amp[:, None] * np.exp(-0.5 * (circ_dist(weeks[None, :], peak[:, None]) / width[:, None]) ** 2)
    rows, expect = [], {}
    for ci in range(n_cells):
        for y in years:
            f = step_factor if y >= step_year else 1.0
            m = mu[ci] * f
            p = dispersion_k / (dispersion_k + m)
            vals = rng.negative_binomial(dispersion_k, p)
            for w, v in zip(weeks, vals):
                rows.append((f"c{ci:03d}", y, int(w), float(v)))
                expect[(f"c{ci:03d}", y, int(w))] = m[w - 1]
    df = pd.DataFrame(rows, columns=["cell_id", "year", "week", "value"])
    # Planted anomalies: distinct cells, mid-record years, weeks with some activity.
    anomalies = []
    cells = rng.choice(n_cells, n_anomalies, replace=False)
    for ci in cells:
        y = int(rng.choice(years[2:-2]))
        w = int((peak[ci] + rng.integers(-6, 7) - 1) % 52 + 1)
        key = (f"c{ci:03d}", y, w)
        val = float(round(4 * expect[key] + 15))
        df.loc[(df["cell_id"] == key[0]) & (df["year"] == y) & (df["week"] == w), "value"] = val
        anomalies.append(key)
    truth = {"peak_week": {f"c{i:03d}": int(peak[i]) for i in range(n_cells)}, "step_year": step_year,
             "step_factor": step_factor, "anomalies": anomalies}
    return df, truth
