"""PELT change-point detection on long-term burning activity.

Detected change points are *statistically detected changes* in the level of a
deseasonalized monthly series. They can reflect climate, land use, agricultural
practice, or sensor/record effects; they are not asserted as physical truths.
"""

from __future__ import annotations

from math import log, log1p, expm1
from statistics import median
from typing import Any


def pelt_mean_shift(values: list[float], penalty: float, min_size: int = 2) -> list[int]:
    """Optimal partition under a Gaussian mean-change cost (Killick et al. 2012).

    Returns the indices where new segments start (excluding 0).
    """
    n = len(values)
    if n < 2 * min_size:
        return []
    s1 = [0.0]
    s2 = [0.0]
    for v in values:
        s1.append(s1[-1] + v)
        s2.append(s2[-1] + v * v)

    def cost(a: int, b: int) -> float:
        length = b - a
        total = s1[b] - s1[a]
        return (s2[b] - s2[a]) - total * total / length

    best = [0.0] * (n + 1)
    best[0] = -penalty
    last_change = [0] * (n + 1)
    candidates = [0]
    for t in range(1, n + 1):
        scores = [(best[tau] + cost(tau, t) + penalty, tau) for tau in candidates if t - tau >= min_size]
        if not scores:
            best[t] = float("inf")
            continue
        best[t], last_change[t] = min(scores)
        # Pruning: drop candidates that can never be optimal again.
        candidates = [tau for tau in candidates if t - tau < min_size or best[tau] + cost(tau, t) <= best[t]]
        candidates.append(t)

    changes = []
    t = n
    while t > 0:
        tau = last_change[t]
        if tau > 0:
            changes.append(tau)
        t = tau
    return sorted(changes)


def detect_monthly_change_points(monthly: list[dict[str, Any]], min_segment_months: int = 12) -> dict[str, Any]:
    """monthly: rows {year, month, harmonized_activity} in chronological order."""
    if len(monthly) < 3 * min_segment_months:
        return {
            "change_points": [],
            "status": "insufficient_record",
            "note": f"Change-point detection needs at least {3 * min_segment_months} months of record.",
        }
    logs = [log1p(float(row["harmonized_activity"])) for row in monthly]
    by_month: dict[int, list[float]] = {}
    for row, value in zip(monthly, logs):
        by_month.setdefault(int(row["month"]), []).append(value)
    clim = {m: median(v) for m, v in by_month.items()}
    residuals = [value - clim[int(row["month"])] for row, value in zip(monthly, logs)]

    diffs = [abs(b - a) for a, b in zip(residuals, residuals[1:])]
    sigma = (1.4826 * median(diffs) / 2**0.5) if diffs else 0.0
    sigma = max(sigma, 0.05)
    n = len(residuals)
    penalty = 3 * sigma * sigma * log(n)
    indices = pelt_mean_shift(residuals, penalty, min_segment_months)

    bounds = [0, *indices, n]
    segments = []
    for a, b in zip(bounds, bounds[1:]):
        seg = residuals[a:b]
        raw = [float(row["harmonized_activity"]) for row in monthly[a:b]]
        segments.append(
            {
                "start": f"{monthly[a]['year']}-{monthly[a]['month']:02d}",
                "end": f"{monthly[b - 1]['year']}-{monthly[b - 1]['month']:02d}",
                "mean_log_anomaly": round(sum(seg) / len(seg), 4),
                "mean_monthly_activity": round(sum(raw) / len(raw), 3),
            }
        )
    change_points = []
    for i, idx in enumerate(indices):
        before, after = segments[i], segments[i + 1]
        ratio = expm1(after["mean_log_anomaly"] - before["mean_log_anomaly"]) + 1
        change_points.append(
            {
                "date": f"{monthly[idx]['year']}-{monthly[idx]['month']:02d}",
                "direction": "increase" if ratio > 1 else "decrease",
                "relative_change": round(ratio, 3),
                "mean_activity_before": before["mean_monthly_activity"],
                "mean_activity_after": after["mean_monthly_activity"],
                "description": f"Statistically detected change: seasonally adjusted activity {'rose' if ratio > 1 else 'fell'} by a factor of about {ratio:.2f} from {after['start']}.",
            }
        )
    return {
        "change_points": change_points,
        "segments": segments,
        "status": "ok",
        "method": "PELT (Gaussian mean-shift cost) on log(1 + monthly harmonized activity) minus the monthly median climatology; penalty 3*sigma^2*log(n), minimum segment 12 months.",
        "caveat": "These are statistically detected changes. They may reflect climate, land use, fire management, or changes in the satellite record (e.g. VIIRS joining in 2012), and are not proof of a physical shift.",
    }
