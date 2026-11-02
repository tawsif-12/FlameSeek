"""XGBoost fire-occurrence model. STATUS: requires multi-year data.

Written and wired, but it is only trained when the input spans at least
history.min_years_forecast years and xgboost is installed. Otherwise it returns a status
and no model; no numbers are produced from short records.

Features (per cell-week): climatology probability, previous week's fire count, cell latitude,
week of year (sin/cos). Target: fire week yes/no. Split by year (train on earlier years,
evaluate on later years) to avoid leakage between neighbouring weeks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.calendar import n_years


def features(weekly_full: pd.DataFrame, clim_prob: pd.DataFrame) -> pd.DataFrame:
    f = weekly_full.sort_values(["cell_id", "year", "week"]).copy()
    f["prev_week_count"] = f.groupby("cell_id")["value"].shift(1).fillna(0)
    f["week_sin"] = np.sin(2 * np.pi * f["week"] / 52)
    f["week_cos"] = np.cos(2 * np.pi * f["week"] / 52)
    f = f.merge(clim_prob, on=["cell_id", "week"], how="left")
    f["y"] = (f["value"] > 0).astype(int)
    return f


def train(feat: pd.DataFrame, cfg: dict, train_years: list[int]) -> dict:
    need = cfg["history"]["min_years_forecast"]
    if n_years(feat) < need:
        return {"status": "requires_multi_year_data", "years_available": n_years(feat), "years_required": need}
    try:
        import xgboost as xgb
    except ImportError:
        return {"status": "xgboost_not_installed",
                "note": "pip install xgboost in the flameseek env, then rerun"}
    cols = ["clim_p", "prev_week_count", "week_sin", "week_cos"]
    tr = feat[feat["year"].isin(train_years)]
    model = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8,
                              eval_metric="logloss")
    model.fit(tr[cols], tr["y"])
    return {"status": "ok", "model": model, "features": cols}
