"""Step 9: burning calendar, seasonal peak week and season onset.

Input: weekly values per cell and year, columns [cell_id, year, week (1-52), value]. The value
is whatever activity measure is available (lambda_hat once Step 8 exists; harmonized event
counts until then).

  climatology  mean value per cell and week over all years
  peak_week    week with the highest climatology after a circular ±1-week running mean
  onset_week   per cell and year: first week whose cumulative value reaches
               onset_share (20%) of that year's total
  onset_trend  Theil–Sen slope of onset_week over years (weeks per year)

With fewer than history.min_years_calendar years every function returns
{"status": "insufficient_history"} and no numbers.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def n_years(weekly: pd.DataFrame) -> int:
    return int(weekly["year"].nunique()) if len(weekly) else 0


def insufficient(weekly: pd.DataFrame, min_years: int, what: str) -> dict | None:
    n = n_years(weekly)
    if n < min_years:
        return {"status": "insufficient_history", "what": what, "years_available": n, "years_required": min_years}
    return None


def to_matrix(weekly: pd.DataFrame) -> tuple[np.ndarray, list, list]:
    """Array [cell, year, week] (weeks 1-52), missing filled with 0."""
    cells = sorted(weekly["cell_id"].unique())
    years = sorted(weekly["year"].unique())
    ci = {c: i for i, c in enumerate(cells)}
    yi = {y: i for i, y in enumerate(years)}
    M = np.zeros((len(cells), len(years), 52))
    w = weekly[(weekly["week"] >= 1) & (weekly["week"] <= 52)]
    M[w["cell_id"].map(ci).to_numpy(), w["year"].map(yi).to_numpy(), w["week"].to_numpy() - 1] = w["value"].to_numpy()
    return M, cells, years


def build_calendar(weekly: pd.DataFrame, cfg: dict) -> dict:
    bad = insufficient(weekly, cfg["history"]["min_years_calendar"], "calendar")
    if bad:
        return bad
    share = cfg["later_steps"]["season_onset_share"]
    M, cells, years = to_matrix(weekly)
    clim = M.mean(axis=1)                                   # [cell, week]
    smooth = (np.roll(clim, 1, axis=1) + clim + np.roll(clim, -1, axis=1)) / 3
    peak = smooth.argmax(axis=1) + 1
    tot = M.sum(axis=2, keepdims=True)
    frac = np.divide(np.cumsum(M, axis=2), tot, out=np.zeros_like(M), where=tot > 0)
    onset = np.where(tot[..., 0] > 0, (frac >= share).argmax(axis=2) + 1, 0).astype(float)
    onset[tot[..., 0] == 0] = np.nan
    onset_df = pd.DataFrame([{"cell_id": c, "year": y, "onset_week": onset[i, j]}
                             for i, c in enumerate(cells) for j, y in enumerate(years)])
    trend = []
    for i, c in enumerate(cells):
        ok = np.isfinite(onset[i])
        slope = theil_sen(np.array(years)[ok], onset[i][ok]) if ok.sum() >= 3 else np.nan
        trend.append({"cell_id": c, "onset_trend_weeks_per_year": slope, "n_years": int(ok.sum())})
    clim_df = pd.DataFrame({"cell_id": np.repeat(cells, 52), "week": np.tile(np.arange(1, 53), len(cells)),
                            "climatology": clim.ravel()})
    return {"status": "ok", "years": years, "climatology": clim_df,
            "peak": pd.DataFrame({"cell_id": cells, "peak_week": peak}), "onset": onset_df,
            "onset_trend": pd.DataFrame(trend)}


def theil_sen(x, y) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    i, j = np.triu_indices(len(x), k=1)
    dx = x[j] - x[i]
    ok = dx != 0
    return float(np.median((y[j] - y[i])[ok] / dx[ok])) if ok.any() else np.nan


def weekly_from_grid(grid_daily: pd.DataFrame, value_col: str = "n_events_weighted") -> pd.DataFrame:
    """Weekly sums per cell from a grid_daily table (partial days excluded)."""
    g = grid_daily
    if "partial_day" in g:
        g = g[~g["partial_day"].astype(bool)]
    d = pd.to_datetime(g["date"])
    iso = d.dt.isocalendar()
    w = pd.DataFrame({"cell_id": g["cell_id"], "year": iso["year"].astype(int),
                      "week": iso["week"].clip(upper=52).astype(int), "value": g[value_col].fillna(0)})
    return w.groupby(["cell_id", "year", "week"], as_index=False)["value"].sum()
