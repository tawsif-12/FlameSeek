"""Fire Memory: seasonal fire profiles and current-vs-historical comparison."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Any

from harmonize import _percentile, anomaly_category, record_date, robust_scale


MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _longest_run(flags: list[bool]) -> int:
    best = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def monthly_series(daily: list[dict[str, Any]], hotspots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per (year, month): activity, active days, FRP and spatial spread."""
    spread: dict[tuple[int, int], set[tuple[int, int]]] = defaultdict(set)
    frps: dict[tuple[int, int], list[float]] = defaultdict(list)
    for row in hotspots:
        d = record_date(row["acq_datetime"])
        spread[(d.year, d.month)].add((int(float(row["lat"]) * 10), int(float(row["lon"]) * 10)))
        if row.get("frp") is not None:
            frps[(d.year, d.month)].append(float(row["frp"]))
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in daily:
        grouped[(row["date"].year, row["date"].month)].append(row)
    out = []
    for (year, month), rows in sorted(grouped.items()):
        f = frps.get((year, month), [])
        out.append(
            {
                "year": year,
                "month": month,
                "days_in_record": len(rows),
                "harmonized_activity": round(sum(r["harmonized_activity"] for r in rows), 3),
                "hotspot_count": sum(r["hotspot_count"] for r in rows),
                "active_days": sum(1 for r in rows if r["hotspot_count"] > 0),
                "median_frp": round(median(f), 2) if f else None,
                "p90_frp": round(_percentile(f, 0.9), 2) if f else None,
                "spatial_spread_cells_10km": len(spread.get((year, month), set())),
                "mean_sufficiency": round(sum(r["observation"]["sufficiency_score"] for r in rows) / len(rows), 1),
            }
        )
    return out


def seasonal_profile(monthly: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Typical values per calendar month across all years (only complete-ish months)."""
    complete = [m for m in monthly if m["days_in_record"] >= 20]
    years = sorted({m["year"] for m in complete})
    annual_totals = defaultdict(float)
    for m in complete:
        annual_totals[m["year"]] += m["harmonized_activity"]

    event_durations: dict[int, list[float]] = defaultdict(list)
    for ev in events:
        start = ev["first_detection"]
        event_durations[start.month].append(ev["duration_hours"])

    months = []
    for month in range(1, 13):
        rows = [m for m in complete if m["month"] == month]
        if not rows:
            months.append({"month": month, "name": MONTH_NAMES[month - 1], "years": 0})
            continue
        shares = [m["harmonized_activity"] / annual_totals[m["year"]] for m in rows if annual_totals[m["year"]] > 0]
        acts = [m["harmonized_activity"] for m in rows]
        frps = [m["median_frp"] for m in rows if m["median_frp"] is not None]
        durations = event_durations.get(month, [])
        months.append(
            {
                "month": month,
                "name": MONTH_NAMES[month - 1],
                "years": len(rows),
                "median_activity": round(median(acts), 3),
                "activity_iqr": [round(_percentile(acts, 0.25), 3), round(_percentile(acts, 0.75), 3)],
                "median_hotspots": median([m["hotspot_count"] for m in rows]),
                "median_active_days": median([m["active_days"] for m in rows]),
                "median_frp": round(median(frps), 2) if frps else None,
                "median_spatial_spread_cells_10km": median([m["spatial_spread_cells_10km"] for m in rows]),
                "median_event_duration_hours": round(median(durations), 1) if durations else None,
                "events_per_year": round(len(durations) / len(rows), 2),
                "median_share_of_year": round(median(shares), 4) if shares else 0.0,
            }
        )
    ranked = sorted((m for m in months if m.get("years")), key=lambda m: m["median_share_of_year"], reverse=True)
    peak = [m["name"] for m in ranked[:3] if m["median_share_of_year"] > 0]
    active = [m["name"] for m in months if m.get("median_share_of_year", 0) >= 0.10]
    quiet = [m["name"] for m in months if m.get("years") and m.get("median_share_of_year", 0) < 0.02]
    for m in months:
        share = m.get("median_share_of_year", 0)
        m["season_level"] = "peak" if m["name"] in peak[:1] else "active" if share >= 0.10 else "moderate" if share >= 0.02 else "quiet" if m.get("years") else "no data"
    return {
        "years": years,
        "months": months,
        "peak_months": peak,
        "active_months": active,
        "quiet_months": quiet,
        "note": "Typical values are medians across years for months with at least 20 days of record.",
    }


def calendar_grid(monthly: list[dict[str, Any]]) -> dict[str, Any]:
    years = sorted({m["year"] for m in monthly})
    lookup = {(m["year"], m["month"]): m for m in monthly}
    return {
        "years": years,
        "months": MONTH_NAMES,
        "activity": [[lookup[(y, mo)]["harmonized_activity"] if (y, mo) in lookup else None for mo in range(1, 13)] for y in years],
        "hotspots": [[lookup[(y, mo)]["hotspot_count"] if (y, mo) in lookup else None for mo in range(1, 13)] for y in years],
    }


def compare_current(daily: list[dict[str, Any]], profile: dict[str, Any], window_days: int = 30) -> dict[str, Any]:
    """Compare the most recent window with the same calendar window in earlier years."""
    if not daily:
        return {"status": "no_data"}
    end = daily[-1]["date"]
    start = end - timedelta(days=window_days - 1)
    by_date = {row["date"]: row for row in daily}
    current = [by_date[d] for d in (start + timedelta(days=i) for i in range(window_days)) if d in by_date]

    history = []
    for year in sorted({row["date"].year for row in daily}):
        if year == end.year:
            continue
        try:
            h_end = end.replace(year=year)
        except ValueError:
            h_end = end.replace(year=year, day=28)
        h_start = h_end - timedelta(days=window_days - 1)
        rows = [by_date[d] for d in (h_start + timedelta(days=i) for i in range(window_days)) if d in by_date]
        if len(rows) >= window_days * 0.8:
            history.append({"year": year, "rows": rows})

    cur_total = sum(r["harmonized_activity"] for r in current)
    cur_hotspots = sum(r["hotspot_count"] for r in current)
    cur_max_frp = max((r["max_frp"] or 0) for r in current)
    cur_run = _longest_run([r["hotspot_count"] > 0 for r in current])
    recent3 = current[-3:]
    prior = current[-17:-3]

    flags = []
    result: dict[str, Any] = {
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": window_days},
        "current": {"harmonized_activity": round(cur_total, 3), "hotspots": cur_hotspots, "max_frp": cur_max_frp, "longest_active_run_days": cur_run},
        "history_years": [h["year"] for h in history],
        "flags": flags,
    }
    if len(history) < 2:
        result["status"] = "insufficient_history"
        result["overall_category"] = "Not assessed"
        result["note"] = "At least two earlier years covering the same window are needed; extend the history period."
        return result

    hist_totals = [sum(r["harmonized_activity"] for r in h["rows"]) for h in history]
    hist_hotspots = [sum(r["hotspot_count"] for r in h["rows"]) for h in history]
    hist_daily_max_frp = [r["max_frp"] for h in history for r in h["rows"] if r["max_frp"]]
    hist_runs = [_longest_run([r["hotspot_count"] > 0 for r in h["rows"]]) for h in history]
    med, scale = robust_scale(hist_totals)
    z = (cur_total - med) / scale
    result["historical"] = {
        "median_harmonized_activity": round(med, 3),
        "median_hotspots": median(hist_hotspots),
        "p95_daily_max_frp": round(_percentile(hist_daily_max_frp, 0.95), 2) if hist_daily_max_frp else None,
        "p90_longest_run_days": round(_percentile([float(x) for x in hist_runs], 0.9), 1),
    }
    result["robust_z"] = round(z, 3)
    result["overall_category"] = anomaly_category(z)
    result["percentile_rank"] = round(100 * sum(1 for t in hist_totals if t < cur_total) / len(hist_totals), 1)

    if cur_total > 0 and z >= 2:
        flags.append({"flag": "more_than_normal", "label": "More hotspots than normal", "detail": f"{cur_total:.1f} harmonized active cells vs a historical median of {med:.1f} for this window."})
    p95 = result["historical"]["p95_daily_max_frp"]
    if p95 and cur_max_frp > p95:
        flags.append({"flag": "strong_frp", "label": "Unusually strong FRP", "detail": f"Peak FRP {cur_max_frp:.0f} MW exceeds the historical 95th percentile ({p95:.0f} MW) for this window."})
    month = end.month
    month_info = next((m for m in profile.get("months", []) if m["month"] == month), None)
    if month_info and month_info.get("season_level") == "quiet" and cur_hotspots >= 5:
        flags.append({"flag": "outside_season", "label": "Fire outside the normal burning season", "detail": f"{month_info['name']} normally holds under 2% of annual activity, yet {cur_hotspots} detections occurred."})
    rc = [r["active_cell_count"] for r in recent3]
    pc = [r["active_cell_count"] for r in prior] or [0]
    if rc and sum(rc) / len(rc) >= max(5, 2 * (sum(pc) / len(pc))):
        flags.append({"flag": "rapid_expansion", "label": "Rapid spatial expansion", "detail": f"Active ~1 km cells averaged {sum(rc) / len(rc):.1f}/day over the last 3 days vs {sum(pc) / len(pc):.1f}/day in the prior two weeks."})
    if cur_run >= max(5, result["historical"]["p90_longest_run_days"] + 1):
        flags.append({"flag": "repeated_detections", "label": "Repeated detections over a long period", "detail": f"{cur_run} consecutive active days vs a historical 90th percentile of {result['historical']['p90_longest_run_days']:.0f}."})
    ra = sum(r["harmonized_activity"] for r in recent3) / max(1, len(recent3))
    pa = sum(r["harmonized_activity"] for r in prior) / max(1, len(prior))
    if ra >= 3 and ra >= 3 * max(pa, 0.5):
        flags.append({"flag": "sudden_increase", "label": "Sudden increase in burning activity", "detail": f"Last-3-day activity ({ra:.1f}/day) is over three times the preceding fortnight ({pa:.1f}/day)."})
    result["status"] = "ok"
    result["note"] = "Categories describe statistical behaviour relative to this area's own history, not disaster severity."
    return result
