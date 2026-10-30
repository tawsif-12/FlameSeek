"""Fire Past: find historical events that looked like the current one at the same age.

Each historical event is truncated to the current event's age before features
are computed, so similarity uses only what was knowable at that stage; its full
outcome (duration, expansion, FRP evolution, decay) is then reported. Distances
are Mahalanobis on standardized features with a shrinkage-regularized
covariance, and the K nearest events are returned.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import cos, log1p, pi, sin
from statistics import median
from typing import Any

import numpy as np

from events import _as_datetime, reconstruct_events
from geo import detections_extent_km2


FEATURES = ["doy_sin", "doy_cos", "log_detections", "log_total_frp", "log_max_frp", "log_extent_km2", "active_days", "frp_growth", "temp_max", "rh_min", "wind_max"]


def _truncate(detections: list[dict[str, Any]], age_hours: float) -> list[dict[str, Any]]:
    start = _as_datetime(detections[0]["acq_datetime"])
    cutoff = start + timedelta(hours=age_hours)
    return [d for d in detections if _as_datetime(d["acq_datetime"]) <= cutoff]


def _features(detections: list[dict[str, Any]], weather: dict[str, Any] | None) -> dict[str, float | None]:
    start = _as_datetime(detections[0]["acq_datetime"])
    frps = [float(d.get("frp") or 0) for d in detections]
    doy = start.timetuple().tm_yday
    half = len(frps) // 2
    early = sum(frps[:half]) or 0.1
    late = sum(frps[half:]) or 0.1
    return {
        "doy_sin": sin(2 * pi * doy / 365.25),
        "doy_cos": cos(2 * pi * doy / 365.25),
        "log_detections": log1p(len(detections)),
        "log_total_frp": log1p(sum(frps)),
        "log_max_frp": log1p(max(frps) if frps else 0),
        "log_extent_km2": log1p(detections_extent_km2(detections)),
        "active_days": float(len({_as_datetime(d["acq_datetime"]).date() for d in detections})),
        "frp_growth": float(np.clip(np.log(late / early), -3, 3)) if len(frps) >= 2 else 0.0,
        "temp_max": (weather or {}).get("temperature_2m_max"),
        "rh_min": (weather or {}).get("relative_humidity_2m_min"),
        "wind_max": (weather or {}).get("wind_speed_10m_max"),
    }


def _outcome(event: dict[str, Any], age_hours: float) -> dict[str, Any]:
    timeline = event["timeline"]
    start = _as_datetime(event["first_detection"])
    peak = max(timeline, key=lambda b: b["total_frp"]) if timeline else None
    truncated = _truncate(event["detections"], age_hours)
    ext_then = detections_extent_km2(truncated)
    ext_final = event["extent_km2"]
    peak_h = (datetime.fromisoformat(peak["window_start"]) - start).total_seconds() / 3600 if peak else None
    return {
        "duration_hours": event["duration_hours"],
        "total_detections": event["observation_count"],
        "final_extent_km2": ext_final,
        "extent_at_matched_age_km2": ext_then,
        "expanded_after_matched_age": ext_final >= 1.5 * max(ext_then, 0.1) and ext_final - ext_then >= 1.0,
        "peak_frp_window_hours_from_start": round(peak_h, 1) if peak_h is not None else None,
        "peak_window_frp": peak["total_frp"] if peak else None,
        "decay_began_hours_from_start": round(peak_h + 12, 1) if peak_h is not None and peak_h + 12 <= event["duration_hours"] else None,
        "frp_timeline": [{"hours": round((datetime.fromisoformat(b["window_start"]) - start).total_seconds() / 3600, 1), "frp": b["total_frp"]} for b in timeline],
        "remaining_hours_after_matched_age": round(max(0.0, event["duration_hours"] - age_hours), 1),
    }


def find_analogues(current: dict[str, Any], history: dict[str, Any], current_weather: dict[str, Any] | None, k: int = 5) -> dict[str, Any]:
    age = max(12.0, float(current["duration_hours"]))
    # Yearly windows are months apart, so events never link across years.
    rows_all = history["rows"]
    ref = max((_as_datetime(r["acq_datetime"]) for r in rows_all), default=datetime.now(timezone.utc)) + timedelta(days=1)
    hist_events = reconstruct_events(rows_all, reference_time=ref, min_detections=3) if rows_all else []

    if len(hist_events) < k + 2:
        return {
            "status": "insufficient_history",
            "candidates": len(hist_events),
            "analogues": [],
            "note": f"Only {len(hist_events)} historical events with 3+ detections were found in this region and season; analogue search needs at least {k + 2}.",
        }

    cur_feat = _features(current["detections"], current_weather)
    rows, metas = [], []
    for ev in hist_events:
        truncated = _truncate(ev["detections"], age)
        w = history["weather_by_date"].get(_as_datetime(ev["first_detection"]).date().isoformat())
        rows.append(_features(truncated, w))
        metas.append(ev)
    usable = [f for f in FEATURES if cur_feat.get(f) is not None and sum(1 for r in rows if r.get(f) is not None) >= 0.8 * len(rows)]
    X = np.array([[r.get(f) if r.get(f) is not None else np.nan for f in usable] for r in rows], dtype=float)
    col_mean = np.nanmean(X, axis=0)
    X = np.where(np.isnan(X), col_mean, X)
    x0 = np.array([cur_feat[f] for f in usable], dtype=float)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    z0 = (x0 - mu) / sd
    method = "mahalanobis_shrinkage"
    if len(Z) > len(usable) + 2:
        cov = np.cov(Z, rowvar=False)
        cov = 0.8 * cov + 0.2 * np.diag(np.diag(cov))
        inv = np.linalg.pinv(cov)
        diff = Z - z0
        dist = np.sqrt(np.einsum("ij,jk,ik->i", diff, inv, diff).clip(min=0))
    else:
        method = "euclidean_standardized"
        dist = np.linalg.norm(Z - z0, axis=1)
    order = np.argsort(dist)[:k]

    analogues = []
    for idx in order:
        ev = metas[idx]
        contrib = sorted(((usable[j], abs(float(Z[idx, j] - z0[j]))) for j in range(len(usable))), key=lambda t: t[1])
        analogues.append(
            {
                "event_id": ev["event_id"],
                "year": _as_datetime(ev["first_detection"]).year,
                "first_detection": ev["first_detection"].isoformat(),
                "centroid": ev["centroid"],
                "distance": round(float(dist[idx]), 3),
                "most_similar_on": [c[0] for c in contrib[:3]],
                "least_similar_on": [c[0] for c in contrib[-2:]],
                "features_at_matched_age": {f: round(float(v), 3) for f, v in zip(usable, X[idx])},
                "outcome": _outcome(ev, age),
                "sensors": ev["sensors"],
            }
        )
    durations = [a["outcome"]["duration_hours"] for a in analogues]
    remaining = [a["outcome"]["remaining_hours_after_matched_age"] for a in analogues]
    expanded = sum(1 for a in analogues if a["outcome"]["expanded_after_matched_age"])
    peaks = [a["outcome"]["peak_frp_window_hours_from_start"] for a in analogues if a["outcome"]["peak_frp_window_hours_from_start"] is not None]
    return {
        "status": "ok",
        "method": method,
        "matched_age_hours": round(age, 1),
        "features_used": usable,
        "current_features": {f: round(float(cur_feat[f]), 3) for f in usable},
        "candidates": len(hist_events),
        "analogues": analogues,
        "summary": {
            "median_total_duration_hours": round(median(durations), 1),
            "median_remaining_hours": round(median(remaining), 1),
            "expanded_after_this_age": f"{expanded} of {len(analogues)}",
            "median_peak_frp_hours_from_start": round(median(peaks), 1) if peaks else None,
            "typical_duration_range_hours": [round(min(durations), 1), round(max(durations), 1)],
        },
        "ecological_context": "Candidates come from the same ~60 km region and season, so they share ecological setting; land-cover similarity is not separately scored.",
        "caveat": "Historical analogues give context about how similar fires behaved. They do not mean the current fire will behave the same way.",
    }
