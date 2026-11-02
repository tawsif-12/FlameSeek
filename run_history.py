"""Run the multi-year components (calendar, anomalies, change point, forecast) on a window.

    python run_history.py --window current_2026

They need years of data. On a short window every component returns its status
("insufficient_history" / "requires_multi_year_data") and no numbers; nothing is filled in.
Writes <window outputs>/history_status.json.
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from forecast import climatology, xgb
from pipeline import anomalies, calendar
from pipeline.config import load_settings


def main(window=None) -> dict:
    cfg = load_settings(window=window)
    gd = pd.read_csv(cfg["paths"]["window_processed"] / "grid_daily.csv")
    weekly = calendar.weekly_from_grid(gd)
    annual = weekly.groupby("year")["value"].sum()
    res = {"window": cfg["window"]["name"], "years_in_window": sorted(int(y) for y in weekly["year"].unique()),
           "calendar": calendar.build_calendar(weekly, cfg),
           "anomalies": anomalies.detect(weekly, cfg),
           "changepoint": anomalies.pettitt(annual.to_numpy(), annual.index, cfg),
           "forecast_climatology": climatology.fit(weekly, cfg),
           "forecast_xgboost": xgb.train(weekly, cfg, list(annual.index))}
    status = {k: (v.get("status") if isinstance(v, dict) else v) for k, v in res.items()}
    detail = {k: {kk: vv for kk, vv in v.items() if kk in ("status", "what", "years_available", "years_required")}
              for k, v in res.items() if isinstance(v, dict)}
    out = cfg["paths"]["window_outputs"] / "history_status.json"
    out.write_text(json.dumps({"window": res["window"], "years_in_window": res["years_in_window"], **detail},
                              indent=2))
    print(json.dumps(detail, indent=2))
    return {"status": status, "detail": detail}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", default=None)
    main(ap.parse_args().window)
