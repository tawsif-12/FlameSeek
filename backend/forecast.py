"""Fire Future: where new satellite-observed burning activity may be detected next.

Target: for a ~3.3 km grid cell and horizon h in {6, 12, 24} h, will MODIS/VIIRS
detect fire in the cell during (t0, t0 + h]? This forecasts *satellite-observed
activity in the next valid observation windows*, not physical fire spread.

Training data: the same season in earlier years around the event (history.py),
sampled at every 6-hourly issue time with active fire nearby.

Models, all evaluated on the same holdouts:
- persistence baseline: burning cells keep burning (calibrated by frequency)
- seasonal baseline: historical detection frequency of the cell
- wind-only baseline: distance decay stretched downwind
- LightGBM on all features

LightGBM is used operationally only if it beats every baseline on Brier score in
both the temporal holdout (latest year) and the spatial holdout (east/west
split) without losing footprint skill. Otherwise the best baseline is used. With
too little history or no recent observation, the forecast is withheld.
"""

from __future__ import annotations

import asyncio
import time
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
from math import cos, pi, radians, sin
from typing import Any

import numpy as np

from environment import elevations, hourly_weather
from events import _as_datetime
from geo import KM_PER_DEG_LAT, km_per_deg_lon


CELL_DEG = 0.03
HORIZONS = [6, 12, 24]
ACTIVE_WINDOW_H = 24
CANDIDATE_RADIUS_KM = 15.0
NEAR_KM = 5.0
ISSUE_STEP_H = 6
NEGATIVE_KEEP = 0.35
MIN_TRAIN_POSITIVES = 40
MIN_TEST_POSITIVES = 10
FEATURE_NAMES = [
    "dist_nearest_active_km",
    "detections_5km_24h",
    "detections_5km_72h",
    "log_frp_5km_24h",
    "detections_in_cell_24h",
    "wind_alignment",
    "wind_speed_kmh",
    "downwind_push",
    "relative_humidity",
    "temperature_c",
    "seasonal_frequency",
    "elevation_diff_m",
    "issue_hour_sin",
    "issue_hour_cos",
]
_MODEL_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class Grid:
    def __init__(self, bbox: list[float]):
        self.west, self.south, self.east, self.north = bbox
        self.nx = int(np.ceil((self.east - self.west) / CELL_DEG))
        self.ny = int(np.ceil((self.north - self.south) / CELL_DEG))
        self.lat0 = (self.south + self.north) / 2
        self.kx = km_per_deg_lon(self.lat0)
        self.ky = KM_PER_DEG_LAT

    def cell(self, lat: float, lon: float) -> tuple[int, int] | None:
        i = int((lat - self.south) / CELL_DEG)
        j = int((lon - self.west) / CELL_DEG)
        return (i, j) if 0 <= i < self.ny and 0 <= j < self.nx else None

    def center(self, i: int, j: int) -> tuple[float, float]:
        return (self.south + (i + 0.5) * CELL_DEG, self.west + (j + 0.5) * CELL_DEG)

    def km(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        return np.stack([(lon - self.west) * self.kx, (lat - self.south) * self.ky], axis=-1)

    def neighbourhood(self, radius_km: float) -> list[tuple[int, int]]:
        ri = int(np.ceil(radius_km / (CELL_DEG * self.ky)))
        rj = int(np.ceil(radius_km / (CELL_DEG * self.kx)))
        return [(di, dj) for di in range(-ri, ri + 1) for dj in range(-rj, rj + 1) if (di * CELL_DEG * self.ky) ** 2 + (dj * CELL_DEG * self.kx) ** 2 <= radius_km**2]


class Detections:
    """Time-sorted detections with fast window queries."""

    def __init__(self, rows: list[dict[str, Any]], grid: Grid):
        rows = sorted(rows, key=lambda r: _as_datetime(r["acq_datetime"]))
        self.t = np.array([_as_datetime(r["acq_datetime"]).timestamp() for r in rows])
        self.lat = np.array([float(r["lat"]) for r in rows])
        self.lon = np.array([float(r["lon"]) for r in rows])
        self.frp = np.array([float(r.get("frp") or 0) for r in rows])
        self.xy = grid.km(self.lat, self.lon) if rows else np.zeros((0, 2))
        cells = [grid.cell(a, b) for a, b in zip(self.lat, self.lon)]
        self.ci = np.array([c[0] if c else -1 for c in cells])
        self.cj = np.array([c[1] if c else -1 for c in cells])
        self.ts_list = self.t.tolist()

    def window(self, t_from: float, t_to: float) -> slice:
        """Detections with t_from < t <= t_to."""
        return slice(bisect_right(self.ts_list, t_from), bisect_right(self.ts_list, t_to))


def _wind_at(hourly: dict[str, dict[str, Any]], t0: float, hours: int) -> tuple[float, float, float, float]:
    """Mean wind (vector average), RH and temperature over (t0, t0 + h]."""
    u = v = rh = temp = 0.0
    n = 0
    start = datetime.fromtimestamp(t0, tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    for k in range(1, hours + 1):
        row = hourly.get((start + timedelta(hours=k)).strftime("%Y-%m-%dT%H:00"))
        if not row or row.get("wind_speed_10m") is None or row.get("wind_direction_10m") is None:
            continue
        to_dir = radians((row["wind_direction_10m"] + 180) % 360)
        u += row["wind_speed_10m"] * sin(to_dir)
        v += row["wind_speed_10m"] * cos(to_dir)
        rh += row.get("relative_humidity_2m") or 0
        temp += row.get("temperature_2m") or 0
        n += 1
    if n == 0:
        return 0.0, 0.0, 50.0, 20.0
    u, v = u / n, v / n
    return float(np.hypot(u, v)), float(np.degrees(np.arctan2(u, v)) % 360), rh / n, temp / n


def _features_at(
    det: Detections,
    grid: Grid,
    t0: float,
    horizon: int,
    hourly: dict[str, dict[str, Any]],
    seasonal: np.ndarray,
    elev: np.ndarray,
    offsets: list[tuple[int, int]],
) -> tuple[list[tuple[int, int]], np.ndarray] | None:
    act = det.window(t0 - ACTIVE_WINDOW_H * 3600, t0)
    if act.stop - act.start == 0:
        return None
    act_ci, act_cj = det.ci[act], det.cj[act]
    cand = {(i + di, j + dj) for i, j in zip(act_ci, act_cj) if i >= 0 for di, dj in offsets}
    cand = [c for c in cand if 0 <= c[0] < grid.ny and 0 <= c[1] < grid.nx]
    if not cand:
        return None
    ci = np.array([c[0] for c in cand])
    cj = np.array([c[1] for c in cand])
    centers = np.stack([(cj + 0.5) * CELL_DEG * grid.kx, (ci + 0.5) * CELL_DEG * grid.ky], axis=-1)
    a_xy = det.xy[act]
    d = np.linalg.norm(centers[:, None, :] - a_xy[None, :, :], axis=-1)
    nearest_idx = d.argmin(axis=1)
    d_near = d[np.arange(len(cand)), nearest_idx]
    near = d <= NEAR_KM
    n24 = near.sum(axis=1)
    frp24 = np.log1p((near * det.frp[act][None, :]).sum(axis=1))
    w72 = det.window(t0 - 72 * 3600, t0)
    if w72.stop > w72.start:
        d72 = np.linalg.norm(centers[:, None, :] - det.xy[w72][None, :, :], axis=-1)
        n72 = (d72 <= NEAR_KM).sum(axis=1)
    else:
        n72 = np.zeros(len(cand))
    in_cell = np.zeros(len(cand))
    cell_index = {c: k for k, c in enumerate(cand)}
    for i, j in zip(act_ci, act_cj):
        k = cell_index.get((i, j))
        if k is not None:
            in_cell[k] += 1
    speed, to_dir, rh, temp = _wind_at(hourly, t0, horizon)
    vec = centers - a_xy[nearest_idx]
    bearing = np.degrees(np.arctan2(vec[:, 0], vec[:, 1])) % 360
    align = np.where(d_near > 0.3, np.cos(np.radians(bearing - to_dir)), 0.0)
    push = align * speed / (1 + d_near)
    src_i, src_j = act_ci[nearest_idx], act_cj[nearest_idx]
    elev_diff = elev[ci, cj] - elev[np.clip(src_i, 0, grid.ny - 1), np.clip(src_j, 0, grid.nx - 1)]
    hour = datetime.fromtimestamp(t0, tz=timezone.utc).hour
    X = np.column_stack(
        [
            d_near,
            n24,
            n72,
            frp24,
            in_cell,
            align,
            np.full(len(cand), speed),
            push,
            np.full(len(cand), rh),
            np.full(len(cand), temp),
            seasonal[ci, cj],
            np.nan_to_num(elev_diff),
            np.full(len(cand), sin(2 * pi * hour / 24)),
            np.full(len(cand), cos(2 * pi * hour / 24)),
        ]
    )
    return cand, X


def _labels(det: Detections, cand: list[tuple[int, int]], t0: float, horizon: int) -> np.ndarray:
    w = det.window(t0, t0 + horizon * 3600)
    hit = set(zip(det.ci[w].tolist(), det.cj[w].tolist()))
    return np.array([1 if c in hit else 0 for c in cand])


# --- Models -----------------------------------------------------------------------------------


class BinnedCalibrator:
    """Maps a score to the observed event frequency per quantile bin (fitted on training data only)."""

    def __init__(self, bins: int = 12):
        self.bins = bins

    def fit(self, score: np.ndarray, y: np.ndarray, w: np.ndarray) -> "BinnedCalibrator":
        qs = np.unique(np.quantile(score, np.linspace(0, 1, self.bins + 1)))
        self.edges = qs
        idx = np.clip(np.searchsorted(qs, score, side="right") - 1, 0, max(len(qs) - 2, 0))
        prior = float(np.average(y, weights=w))
        self.rates = np.array([(np.sum(w[idx == b] * y[idx == b]) + prior) / (np.sum(w[idx == b]) + 1) for b in range(max(len(qs) - 1, 1))])
        return self

    def predict(self, score: np.ndarray) -> np.ndarray:
        idx = np.clip(np.searchsorted(self.edges, score, side="right") - 1, 0, len(self.rates) - 1)
        return self.rates[idx]


def _baseline_scores(X: np.ndarray) -> dict[str, np.ndarray]:
    f = {name: X[:, k] for k, name in enumerate(FEATURE_NAMES)}
    return {
        "persistence": f["detections_in_cell_24h"] * 10 + f["detections_5km_24h"] / 10 - f["dist_nearest_active_km"] / 100,
        "seasonal": f["seasonal_frequency"],
        "wind_only": np.exp(-f["dist_nearest_active_km"] / 3.0) * (1 + f["wind_alignment"] * np.minimum(1.0, f["wind_speed_kmh"] / 20)),
    }


def _fit_models(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> dict[str, Any]:
    import lightgbm as lgb

    models: dict[str, Any] = {}
    for name, score in _baseline_scores(X).items():
        models[name] = BinnedCalibrator().fit(score, y, w)
    clf = lgb.LGBMClassifier(
        n_estimators=250,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=30,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        verbose=-1,
    )
    clf.fit(X, y, sample_weight=w)
    models["lightgbm"] = clf
    return models


def _predict(models: dict[str, Any], X: np.ndarray) -> dict[str, np.ndarray]:
    out = {name: models[name].predict(score) for name, score in _baseline_scores(X).items()}
    out["lightgbm"] = models["lightgbm"].predict_proba(X)[:, 1]
    return out


def _metrics(p: np.ndarray, y: np.ndarray, w: np.ndarray, groups: np.ndarray, threshold: float) -> dict[str, Any]:
    from sklearn.metrics import roc_auc_score

    brier = float(np.average((p - y) ** 2, weights=w))
    base = float(np.average(y, weights=w))
    brier_clim = float(np.average((base - y) ** 2, weights=w))
    pred = p >= threshold
    tp = float(np.sum(w * (pred & (y == 1))))
    fp = float(np.sum(w * (pred & (y == 0))))
    fn = float(np.sum(w * (~pred & (y == 1))))
    bins = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(p, bins) - 1, 0, 9)
    reliability = []
    ece = 0.0
    for b in range(10):
        m = idx == b
        if m.sum() == 0:
            continue
        wp, wy = float(np.average(p[m], weights=w[m])), float(np.average(y[m], weights=w[m]))
        reliability.append({"bin": f"{bins[b]:.1f}-{bins[b + 1]:.1f}", "mean_forecast": round(wp, 3), "observed_frequency": round(wy, 3), "n": int(m.sum())})
        ece += float(np.sum(w[m])) / float(np.sum(w)) * abs(wp - wy)
    footprint = []
    for g in np.unique(groups):
        m = groups == g
        inter = np.sum(pred[m] & (y[m] == 1))
        union = np.sum(pred[m] | (y[m] == 1))
        if union:
            footprint.append(inter / union)
    try:
        auc = float(roc_auc_score(y, p, sample_weight=w)) if 0 < y.sum() < len(y) else None
    except ValueError:
        auc = None
    return {
        "brier": round(brier, 5),
        "brier_skill_vs_climatology": round(1 - brier / brier_clim, 4) if brier_clim else None,
        "auc": round(auc, 4) if auc is not None else None,
        "probability_of_detection": round(tp / (tp + fn), 4) if tp + fn else None,
        "false_alarm_ratio": round(fp / (tp + fp), 4) if tp + fp else None,
        "critical_success_index": round(tp / (tp + fp + fn), 4) if tp + fp + fn else None,
        "footprint_iou_mean": round(float(np.mean(footprint)), 4) if footprint else None,
        "expected_calibration_error": round(ece, 4),
        "reliability": reliability,
        "threshold": round(threshold, 3),
        "positives": int(y.sum()),
        "samples": int(len(y)),
    }


def _best_threshold(p: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    best, best_t = -1.0, 0.5
    for t in np.linspace(0.05, 0.8, 16):
        pred = p >= t
        tp = np.sum(w * (pred & (y == 1)))
        denom = np.sum(w * (pred | (y == 1)))
        csi = tp / denom if denom else 0
        if csi > best:
            best, best_t = csi, float(t)
    return best_t


def _evaluate(split_name: str, X, y, w, groups, train_mask, test_mask) -> dict[str, Any]:
    if y[train_mask].sum() < MIN_TRAIN_POSITIVES or y[test_mask].sum() < MIN_TEST_POSITIVES:
        return {"split": split_name, "status": "insufficient", "train_positives": int(y[train_mask].sum()), "test_positives": int(y[test_mask].sum())}
    models = _fit_models(X[train_mask], y[train_mask], w[train_mask])
    train_pred = _predict(models, X[train_mask])
    test_pred = _predict(models, X[test_mask])
    results = {}
    for name in test_pred:
        thr = _best_threshold(train_pred[name], y[train_mask], w[train_mask])
        results[name] = _metrics(test_pred[name], y[test_mask], w[test_mask], groups[test_mask], thr)
    return {"split": split_name, "status": "ok", "models": results}


# --- Training set -----------------------------------------------------------------------------


async def _hourly_lookup(lat: float, lon: float, spans: list[tuple[datetime, datetime]]) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for a, b in spans:
        try:
            for row in await hourly_weather(lat, lon, a.date(), b.date()):
                table[row["time"]] = row
        except Exception:  # noqa: BLE001 - weather gaps degrade features, they do not stop the forecast
            continue
    return table


def _seasonal_grid(det: Detections, grid: Grid, exclude_year: int | None, n_years: int) -> np.ndarray:
    s = np.zeros((grid.ny, grid.nx))
    years = np.array([datetime.fromtimestamp(t, tz=timezone.utc).year for t in det.t]) if len(det.t) else np.array([])
    for k in range(len(det.t)):
        if det.ci[k] < 0 or (exclude_year is not None and years[k] == exclude_year):
            continue
        s[det.ci[k], det.cj[k]] += 1
    return s / max(1, n_years - (1 if exclude_year is not None else 0))


def _build_training(history: dict[str, Any], grid: Grid, hourly: dict[str, dict[str, Any]], elev: np.ndarray, horizon: int, rng: np.random.Generator):
    det = Detections(history["rows"], grid)
    offsets = grid.neighbourhood(CANDIDATE_RADIUS_KM)
    n_years = len(history["years"])
    seasonal_by_year = {y: _seasonal_grid(det, grid, y, n_years) for y in history["years"]}
    X_parts, y_parts, w_parts, g_parts, year_parts, lon_parts = [], [], [], [], [], []
    group = 0
    for year, info in history["per_year"].items():
        if info.get("status") != "ok":
            continue
        start = datetime.fromisoformat(info["start"]).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(info["end"]).replace(tzinfo=timezone.utc)
        t0 = start.timestamp() + ACTIVE_WINDOW_H * 3600
        while t0 + horizon * 3600 <= end.timestamp() + 86400:
            feats = _features_at(det, grid, t0, horizon, hourly, seasonal_by_year[year], elev, offsets)
            if feats is not None:
                cand, X = feats
                y = _labels(det, cand, t0, horizon)
                keep = (y == 1) | (rng.random(len(y)) < NEGATIVE_KEEP)
                if keep.any():
                    X_parts.append(X[keep])
                    y_parts.append(y[keep])
                    w_parts.append(np.where(y[keep] == 1, 1.0, 1 / NEGATIVE_KEEP))
                    g_parts.append(np.full(int(keep.sum()), group))
                    year_parts.append(np.full(int(keep.sum()), year))
                    lon_parts.append(np.array([grid.center(*c)[1] for c, k in zip(cand, keep) if k]))
                    group += 1
            t0 += ISSUE_STEP_H * 3600
    if not X_parts:
        return None
    return (np.vstack(X_parts), np.concatenate(y_parts), np.concatenate(w_parts), np.concatenate(g_parts), np.concatenate(year_parts), np.concatenate(lon_parts), group)


# --- Public entry point -----------------------------------------------------------------------


async def forecast_event(event: dict[str, Any], history: dict[str, Any], recent_rows: list[dict[str, Any]], observation_context: dict[str, Any], progress=None) -> dict[str, Any]:
    grid = Grid(history["bbox"])
    now = datetime.now(timezone.utc)
    latest = _as_datetime(event["latest_detection"])
    t0 = now.replace(minute=0, second=0, microsecond=0)
    base = {
        "target": "Probability that MODIS/VIIRS detect burning activity in each ~3.3 km cell during the next 6, 12 and 24 h of satellite observation.",
        "issue_time": t0.isoformat(),
        "cell_size_deg": CELL_DEG,
        "grid_bbox": history["bbox"],
        "caveat": "This is not a fire-spread prediction. It estimates where new satellite-observed activity may be detected, and a cell outside the corridor can still burn.",
        "inputs_used": ["recent detections (MODIS, VIIRS SNPP, VIIRS NOAA-20)", "historical same-season detections", "wind, humidity and temperature (Open-Meteo; ERA5 for training)", "terrain elevation (Copernicus DEM)", "hour of day"],
        "inputs_not_used": ["land cover (no free global raster API integrated)", "fuel moisture", "suppression activity"],
    }
    withheld_reasons = []
    hours_since = (now - latest).total_seconds() / 3600
    if hours_since > ACTIVE_WINDOW_H:
        withheld_reasons.append(f"The event's latest detection was {hours_since:.0f} h ago, so its current state is not observed.")
    cloud = observation_context.get("recent_cloud_cover_pct")
    if cloud is not None and cloud >= 85:
        withheld_reasons.append(f"Mean cloud cover over the last 24 h was {cloud:.0f}%, so recent observations are unreliable.")
    if history["failed_years"] > len(history["years"]) / 2:
        withheld_reasons.append("Most historical years could not be retrieved.")

    key = f"{round(event['centroid']['lat'], 1)}:{round(event['centroid']['lon'], 1)}:{t0.date().isoformat()}"
    cached = _MODEL_CACHE.get(key)
    if cached and time.time() - cached[0] < 6 * 3600:
        trained = cached[1]
    else:
        if progress:
            await progress("Fetching terrain elevation for the forecast grid", 0.05)
        centres = [grid.center(i, j) for i in range(grid.ny) for j in range(grid.nx)]
        elev_list = await elevations(centres)
        elev = np.array([e if e is not None else np.nan for e in elev_list]).reshape(grid.ny, grid.nx)
        elev = np.where(np.isnan(elev), np.nanmean(elev) if np.isfinite(np.nanmean(elev)) else 0.0, elev)
        if progress:
            await progress("Fetching hourly weather for training seasons", 0.15)
        spans = [(datetime.fromisoformat(i["start"]), datetime.fromisoformat(i["end"]) + timedelta(days=2)) for i in history["per_year"].values() if i.get("status") == "ok"]
        c = event["centroid"]
        hourly_hist = await _hourly_lookup(c["lat"], c["lon"], spans)
        hourly_now = await _hourly_lookup(c["lat"], c["lon"], [(now - timedelta(days=4), now + timedelta(days=2))])
        trained = {"elev": elev, "hourly_hist": hourly_hist, "hourly_now": hourly_now, "horizons": {}}
        rng = np.random.default_rng(42)
        for k, h in enumerate(HORIZONS):
            if progress:
                await progress(f"Training and validating {h} h models", 0.25 + 0.2 * k)
            data = await asyncio.to_thread(_build_training, history, grid, hourly_hist, elev, h, rng)
            if data is None:
                trained["horizons"][h] = {"status": "no_training_data"}
                continue
            X, y, w, groups, years, lons, n_groups = data
            latest_year = int(years.max())
            temporal = await asyncio.to_thread(_evaluate, "temporal holdout (latest season)", X, y, w, groups, years != latest_year, years == latest_year)
            median_lon = float(np.median(lons))
            spatial = await asyncio.to_thread(_evaluate, "spatial holdout (east of median longitude)", X, y, w, groups, lons < median_lon, lons >= median_lon)
            final_models = await asyncio.to_thread(_fit_models, X, y, w) if y.sum() >= MIN_TRAIN_POSITIVES else None
            thresholds = {}
            if final_models:
                preds = _predict(final_models, X)
                thresholds = {name: _best_threshold(p, y, w) for name, p in preds.items()}
            trained["horizons"][h] = {
                "status": "ok",
                "temporal": temporal,
                "spatial": spatial,
                "models": final_models,
                "thresholds": thresholds,
                "training": {"samples": int(len(y)), "positives": int(y.sum()), "issue_times": n_groups, "years": sorted({int(v) for v in years})},
                "feature_importance": dict(sorted(zip(FEATURE_NAMES, final_models["lightgbm"].booster_.feature_importance("gain").round(1).tolist()), key=lambda kv: -kv[1])) if final_models else {},
            }
        _MODEL_CACHE[key] = (time.time(), trained)

    live_grid_det = Detections(recent_rows, grid)
    seasonal_all = _seasonal_grid(Detections(history["rows"], grid), grid, None, len(history["years"]))
    offsets = grid.neighbourhood(CANDIDATE_RADIUS_KM)
    horizons_out = {}
    for h in HORIZONS:
        info = trained["horizons"].get(h, {})
        out: dict[str, Any] = {"horizon_hours": h, "valid_from": t0.isoformat(), "valid_to": (t0 + timedelta(hours=h)).isoformat()}
        reasons = list(withheld_reasons)
        if info.get("status") != "ok" or not info.get("models"):
            reasons.append("Not enough historical detections in this region and season to train and validate a forecast.")
        temporal, spatial = info.get("temporal", {}), info.get("spatial", {})
        if temporal.get("status") != "ok":
            reasons.append("The temporal holdout lacks enough positive cases to validate any model.")
        out["validation"] = {"temporal": temporal, "spatial": spatial}
        out["training"] = info.get("training")
        out["feature_importance"] = info.get("feature_importance")
        if reasons:
            horizons_out[h] = {**out, "status": "FORECAST WITHHELD", "reasons": reasons, "cells": []}
            continue

        chosen, why = _select_model(temporal, spatial)
        feats = _features_at(live_grid_det, grid, t0.timestamp(), h, trained["hourly_now"], seasonal_all, trained["elev"], offsets)
        if feats is None:
            horizons_out[h] = {**out, "status": "FORECAST WITHHELD", "reasons": ["No detection of this event in the last 24 h in the forecast domain."], "cells": []}
            continue
        cand, X = feats
        p = _predict(info["models"], X)[chosen]
        cells = []
        for (i, j), prob in zip(cand, p):
            if prob >= 0.05:
                lat, lon = grid.center(i, j)
                cells.append({"lat": round(lat, 4), "lon": round(lon, 4), "p": round(float(prob), 3), "level": "high" if prob >= 0.6 else "moderate" if prob >= 0.3 else "low"})
        cells.sort(key=lambda c: -c["p"])
        horizons_out[h] = {
            **out,
            "status": "ISSUED",
            "model_used": chosen,
            "model_selection": why,
            "decision_threshold": round(info["thresholds"].get(chosen, 0.5), 3),
            "cells": cells,
            "corridor_area_km2": round(sum(1 for c in cells if c["p"] >= 0.1) * (CELL_DEG * grid.kx) * (CELL_DEG * grid.ky), 1),
            "wind": dict(zip(["mean_speed_kmh", "blowing_toward_deg", "mean_rh_pct", "mean_temp_c"], [round(v, 1) for v in _wind_at(trained["hourly_now"], t0.timestamp(), h)])),
        }
    return {**base, "horizons": horizons_out, "withheld_reasons_global": withheld_reasons}


def _select_model(temporal: dict[str, Any], spatial: dict[str, Any]) -> tuple[str, str]:
    chosen, why = _choose(temporal, spatial)
    bss = temporal["models"][chosen].get("brier_skill_vs_climatology")
    if bss is not None and bss < 0:
        why += f" Caution: in the latest-season holdout its Brier score is worse than a constant base-rate forecast (skill {bss}), so the corridor shape is more reliable than the exact probabilities."
    return chosen, why


def _choose(temporal: dict[str, Any], spatial: dict[str, Any]) -> tuple[str, str]:
    tm = temporal["models"]
    baselines = ["persistence", "seasonal", "wind_only"]
    best_base = min(baselines, key=lambda n: tm[n]["brier"])
    ml_better_temporal = tm["lightgbm"]["brier"] < min(tm[b]["brier"] for b in baselines)
    ml_footprint_ok = (tm["lightgbm"]["critical_success_index"] or 0) >= (tm[best_base]["critical_success_index"] or 0) - 0.02
    ml_better_spatial = True
    if spatial.get("status") == "ok":
        sm = spatial["models"]
        ml_better_spatial = sm["lightgbm"]["brier"] < min(sm[b]["brier"] for b in baselines)
    if ml_better_temporal and ml_better_spatial and ml_footprint_ok:
        return "lightgbm", f"LightGBM beat all baselines on Brier score in the temporal holdout ({tm['lightgbm']['brier']} vs best baseline {tm[best_base]['brier']}){' and the spatial holdout' if spatial.get('status') == 'ok' else ''}, without losing footprint skill."
    failed = []
    if not ml_better_temporal:
        failed.append("temporal-holdout Brier")
    if not ml_better_spatial:
        failed.append("spatial-holdout Brier")
    if not ml_footprint_ok:
        failed.append("footprint CSI")
    return best_base, f"LightGBM did not beat the baselines on {', '.join(failed)}, so the best baseline ({best_base.replace('_', '-')}, temporal Brier {tm[best_base]['brier']}) is used."
