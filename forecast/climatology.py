"""Climatology baseline: P(at least one fire in a cell-week), Beta-smoothed.

For each cell and week, the training years give k "fire weeks" out of n looks, pooled over
weeks w-s..w+s (circular) to steady the estimate. A Beta prior shrinks cells with little
data towards the cell's own all-year fire-week rate:
    alpha = m * p_cell,  beta = m * (1 - p_cell)
    P = (k + alpha) / (n + alpha + beta)
m (prior strength) and s (week half-window) are parameters. No fire data is invented: with
fewer than history.min_years_forecast training years the function returns
{"status": "insufficient_history"}.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.calendar import insufficient, to_matrix


def fit(weekly: pd.DataFrame, cfg: dict, prior_strength: float = 10.0, half_window: int = 1) -> dict:
    bad = insufficient(weekly, cfg["history"]["min_years_forecast"], "forecast climatology")
    if bad:
        return bad
    M, cells, years = to_matrix(weekly)
    B = (M > 0).astype(float)                                     # fire week yes/no
    k = sum(np.roll(B, s, axis=2) for s in range(-half_window, half_window + 1)).sum(axis=1)
    n = (2 * half_window + 1) * B.shape[1]
    p_cell = B.mean(axis=(1, 2))[:, None]
    a, b = prior_strength * p_cell, prior_strength * (1 - p_cell)
    P = (k + a) / (n + a + b)
    return {"status": "ok", "cells": cells, "train_years": years, "prob": P,
            "params": {"prior_strength": prior_strength, "half_window": half_window}}


def predict(model: dict, weekly_target: pd.DataFrame) -> pd.DataFrame:
    """Probabilities and outcomes for target cell-weeks (cells unseen in training are dropped)."""
    ci = {c: i for i, c in enumerate(model["cells"])}
    t = weekly_target[weekly_target["cell_id"].isin(ci)].copy()
    t["p"] = model["prob"][t["cell_id"].map(ci).to_numpy(), t["week"].to_numpy() - 1]
    t["y"] = (t["value"] > 0).astype(int)
    return t


def complete(weekly: pd.DataFrame, cells, years) -> pd.DataFrame:
    """All cell-year-week combinations with zeros where nothing burned (needed for scoring)."""
    idx = pd.MultiIndex.from_product([cells, years, range(1, 53)], names=["cell_id", "year", "week"])
    return weekly.set_index(["cell_id", "year", "week"]).reindex(idx, fill_value=0).reset_index()
