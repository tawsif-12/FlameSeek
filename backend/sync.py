"""Sensor synchronization: spatial, radiometric/count and temporal harmonization.

Converts raw MODIS/VIIRS/Himawari detections from any year into one unit,
"harmonized fire activity in grid cell c during week w", with uncertainty.

  1. Spatial   - footprint-aware clustering and area-overlap regridding to the 0.1 deg grid.
  2. Radiometric/count - MODIS -> VIIRS-equivalent FRP (Deming regression per biome), count
     ratios per biome/season, and a detection-probability model for sub-detection fires.
  3. Temporal  - Himawari-derived Gaussian diurnal shape turns any overpass FRP into daily energy.
  4. Output    - one cell-week record per cell (see build_cell_week_records).

Everything here is pure computation on dicts/arrays; no network or disk access.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import exp, log, sqrt
from typing import Any, Iterable, Sequence

import numpy as np
from scipy.optimize import curve_fit
from scipy.spatial import cKDTree
from sklearn.linear_model import LogisticRegression

from geo import KM_PER_DEG_LAT, footprint_cell_fractions, km_per_deg_lon, pixel_size_km


CALENDAR_GRID_RES = 0.1
TIME_WINDOW_MIN = 30.0


# --- Step 1: spatial sync ------------------------------------------------------------


def footprint_area_km2(row: dict[str, Any]) -> float:
    scan, track = pixel_size_km(row)
    return scan * track


def _acq_minutes(row: dict[str, Any]) -> float:
    dt = row["acq_datetime"]
    return dt.timestamp() / 60.0


def cluster_events(rows: Sequence[dict[str, Any]], eps_factor: float = 1.5, time_window_min: float = TIME_WINDOW_MIN) -> list[list[dict[str, Any]]]:
    """ST-DBSCAN-style clustering run per sensor, so each sensor is clustered on its own.

    Detections are neighbours only if they are also within time_window_min of each other,
    which keeps separate overpasses apart.

    The spatial threshold scales with the footprint: two pixels are neighbours when their
    centres are within eps_factor * the larger pixel's diagonal, so edge-of-swath MODIS pixels
    are not split and nadir VIIRS pixels are not over-merged. min_samples is 1, i.e. every
    detection belongs to a cluster (single-linkage components).
    """
    by_sensor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_sensor[str(row.get("sensor", ""))].append(row)
    clusters: list[list[dict[str, Any]]] = []
    for sensor_rows in by_sensor.values():
        clusters.extend(_cluster_one_sensor(sensor_rows, eps_factor, time_window_min))
    return clusters


def _cluster_one_sensor(rows: list[dict[str, Any]], eps_factor: float, time_window_min: float) -> list[list[dict[str, Any]]]:
    n = len(rows)
    lat0 = float(np.mean([float(r["lat"]) for r in rows]))
    kx = km_per_deg_lon(lat0)
    pts = np.array([[float(r["lon"]) * kx, float(r["lat"]) * KM_PER_DEG_LAT] for r in rows])
    times = np.array([_acq_minutes(r) for r in rows])
    diag = np.array([sqrt(sum(s * s for s in pixel_size_km(r))) for r in rows])

    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    tree = cKDTree(pts)
    # Query with the largest possible radius, then apply the pairwise footprint-scaled threshold.
    for i, j in tree.query_pairs(float(diag.max()) * eps_factor):
        if abs(times[i] - times[j]) > time_window_min:
            continue
        if np.hypot(*(pts[i] - pts[j])) <= eps_factor * max(diag[i], diag[j]):
            parent[find(i)] = find(j)
    comps: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i, row in enumerate(rows):
        comps[find(i)].append(row)
    return list(comps.values())


def cluster_centroid(cluster: Sequence[dict[str, Any]]) -> tuple[float, float]:
    weights = np.array([max(float(r.get("frp") or 0.0), 1e-6) for r in cluster])
    lat = float(np.average([float(r["lat"]) for r in cluster], weights=weights))
    lon = float(np.average([float(r["lon"]) for r in cluster], weights=weights))
    return lat, lon


def snap_cell(lat: float, lon: float, res: float = CALENDAR_GRID_RES) -> tuple[float, float]:
    return round(round(lat / res) * res, 6), round(round(lon / res) * res, 6)


def allocate_to_grid(rows: Iterable[dict[str, Any]], res: float = CALENDAR_GRID_RES) -> dict[tuple[float, float], dict[str, float]]:
    """Area-overlap allocation w_ic = Area(F_i & C_c) / Area(F_i).

    FRP is additive (sum of w_ic * FRP_i, energy conserved). Brightness temperature is not
    additive, so it is the weight-averaged value per cell, and its max is kept alongside.
    """
    cells: dict[tuple[float, float], dict[str, float]] = defaultdict(lambda: {"frp": 0.0, "weight": 0.0, "bt_sum": 0.0, "bt_max": float("-inf")})
    for row in rows:
        frp = float(row.get("frp") or 0.0)
        bt = row.get("brightness")
        for cell_lat, cell_lon, w in footprint_cell_fractions(row, res):
            c = cells[(cell_lat, cell_lon)]
            c["frp"] += w * frp
            c["weight"] += w
            if bt is not None:
                c["bt_sum"] += w * float(bt)
                c["bt_max"] = max(c["bt_max"], float(bt))
    out = {}
    for key, c in cells.items():
        out[key] = {
            "frp": c["frp"],
            "brightness_mean": c["bt_sum"] / c["weight"] if c["weight"] and c["bt_max"] > float("-inf") else float("nan"),
            "brightness_max": c["bt_max"] if c["bt_max"] > float("-inf") else float("nan"),
        }
    return out


def cell_event_counts(clusters: Iterable[Sequence[dict[str, Any]]], res: float = CALENDAR_GRID_RES) -> dict[tuple[float, float], int]:
    """Event count per cell = clusters whose centroid falls in the cell, not pixels."""
    counts: dict[tuple[float, float], int] = defaultdict(int)
    for cluster in clusters:
        counts[snap_cell(*cluster_centroid(cluster), res)] += 1
    return dict(counts)


# --- Step 2: radiometric and count sync ----------------------------------------------


@dataclass(frozen=True)
class FrpCalibration:
    """log(FRP_VIIRS) = a + b * log(FRP_MODIS), with parameter standard errors and residual sd."""

    a: float
    b: float
    a_se: float
    b_se: float
    resid_sd: float
    n: int

    def predict(self, frp_modis: float) -> tuple[float, float]:
        """VIIRS-equivalent FRP and a 1-sigma multiplicative-uncertainty (log-space sd) for one value."""
        x = log(max(frp_modis, 1e-6))
        var = self.a_se**2 + (x * self.b_se) ** 2 + self.resid_sd**2
        return exp(self.a + self.b * x), sqrt(var)


def deming_regression(x: np.ndarray, y: np.ndarray, delta: float = 1.0) -> tuple[float, float]:
    """Deming regression (errors in both variables). delta = var(err_y) / var(err_x); 1 = orthogonal."""
    mx, my = x.mean(), y.mean()
    sxx = ((x - mx) ** 2).mean()
    syy = ((y - my) ** 2).mean()
    sxy = ((x - mx) * (y - my)).mean()
    if sxy == 0:
        raise ValueError("x and y are uncorrelated; regression slope is undefined")
    slope = (syy - delta * sxx + sqrt((syy - delta * sxx) ** 2 + 4 * delta * sxy**2)) / (2 * sxy)
    return my - slope * mx, slope


def fit_frp_calibration(frp_modis: Sequence[float], frp_viirs: Sequence[float], n_boot: int = 200, seed: int = 0) -> FrpCalibration:
    """Fit one biome's MODIS->VIIRS FRP conversion on matched cluster pairs (log space).

    Standard errors come from a bootstrap, which also covers the Deming slope.
    """
    x = np.log(np.maximum(np.asarray(frp_modis, dtype=float), 1e-6))
    y = np.log(np.maximum(np.asarray(frp_viirs, dtype=float), 1e-6))
    if len(x) < 10:
        raise ValueError("need at least 10 matched pairs to calibrate")
    a, b = deming_regression(x, y)
    resid_sd = float(np.std(y - (a + b * x), ddof=2))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(x), len(x))
        try:
            boots.append(deming_regression(x[idx], y[idx]))
        except ValueError:
            continue
    arr = np.array(boots)
    return FrpCalibration(a=a, b=b, a_se=float(arr[:, 0].std()), b_se=float(arr[:, 1].std()), resid_sd=resid_sd, n=len(x))


def match_overpasses(modis: Sequence[dict[str, Any]], viirs: Sequence[dict[str, Any]], max_dt_min: float = 30.0, max_km: float | None = None) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Pair MODIS and VIIRS clusters seen within max_dt_min of each other over the same place.

    Each cluster is a list of rows; the spatial threshold defaults to the MODIS pixel diagonal.
    Nearest-in-space wins and every cluster is used at most once.
    """
    if not modis or not viirs:
        return []
    mc = [cluster_centroid(c) for c in modis]
    vc = [cluster_centroid(c) for c in viirs]
    lat0 = float(np.mean([p[0] for p in mc]))
    kx = km_per_deg_lon(lat0)
    tree = cKDTree(np.array([[p[1] * kx, p[0] * KM_PER_DEG_LAT] for p in vc]))
    vt = [np.mean([_acq_minutes(r) for r in c]) for c in viirs]
    pairs, used = [], set()
    for i, c in enumerate(modis):
        radius = max_km if max_km is not None else 1.5 * max(sqrt(sum(s * s for s in pixel_size_km(r))) for r in c)
        mt = np.mean([_acq_minutes(r) for r in c])
        cand = tree.query_ball_point([mc[i][1] * kx, mc[i][0] * KM_PER_DEG_LAT], radius)
        cand = [j for j in cand if j not in used and abs(vt[j] - mt) <= max_dt_min]
        if not cand:
            continue
        j = min(cand, key=lambda j: np.hypot(vc[j][1] * kx - mc[i][1] * kx, vc[j][0] * KM_PER_DEG_LAT - mc[i][0] * KM_PER_DEG_LAT))
        used.add(j)
        pairs.append((c, viirs[j]))
    return pairs


@dataclass(frozen=True)
class CountRatio:
    """N_VIIRS / N_MODIS for one biome and season: Poisson MLE with a Wald interval on log ratio."""

    ratio: float
    log_se: float
    n_modis: int
    n_viirs: int

    def scale(self, n_modis: float) -> tuple[float, float]:
        """VIIRS-equivalent count and 1-sigma log-space uncertainty."""
        return n_modis * self.ratio, self.log_se


def fit_count_ratio(n_modis: Sequence[int], n_viirs: Sequence[int]) -> CountRatio:
    """Poisson GLM log(E[N_V]) = log(N_M) + c has closed form ratio = sum(N_V)/sum(N_M).

    Counts are summed over matched overlap-era cell-weeks for one (biome, season).
    """
    m, v = int(np.sum(n_modis)), int(np.sum(n_viirs))
    if m == 0:
        raise ValueError("MODIS saw no fires in this stratum; use the detection-probability model instead")
    se = sqrt(1.0 / max(v, 1) + 1.0 / m) if v else float("inf")
    return CountRatio(ratio=v / m, log_se=se, n_modis=m, n_viirs=v)


@dataclass(frozen=True)
class DetectionModel:
    """P(MODIS detects | FRP, A) = sigmoid(b0 + b1 log FRP - b2 log A)."""

    b0: float
    b1: float
    b2: float

    def probability(self, frp: float, area_km2: float) -> float:
        z = self.b0 + self.b1 * log(max(frp, 1e-6)) - self.b2 * log(max(area_km2, 1e-6))
        return 1.0 / (1.0 + exp(-z))

    def inflate(self, observed_count: float, frp: float, area_km2: float, p_floor: float = 0.05) -> float:
        """Expected true count given observed detections: count / P, with P floored to cap the inflation."""
        return observed_count / max(self.probability(frp, area_km2), p_floor)


def fit_detection_model(frp: Sequence[float], area_km2: Sequence[float], detected_by_modis: Sequence[int]) -> DetectionModel:
    """Fit on VIIRS fire clusters labelled by whether a coincident MODIS detection exists."""
    y = np.asarray(detected_by_modis, dtype=int)
    if y.min() == y.max():
        raise ValueError("detection labels need both detected and missed examples")
    X = np.column_stack([np.log(np.maximum(frp, 1e-6)), -np.log(np.maximum(area_km2, 1e-6))])
    clf = LogisticRegression(C=1e6, max_iter=1000).fit(X, y)
    return DetectionModel(float(clf.intercept_[0]), float(clf.coef_[0][0]), float(clf.coef_[0][1]))


def terra_only_correction(terra_aqua_ratio_by_month: dict[int, float], month: int) -> float:
    """Multiplier turning a Terra-only observation count into Terra+Aqua, learned from 2003 onward."""
    return terra_aqua_ratio_by_month.get(month, 1.0)


def calibration_holdout_error(
    calibration: FrpCalibration, modis_frp: Sequence[float], viirs_frp: Sequence[float]
) -> dict[str, float]:
    """Reconstruct VIIRS from MODIS on held-out pairs and report the error (fit on 2012-2018, test 2019-2025)."""
    pred = np.array([calibration.predict(v)[0] for v in modis_frp])
    obs = np.asarray(viirs_frp, dtype=float)
    log_err = np.log(np.maximum(pred, 1e-6)) - np.log(np.maximum(obs, 1e-6))
    return {
        "n": float(len(obs)),
        "mae_mw": float(np.mean(np.abs(pred - obs))),
        "median_abs_pct_error": float(np.median(np.abs(pred - obs) / np.maximum(obs, 1e-6)) * 100),
        "log_bias": float(log_err.mean()),
        "log_rmse": float(sqrt((log_err**2).mean())),
    }


# --- Step 3: temporal sync -----------------------------------------------------------


@dataclass(frozen=True)
class DiurnalShape:
    """FRP(t) = base + peak * exp(-(t-h)^2 / (2 sigma^2)), t in local solar hours."""

    base: float
    peak: float
    h: float
    sigma: float

    def at(self, hour: float) -> float:
        d = min(abs(hour - self.h), 24 - abs(hour - self.h))
        return self.base + self.peak * exp(-(d**2) / (2 * self.sigma**2))

    def daily_integral(self) -> float:
        """Integral over 24 h of the shape, in (shape units * hours), wrapping around midnight."""
        t = np.linspace(0, 24, 24 * 60 + 1)
        d = np.minimum(np.abs(t - self.h), 24 - np.abs(t - self.h))
        y = self.base + self.peak * np.exp(-(d**2) / (2 * self.sigma**2))
        return float(np.trapezoid(y, t) if hasattr(np, "trapezoid") else np.trapz(y, t))


def fit_diurnal_shape(hours: Sequence[float], frp: Sequence[float]) -> DiurnalShape:
    """Fit the Gaussian-plus-baseline curve to stacked Himawari 10-minute FRP for one biome/region/month.

    Himawari supplies the *shape* only; polar sensors set the magnitude.
    """
    t = np.asarray(hours, dtype=float) % 24
    y = np.asarray(frp, dtype=float)
    if len(t) < 8:
        raise ValueError("need at least 8 diurnal samples")

    def model(t_, base, peak, h, sigma):
        d = np.minimum(np.abs(t_ - h), 24 - np.abs(t_ - h))
        return base + peak * np.exp(-(d**2) / (2 * sigma**2))

    p0 = [max(float(y.min()), 0.0), max(float(y.max() - y.min()), 1e-6), float(t[np.argmax(y)]), 3.0]
    (base, peak, h, sigma), _ = curve_fit(model, t, y, p0=p0, bounds=([0, 0, 0, 0.5], [np.inf, np.inf, 24, 12]), maxfev=5000)
    return DiurnalShape(float(base), float(peak), float(h % 24), float(sigma))


def daily_fre_mj(frp_obs_mw: float, overpass_hour: float, shape: DiurnalShape) -> float:
    """FRE_daily = FRP_obs / shape(t_obs) * integral(shape), in MJ (MW * hours * 3600 s/h).

    Puts Terra (10:30), Aqua/VIIRS (13:30) and any other pass on the same daily-energy scale.
    """
    at_pass = shape.at(overpass_hour % 24)
    if at_pass <= 0:
        raise ValueError("diurnal shape is zero at the overpass time")
    return frp_obs_mw / at_pass * shape.daily_integral() * 3600.0


def climatological_shape(shapes_by_biome_month: dict[tuple[str, int], DiurnalShape], biome: str, month: int) -> DiurnalShape:
    """Pre-2015 years have no Himawari; reuse the 2015+ climatological shape for that biome and month."""
    try:
        return shapes_by_biome_month[(biome, month)]
    except KeyError:
        raise KeyError(f"no diurnal shape learned for biome={biome!r} month={month}") from None


# --- False-positive cleanup ----------------------------------------------------------


def persistence_filter(frames: Sequence[set[tuple[float, float]]], min_frames: int = 3) -> set[tuple[float, float]]:
    """Keep cells hot in at least min_frames *consecutive* Himawari frames; drop sun glint and hot roofs.

    frames: per-10-minute-frame sets of hot cell keys, in time order.
    """
    run: dict[tuple[float, float], int] = {}
    kept: set[tuple[float, float]] = set()
    for frame in frames:
        run = {cell: run.get(cell, 0) + 1 for cell in frame}
        kept.update(cell for cell, n in run.items() if n >= min_frames)
    return kept


STATIC_TYPES = {1, 2, 3}  # MODIS type: 1 active volcano, 2 other static land source, 3 offshore


def static_source_mask(
    rows: Iterable[dict[str, Any]], years_total: int, hot_year_fraction: float = 0.8, res: float = 0.01
) -> set[tuple[float, float]]:
    """Cells to mask permanently: FIRMS type flags non-vegetation fire, or hot in > hot_year_fraction of years."""
    years_hot: dict[tuple[float, float], set[int]] = defaultdict(set)
    masked: set[tuple[float, float]] = set()
    for row in rows:
        key = snap_cell(float(row["lat"]), float(row["lon"]), res)
        if row.get("type") in STATIC_TYPES:
            masked.add(key)
        years_hot[key].add(row["acq_datetime"].year)
    masked.update(k for k, ys in years_hot.items() if years_total > 0 and len(ys) / years_total > hot_year_fraction)
    return masked


# --- Step 4: unified output record ---------------------------------------------------


def build_cell_week_records(
    clusters: Sequence[Sequence[dict[str, Any]]],
    shape_for: "callable[[dict[str, Any]], DiurnalShape | None]",
    frp_cal_for: "callable[[dict[str, Any]], FrpCalibration | None]",
    count_ratio_for: "callable[[dict[str, Any]], CountRatio | None]",
    res: float = CALENDAR_GRID_RES,
) -> dict[tuple[float, float, int, int], dict[str, Any]]:
    """Fold clusters into {(cell_lat, cell_lon, iso_year, iso_week): record}.

    shape_for / frp_cal_for / count_ratio_for take the cluster's lead row (which carries the
    sensor, biome and datetime) and return the correction or None. MODIS clusters get the
    VIIRS-equivalent count (ratio) and FRP (calibration); VIIRS passes through. Uncertainty is the
    quadrature sum of the log-space sds, scaled to the count.
    """
    out: dict[tuple[float, float, int, int], dict[str, Any]] = {}
    for cluster in clusters:
        lead = cluster[0]
        lat, lon = cluster_centroid(cluster)
        cell = snap_cell(lat, lon, res)
        iso = lead["acq_datetime"].isocalendar()
        key = (cell[0], cell[1], iso[0], iso[1])
        sensor_family = "MODIS" if str(lead.get("sensor")) == "modis" else "VIIRS" if str(lead.get("sensor", "")).startswith("viirs") else str(lead.get("sensor"))
        rec = out.setdefault(key, {"fire_events_harm": 0.0, "fre_harm": 0.0, "uncertainty": 0.0, "sensor_agreement": set(), "cause_label": None, "_var": 0.0})

        event_count, log_var = 1.0, 0.0
        frp = sum(float(r.get("frp") or 0.0) for r in cluster)
        if sensor_family == "MODIS":
            ratio = count_ratio_for(lead)
            if ratio is not None:
                event_count, se = ratio.scale(1.0)
                log_var += se**2 if np.isfinite(se) else 0.0
            cal = frp_cal_for(lead)
            if cal is not None:
                frp, se = cal.predict(frp)
                log_var += se**2
        shape = shape_for(lead)
        hour = lead["acq_datetime"].hour + lead["acq_datetime"].minute / 60.0
        fre = daily_fre_mj(frp, hour, shape) if shape is not None else 0.0

        rec["fire_events_harm"] += event_count
        rec["fre_harm"] += fre
        rec["_var"] += (event_count**2) * log_var
        rec["sensor_agreement"].add(sensor_family)
    for rec in out.values():
        rec["uncertainty"] = sqrt(rec.pop("_var"))
        rec["sensor_agreement"] = sorted(rec["sensor_agreement"])
    return out
