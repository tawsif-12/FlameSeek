"""Area fire-intelligence additions to the Fire Memory result.

hotspot_recurrence: where detections repeat. Detections are binned on a grid sized to the area;
each cell reports detections, distinct detection days and distinct years.

area_climatology: chance of at least one fire in the area in the next `horizon_days`, from the
area's own consistent (Aqua 13:30-equivalent) daily record. For each past year the same calendar
window is checked for any harmonized activity; the count of fire years k out of n is shrunk toward
the area's all-year base rate p0 with a weak Beta prior of strength m (2 pseudo-years, since
there is only one outcome per year):
    P = (k + m * p0) / (n + m)
Validation: leave-one-year-out over non-overlapping windows of every year; Brier score against the
constant base rate gives a Brier Skill Score (BSS > 0: seasonal timing adds skill). With fewer than
`min_years` complete years the estimate is withheld. This is a climatological baseline, not a
weather-driven forecast.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import numpy as np

CONFIDENCE_MIN_PCT = 30
TARGET_CELLS = 900


def _cell_size(bbox: tuple[float, float, float, float]) -> float:
    west, south, east, north = bbox
    span = max(east - west, north - south, 0.01)
    raw = span / math.sqrt(TARGET_CELLS)
    for step in (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1.0):
        if raw <= step:
            return step
    return 1.0


def hotspot_recurrence(rows: list[dict[str, Any]], bbox: tuple[float, float, float, float], top: int = 400) -> dict[str, Any]:
    deg = _cell_size(bbox)
    cells: dict[tuple[int, int], dict[str, Any]] = defaultdict(lambda: {"n": 0, "days": set(), "years": set(), "first": None, "last": None})
    used = 0
    for r in rows:
        conf = r.get("confidence_pct")
        if conf is not None and conf < CONFIDENCE_MIN_PCT:
            continue
        when = r.get("acq_datetime")
        day = when.date() if hasattr(when, "date") else None
        if day is None:
            continue
        key = (math.floor(r["lon"] / deg), math.floor(r["lat"] / deg))
        c = cells[key]
        c["n"] += 1
        c["days"].add(day)
        c["years"].add(day.year)
        c["first"] = day if c["first"] is None or day < c["first"] else c["first"]
        c["last"] = day if c["last"] is None or day > c["last"] else c["last"]
        used += 1
    out = [{"lon": (ix + 0.5) * deg, "lat": (iy + 0.5) * deg, "detections": c["n"], "days": len(c["days"]),
            "years": len(c["years"]), "first": c["first"].isoformat(), "last": c["last"].isoformat()}
           for (ix, iy), c in cells.items()]
    out.sort(key=lambda c: (c["days"], c["detections"]), reverse=True)
    return {"status": "computed" if out else "no detections", "cell_deg": deg, "n_cells_with_fire": len(out),
            "detections_used": used, "cells": out[:top], "truncated": len(out) > top,
            "method": f"Detections (confidence >= {CONFIDENCE_MIN_PCT}% where reported) binned on {deg} deg cells; "
                      "days = distinct UTC days with at least one detection in the cell."}


def _shift(day: date, year: int) -> date:
    try:
        return day.replace(year=year)
    except ValueError:  # 29 February
        return day.replace(year=year, day=28)


def area_climatology(daily: list[dict[str, Any]], end: date, horizon_days: int = 28, min_years: int = 5,
                     prior_strength: float = 2.0) -> dict[str, Any]:
    fire = {date.fromisoformat(d["date"]): (d.get("harmonized_activity") or 0) > 0 for d in daily}
    if not fire:
        return {"status": "insufficient_history", "reason": "no daily record"}
    first, last = min(fire), max(fire)
    target_start = end + timedelta(days=1)
    target_end = end + timedelta(days=horizon_days)

    def window_has_fire(start: date) -> bool | None:
        days = [start + timedelta(days=i) for i in range(horizon_days)]
        if days[0] < first or days[-1] > last:
            return None  # window not fully inside the record
        return any(fire.get(d, False) for d in days)

    years = sorted({d.year for d in fire})
    # Outcome of the forecast window in each past year.
    outcomes = {}
    for y in years:
        o = window_has_fire(_shift(target_start, y))
        if o is not None and _shift(target_start, y) <= end:
            outcomes[y] = o
    # Non-overlapping windows of every year for the base rate and validation.
    blocks: dict[int, list[bool]] = {}
    for y in years:
        vals = []
        for b in range(365 // horizon_days):
            o = window_has_fire(date(y, 1, 1) + timedelta(days=b * horizon_days))
            if o is not None:
                vals.append(o)
        if len(vals) == 365 // horizon_days:
            blocks[y] = vals
    n_years = len(blocks)
    if n_years < min_years or len(outcomes) < min_years:
        return {"status": "insufficient_history", "complete_years": n_years, "min_years": min_years,
                "reason": f"needs at least {min_years} complete years of the consistent record"}

    def estimate(exclude: int | None, block: int | None) -> tuple[float, float]:
        ys = [y for y in blocks if y != exclude]
        p0 = float(np.mean([v for y in ys for v in blocks[y]]))
        if block is None:
            hits = [outcomes[y] for y in outcomes if y != exclude]
        else:
            hits = [blocks[y][block] for y in ys]
        k, n = sum(hits), len(hits)
        return (k + prior_strength * p0) / (n + prior_strength), p0

    p, p0 = estimate(None, None)
    preds, refs, obs = [], [], []
    for y in blocks:
        for b, o in enumerate(blocks[y]):
            pb, p0b = estimate(y, b)
            preds.append(pb); refs.append(p0b); obs.append(float(o))
    preds, refs, obs = map(np.asarray, (preds, refs, obs))
    bs = float(np.mean((preds - obs) ** 2))
    bs_ref = float(np.mean((refs - obs) ** 2))
    bss = 1 - bs / bs_ref if bs_ref > 0 else None
    k = sum(outcomes.values())
    return {
        "status": "computed",
        "label": "climatological baseline",
        "event": f"at least one satellite fire detection (consistent record) in the area between {target_start} and {target_end}",
        "window": {"start": target_start.isoformat(), "end": target_end.isoformat(), "days": horizon_days},
        "probability": round(p, 3),
        "years_with_fire_in_window": int(k),
        "years_checked": len(outcomes),
        "base_rate_any_window": round(p0, 3),
        "validation": {"method": "leave-one-year-out over non-overlapping windows", "n": int(len(obs)),
                       "brier": round(bs, 4), "brier_reference": round(bs_ref, 4),
                       "brier_skill_score": None if bss is None else round(bss, 3),
                       "reference": "constant base rate (no seasonal timing)"},
        "skill": None if bss is None else ("adds skill over the base rate" if bss > 0 else "no skill over the base rate"),
        "method": "Beta-smoothed climatology, P = (k + m*p0)/(n + m), m = %g; history: %s to %s" % (prior_strength, first, last),
    }
