"""Probabilistic burn forecast on the harmonized cell-week record.

P(c, w) is the probability that grid cell c has at least one harmonized fire event in week w.
Severity (expected harmonized FRE if it burns) is predicted separately.

Layers:
  1. Climatological baseline p_clim: Beta-smoothed share of years a cell-week burned, smoothed
     across +-1 week and neighbouring cells.
  2. Gradient boosting that learns an adjustment on the logit scale:
         logit P = logit p_clim + f(features)
     (XGBoost with base_margin = logit p_clim; per-prediction SHAP via pred_contribs).
     One model per lead time (direct multi-horizon strategy).
  3. Isotonic calibration on a held-out year, plus reliability table and Brier skill score.
  4. Uncertainty from a bootstrap ensemble.

Leakage rules, enforced by construction:
  * p_clim for a training target is computed leaving that target's year out.
  * Features use data up to the forecast origin only. Weather is "as of origin" conditions;
    pass SEAS5-style seasonal forecasts as separate columns if you have them, never observed
    weather from weeks that have not happened yet.

Arrays: counts[Y, 52, C] harmonized event counts per year, ISO-week slot (week 53 folded into 52)
and cell. Weather, when supplied, is weather[Y, 52, C, F] observed at the end of that week.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
import xgboost as xgb
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression


WEEKS = 52
EPS = 1e-4


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


# --- Layer 1: climatology ------------------------------------------------------------


def climatology(
    counts: np.ndarray,
    years: Sequence[int] | None = None,
    alpha: float = 0.5,
    beta: float = 0.5,
    neighbors: np.ndarray | None = None,
    spatial_weight: float = 0.3,
) -> np.ndarray:
    """p_clim[52, C] = (k + alpha) / (n + alpha + beta), with k smoothed across +-1 week.

    k is the weighted count of years in which the cell burned in week w (weights 1/4, 1/2, 1/4
    over w-1, w, w+1, wrapping the year). `years` selects which year indices to use (default all).
    `neighbors` is an optional [C, C] row-normalised adjacency; spatial_weight blends the
    neighbour average into each cell.
    """
    burned = (counts > 0).astype(float)
    if years is not None:
        burned = burned[list(years)]
    n = burned.shape[0]
    if n == 0:
        raise ValueError("climatology needs at least one year")
    k = burned.sum(axis=0)  # [52, C]
    k = 0.5 * k + 0.25 * np.roll(k, 1, axis=0) + 0.25 * np.roll(k, -1, axis=0)
    p = (k + alpha) / (n + alpha + beta)
    if neighbors is not None and spatial_weight > 0:
        p = (1 - spatial_weight) * p + spatial_weight * (p @ neighbors.T)
    return p


def grid_neighbors(n_rows: int, n_cols: int) -> np.ndarray:
    """Row-normalised 8-neighbour adjacency (cells in row-major order), excluding self."""
    C = n_rows * n_cols
    A = np.zeros((C, C))
    for r in range(n_rows):
        for c in range(n_cols):
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if (dr or dc) and 0 <= r + dr < n_rows and 0 <= c + dc < n_cols:
                        A[r * n_cols + c, (r + dr) * n_cols + c + dc] = 1
    s = A.sum(axis=1, keepdims=True)
    return np.divide(A, s, out=np.zeros_like(A), where=s > 0)


def log_z_score(recent: np.ndarray, hist_mean: np.ndarray, hist_std: np.ndarray) -> np.ndarray:
    """z on log(1+x): counts are skewed, so plain mean/std z-scores mislead."""
    return (np.log1p(recent) - hist_mean) / np.maximum(hist_std, 0.25)


# --- Features ------------------------------------------------------------------------

FEATURE_NAMES = [
    "logit_p_clim",
    "p_clim_prev_week",
    "z_recent_2w",
    "z_recent_4w",
    "neighbor_activity_4w",
    "weeks_since_burn",
    "annual_trend",
    "lead_week_of_year_sin",
    "lead_week_of_year_cos",
]


def _slot(year: int, week: int) -> int:
    return year * WEEKS + week


def build_features(
    counts: np.ndarray,
    year: int,
    origin_week: int,
    lead: int,
    p_clim_by_year: dict[int, np.ndarray],
    neighbors: np.ndarray | None = None,
    weather: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Feature matrix [C, F] for forecasting week origin_week + lead of the flat timeline.

    Only data from weeks <= origin_week are touched. p_clim_by_year[y] must be the climatology that
    excludes year y when y is a training year (see leave_one_year_out_climatology). Returns
    (X, target_slot_week_of_year) where the second item is the target's week-of-year.
    """
    Y, _, C = counts.shape
    flat = counts.reshape(Y * WEEKS, C)
    t0 = _slot(year, origin_week)
    tgt = t0 + lead
    t_year, t_week = divmod(tgt, WEEKS)
    t_year = min(t_year, max(p_clim_by_year))
    p_clim = p_clim_by_year[t_year if t_year in p_clim_by_year else max(p_clim_by_year)]

    def recent(w):
        lo = max(t0 - w + 1, 0)
        return flat[lo : t0 + 1].sum(axis=0)

    # Historical log-count mean/std for the same trailing window, over years strictly before `year`.
    def hist_stats(w):
        vals = []
        for y in range(year):
            lo = _slot(y, origin_week) - w + 1
            if lo >= 0:
                vals.append(np.log1p(flat[lo : _slot(y, origin_week) + 1].sum(axis=0)))
        if len(vals) < 2:
            return np.zeros(C), np.ones(C)
        v = np.array(vals)
        return v.mean(axis=0), v.std(axis=0)

    z2 = log_z_score(recent(2), *hist_stats(2))
    z4 = log_z_score(recent(4), *hist_stats(4))
    activity = np.log1p(recent(4))
    nb = activity if neighbors is None else neighbors @ activity

    burned_hist = flat[: t0 + 1] > 0
    last = np.where(burned_hist.any(axis=0), t0 - (len(burned_hist) - 1 - np.argmax(burned_hist[::-1], axis=0)), 104)
    weeks_since = np.minimum(last, 104).astype(float)

    annual = np.log1p(counts[:year].sum(axis=1)) if year >= 3 else np.zeros((max(year, 1), C))
    trend = np.polyfit(np.arange(len(annual)), annual, 1)[0] if len(annual) >= 3 else np.zeros(C)

    angle = 2 * np.pi * t_week / WEEKS
    cols = [
        logit(p_clim[t_week]),
        logit(p_clim[(t_week - 1) % WEEKS]),
        z2,
        z4,
        nb,
        weeks_since,
        trend,
        np.full(C, np.sin(angle)),
        np.full(C, np.cos(angle)),
    ]
    if weather is not None:
        w = weather[year, origin_week]  # [C, F]; as-of-origin conditions only
        cols.extend(w[:, f] for f in range(w.shape[1]))
    return np.column_stack(cols), np.full(C, t_week)


def leave_one_year_out_climatology(counts: np.ndarray, train_years: Sequence[int], **kw) -> dict[int, np.ndarray]:
    """p_clim for each year computed from the *other* training years; unseen years use all of them."""
    out = {y: climatology(counts, [x for x in train_years if x != y], **kw) for y in train_years}
    full = climatology(counts, list(train_years), **kw)
    for y in range(counts.shape[0]):
        out.setdefault(y, full)
    return out


# --- Layers 2-4: model ---------------------------------------------------------------


def fit_member(X: np.ndarray, y: np.ndarray, n_estimators: int, seed: int) -> xgb.XGBClassifier:
    """XGBoost trained on top of the climatology: base_margin is logit p_clim (feature column 0)."""
    clf = xgb.XGBClassifier(
        n_estimators=n_estimators, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.9,
        random_state=seed, n_jobs=1, verbosity=0,
    )
    return clf.fit(X, y, base_margin=X[:, 0])


def member_proba(clf: xgb.XGBClassifier, X: np.ndarray) -> np.ndarray:
    return clf.predict_proba(X, base_margin=X[:, 0])[:, 1]


def explain(model: "LeadModel", X: np.ndarray, feature_names: Sequence[str] = FEATURE_NAMES) -> list[dict[str, float]]:
    """Per-row SHAP contributions on the logit scale (first ensemble member), excluding the p_clim offset."""
    names = list(feature_names) + [f"weather_{i}" for i in range(X.shape[1] - len(feature_names))]
    contrib = model.members[0].get_booster().predict(xgb.DMatrix(X, base_margin=X[:, 0]), pred_contribs=True)
    return [dict(zip(names, row[:-1])) for row in contrib]


@dataclass
class LeadModel:
    lead: int
    members: list[xgb.XGBClassifier]
    calibrators: list[IsotonicRegression]
    severity: GradientBoostingRegressor | None = None

    def predict(self, X: np.ndarray) -> dict[str, np.ndarray]:
        raw = np.array([member_proba(m, X) for m in self.members])
        cal = np.array([c.predict(r) for c, r in zip(self.calibrators, raw)])
        return {
            "p": cal.mean(axis=0),
            "p_low": np.quantile(cal, 0.1, axis=0),
            "p_high": np.quantile(cal, 0.9, axis=0),
            "members": cal,
        }


@dataclass
class Forecaster:
    models: dict[int, LeadModel]
    feature_names: list[str] = field(default_factory=lambda: list(FEATURE_NAMES))


def _training_table(counts, years, leads, p_by_year, neighbors, weather, stride):
    Y = counts.shape[0]
    flat = counts.reshape(Y * WEEKS, -1)
    X, y_, fre = {l: [] for l in leads}, {l: [] for l in leads}, {l: [] for l in leads}
    for lead in leads:
        for year in years:
            for w in range(0, WEEKS, stride):
                tgt = _slot(year, w) + lead
                if tgt >= Y * WEEKS or tgt // WEEKS not in years:
                    continue
                feats, _ = build_features(counts, year, w, lead, p_by_year, neighbors, weather)
                X[lead].append(feats)
                y_[lead].append((flat[tgt] > 0).astype(int))
                fre[lead].append(flat[tgt])
    return {l: (np.vstack(X[l]), np.concatenate(y_[l]), np.concatenate(fre[l])) for l in leads if X[l]}


def fit_forecaster(
    counts: np.ndarray,
    train_years: Sequence[int],
    calib_year: int,
    leads: Sequence[int] = tuple(range(1, 9)),
    n_models: int = 5,
    neighbors: np.ndarray | None = None,
    weather: np.ndarray | None = None,
    stride: int = 2,
    seed: int = 0,
    n_estimators: int = 80,
) -> Forecaster:
    """Train one bootstrap ensemble per lead on train_years; fit isotonic calibration on calib_year.

    calib_year must not be in train_years. Its p_clim excludes itself, like the training rows.
    """
    if calib_year in train_years:
        raise ValueError("calib_year must be held out from train_years")
    train_years = list(train_years)
    p_by_year = leave_one_year_out_climatology(counts, train_years, neighbors=neighbors)
    p_by_year[calib_year] = climatology(counts, train_years, neighbors=neighbors)
    train = _training_table(counts, train_years, leads, p_by_year, neighbors, weather, stride)
    calib = _training_table(counts, [calib_year], leads, p_by_year, neighbors, weather, stride)
    rng = np.random.default_rng(seed)

    models: dict[int, LeadModel] = {}
    for lead, (X, y, fre) in train.items():
        Xc, yc, _ = calib[lead]
        members, cals = [], []
        for i in range(n_models):
            idx = rng.integers(0, len(y), len(y))
            clf = fit_member(X[idx], y[idx], n_estimators, int(rng.integers(1 << 31)))
            iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(member_proba(clf, Xc), yc)
            members.append(clf)
            cals.append(iso)
        burned = fre > 0
        sev = None
        if burned.sum() >= 30:
            sev = GradientBoostingRegressor(n_estimators=60, max_depth=3, random_state=seed).fit(X[burned], np.log1p(fre[burned]))
        models[lead] = LeadModel(lead, members, cals, sev)
    return Forecaster(models)


def predict_cells(
    fc: Forecaster,
    counts: np.ndarray,
    year: int,
    origin_week: int,
    neighbors: np.ndarray | None = None,
    weather: np.ndarray | None = None,
    p_by_year: dict[int, np.ndarray] | None = None,
) -> dict[int, dict[str, np.ndarray]]:
    """Forecast every lead from (year, origin_week). Uses data up to the origin only."""
    if p_by_year is None:
        p_by_year = {y: climatology(counts, list(range(counts.shape[0])), neighbors=neighbors) for y in [year]}
    out = {}
    for lead, model in fc.models.items():
        X, tgt_week = build_features(counts, year, origin_week, lead, p_by_year, neighbors, weather)
        res = model.predict(X)
        res["p_clim"] = sigmoid(X[:, 0])
        res["ratio_to_normal"] = res["p"] / np.maximum(res["p_clim"], EPS)
        res["severity_log1p"] = model.severity.predict(X) if model.severity is not None else None
        res["features"] = X
        out[lead] = res
    return out


def expected_peak_lead(curve: Sequence[float]) -> int:
    """Index (1-based lead) of the week with highest probability."""
    return int(np.argmax(curve)) + 1


# --- Evaluation ----------------------------------------------------------------------


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def brier_skill_score(p_model: np.ndarray, p_clim: np.ndarray, y: np.ndarray) -> float:
    """BSS = 1 - Brier_model / Brier_clim; > 0 means the model beats the historical average."""
    ref = brier(p_clim, y)
    return float("nan") if ref == 0 else 1.0 - brier(p_model, y) / ref


def reliability_table(p: np.ndarray, y: np.ndarray, bins: Sequence[float] = (0, 0.1, 0.3, 0.5, 0.7, 1.0001)) -> list[dict[str, float]]:
    """Per bin: mean predicted vs observed frequency. A calibrated 70% burns ~70% of the time."""
    p, y = np.asarray(p), np.asarray(y)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi)
        if m.any():
            rows.append({"bin_low": lo, "bin_high": min(hi, 1.0), "n": int(m.sum()), "mean_predicted": float(p[m].mean()), "observed_frequency": float(y[m].mean())})
    return rows


def evaluate(
    fc: Forecaster,
    counts: np.ndarray,
    test_years: Sequence[int],
    train_years: Sequence[int],
    neighbors: np.ndarray | None = None,
    weather: np.ndarray | None = None,
    stride: int = 4,
) -> dict[int, dict]:
    """Per-lead Brier, BSS vs climatology and reliability table on test years never used for training."""
    p_by_year = {y: climatology(counts, list(train_years), neighbors=neighbors) for y in test_years}
    out = {}
    for lead, model in fc.models.items():
        P, B, Y_ = [], [], []
        flat = counts.reshape(-1, counts.shape[2])
        for year in test_years:
            for w in range(0, WEEKS, stride):
                tgt = _slot(year, w) + lead
                if tgt >= flat.shape[0]:
                    continue
                X, _ = build_features(counts, year, w, lead, p_by_year, neighbors, weather)
                P.append(model.predict(X)["p"])
                B.append(sigmoid(X[:, 0]))
                Y_.append((flat[tgt] > 0).astype(int))
        if not P:
            continue
        P, B, Y_ = np.concatenate(P), np.concatenate(B), np.concatenate(Y_)
        out[lead] = {"n": int(len(Y_)), "brier_model": brier(P, Y_), "brier_clim": brier(B, Y_), "bss": brier_skill_score(P, B, Y_), "reliability": reliability_table(P, Y_)}
    return out


# --- AOI aggregation -----------------------------------------------------------------


def p_aoi_independent(p_cells: np.ndarray) -> float:
    """P_AOI = 1 - prod(1 - P_c). Assumes independent cells, so it overstates risk when neighbours correlate."""
    return float(1.0 - np.prod(1.0 - np.asarray(p_cells)))


def p_aoi_correlated(p_cells: np.ndarray, rho: float, n_sims: int = 20000, seed: int = 0) -> float:
    """Monte Carlo P(any cell burns) with a shared latent factor (Gaussian copula, equicorrelation rho).

    Each cell burns when its copula uniform falls below its marginal P_c, so marginals are preserved.
    Estimate rho from history with mean_pairwise_correlation.
    """
    from scipy.stats import norm

    p = np.asarray(p_cells, dtype=float)
    rng = np.random.default_rng(seed)
    rho = float(np.clip(rho, 0.0, 0.999))
    common = rng.standard_normal((n_sims, 1))
    own = rng.standard_normal((n_sims, len(p)))
    u = norm.cdf(np.sqrt(rho) * common + np.sqrt(1 - rho) * own)
    return float(np.mean((u < p).any(axis=1)))


def mean_pairwise_correlation(burned: np.ndarray) -> float:
    """Mean off-diagonal correlation of burn indicators burned[T, C]; the rho for p_aoi_correlated."""
    b = np.asarray(burned, dtype=float)
    keep = b.std(axis=0) > 0
    if keep.sum() < 2:
        return 0.0
    r = np.corrcoef(b[:, keep], rowvar=False)
    n = r.shape[0]
    return float((r.sum() - n) / (n * (n - 1)))
