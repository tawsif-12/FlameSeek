"""Deterministic Fire DNA statistics derived from server-side monthly aggregates."""

from __future__ import annotations

from statistics import median
from typing import Any


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _peak_season(monthly_reference: list[dict[str, Any]]) -> list[str]:
    """Longest circular run at or above the 75th percentile monthly median."""
    available = [float(row["median_activity"]) for row in monthly_reference if row["median_activity"] is not None]
    if not available or max(available) <= 0:
        return []
    threshold = _percentile(available, 0.75)
    active = [row["median_activity"] is not None and float(row["median_activity"]) >= threshold and float(row["median_activity"]) > 0 for row in monthly_reference]
    doubled = active + active
    best_start = best_length = current_start = current_length = 0
    for index, flag in enumerate(doubled):
        if flag:
            if current_length == 0:
                current_start = index
            current_length = min(current_length + 1, 12)
            if current_length > best_length and current_start < 12:
                best_start, best_length = current_start, current_length
        else:
            current_length = 0
    return [monthly_reference[(best_start + offset) % 12]["name"] for offset in range(best_length)]


def _theil_sen(annual: list[dict[str, Any]]) -> dict[str, Any]:
    comparable = [row for row in annual if row["comparable"]]
    if len(comparable) < 4:
        return {"direction": "Insufficient data", "slope_per_year": None, "percent_per_year": None, "slope_interval": None, "years": len(comparable), "method": "Theil–Sen median slope; at least four complete years required."}
    slopes = [
        (float(b["activity"]) - float(a["activity"])) / (int(b["year"]) - int(a["year"]))
        for index, a in enumerate(comparable)
        for b in comparable[index + 1 :]
        if int(b["year"]) != int(a["year"])
    ]
    slope = median(slopes)
    low, high = _percentile(slopes, 0.25), _percentile(slopes, 0.75)
    typical = median(float(row["activity"]) for row in comparable)
    percent = 100 * slope / typical if typical > 0 else None
    # Direction requires the central half of pairwise slopes to agree in sign.
    direction = "Increasing" if low > 0 else "Decreasing" if high < 0 else "Stable"
    return {
        "direction": direction,
        "slope_per_year": round(slope, 3),
        "percent_per_year": round(percent, 3) if percent is not None else None,
        "slope_interval": [round(low, 3), round(high, 3)],
        "years": len(comparable),
        "method": "Theil–Sen median of all pairwise slopes; direction changes only when the interquartile slope interval excludes zero.",
    }


def build_fire_dna_profile(monthly: list[dict[str, Any]], seasonal: dict[str, Any], period: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    complete_months = [row for row in monthly if int(row["days_in_record"]) >= 20]
    monthly_reference = []
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for month in range(1, 13):
        values = [float(row["harmonized_activity"]) for row in complete_months if int(row["month"]) == month]
        monthly_reference.append({
            "month": month,
            "name": names[month - 1],
            "median_activity": round(median(values), 3) if values else None,
            "q1_activity": round(_percentile(values, 0.25), 3) if values else None,
            "q3_activity": round(_percentile(values, 0.75), 3) if values else None,
            "years": len(values),
        })

    by_year: dict[int, list[dict[str, Any]]] = {}
    for row in monthly:
        by_year.setdefault(int(row["year"]), []).append(row)
    annual = []
    for year, rows in sorted(by_year.items()):
        complete = [row for row in rows if int(row["days_in_record"]) >= 20]
        comparable = len(complete) == 12
        annual.append({
            "year": year,
            "activity": round(sum(float(row["harmonized_activity"]) for row in complete), 3) if complete else None,
            "months": len(complete),
            "comparable": comparable,
        })
    comparable = [row for row in annual if row["comparable"] and row["activity"] is not None]
    trend = _theil_sen(annual)
    peak = max((row for row in monthly_reference if row["median_activity"] is not None), key=lambda row: float(row["median_activity"]), default=None)
    peak_season = _peak_season(monthly_reference)
    typical_annual = round(median(float(row["activity"]) for row in comparable), 3) if comparable else None
    highest = max(comparable, key=lambda row: float(row["activity"]), default=None)
    lowest = min(comparable, key=lambda row: float(row["activity"]), default=None)
    start_year, end_year = str(period["start"])[:4], str(period["end"])[:4]
    peak_words = ", ".join(peak_season) if peak_season else (peak["name"] if peak else "no stable peak month")
    reliability = "limited" if quality.get("pct_days_unobservable", 0) >= 30 else "moderate" if quality.get("mean_sufficiency_score", 0) < 70 else "good"
    summary = f"Between {start_year} and {end_year}, this region typically experienced its highest satellite-detected hotspot activity during {peak_words}. The comparable long-term trend was {str(trend['direction']).lower()}. Data reliability was {reliability}; cloud cover, satellite availability and sensor sensitivity can limit interpretation."
    return {
        "monthly_reference": monthly_reference,
        "annual": annual,
        "peak_month": peak["name"] if peak else None,
        "peak_season": peak_season,
        "typical_annual_activity": typical_annual,
        "highest_year": highest,
        "lowest_year": lowest,
        "trend": trend,
        "reliability": {"label": reliability, "mean_sufficiency_score": quality.get("mean_sufficiency_score"), "pct_days_unobservable": quality.get("pct_days_unobservable"), "method": quality.get("method")},
        "summary": summary,
        "method": "Monthly reference values are medians of months with at least 20 record days. Annual comparisons require all 12 such months. Peak season is the longest circular run at or above the 75th percentile monthly median.",
    }
