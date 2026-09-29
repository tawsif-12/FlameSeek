"""Fire Identity: group detections into evolving fire events and infer behaviour.

Two detections are linked when they are close in time (<= 48 h) and their
separation is within both pixels' location uncertainty plus a spread allowance
that grows with the time gap (a fire front can move between overpasses). Linked
components are one Fire Event. Behaviour labels are *Inferred Fire Behaviour
States* derived from detections, not measurements of physical fire spread.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import log1p
from typing import Any

from geo import IncrementalExtent, bearing_deg, detections_extent_km2, haversine_km, hull_lonlat, location_uncertainty_km
from quality import sensor_family


MAX_GAP_HOURS = 48.0
SPREAD_ALLOWANCE_KM_PER_DAY = 2.0
MAX_LINK_KM = 6.0
HASH_DEG = 0.06
MAX_BUCKET_CHECKS = 48
BIN_HOURS = 12


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def link_threshold_km(a: dict[str, Any], b: dict[str, Any], gap_hours: float) -> float:
    base = a["_unc"] + b["_unc"] + 0.5
    return min(MAX_LINK_KM, base + SPREAD_ALLOWANCE_KM_PER_DAY * gap_hours / 24)


def reconstruct_events(
    hotspots: list[dict[str, Any]],
    reference_time: datetime | None = None,
    min_detections: int = 1,
) -> list[dict[str, Any]]:
    rows = []
    for row in hotspots:
        item = dict(row)
        item["_t"] = _as_datetime(row["acq_datetime"])
        item["_unc"] = location_uncertainty_km(row)
        rows.append(item)
    rows.sort(key=lambda r: r["_t"])
    n = len(rows)
    uf = _UnionFind(n)
    link_strength: dict[int, float] = defaultdict(float)
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)

    for i, row in enumerate(rows):
        gi, gj = int(row["lat"] // HASH_DEG), int(row["lon"] // HASH_DEG)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                bucket = grid.get((gi + di, gj + dj))
                if not bucket:
                    continue
                # Buckets are time-ordered; walk back until the gap exceeds the window.
                # Inside dense fires the recent members already form one component, so
                # checking the latest MAX_BUCKET_CHECKS keeps linking near-linear.
                for checked, j in enumerate(reversed(bucket)):
                    if checked >= MAX_BUCKET_CHECKS:
                        break
                    other = rows[j]
                    gap = (row["_t"] - other["_t"]).total_seconds() / 3600
                    if gap > MAX_GAP_HOURS:
                        break
                    if uf.find(i) == uf.find(j):
                        link_strength[i] = max(link_strength[i], 0.75)
                        continue
                    dist = haversine_km(row["lat"], row["lon"], other["lat"], other["lon"])
                    limit = link_threshold_km(row, other, gap)
                    if dist <= limit:
                        uf.union(i, j)
                        strength = 1 - 0.5 * dist / limit
                        link_strength[i] = max(link_strength[i], strength)
                        link_strength[j] = max(link_strength[j], strength)
        grid[(gi, gj)].append(i)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)

    ref = reference_time or datetime.now(timezone.utc)
    events = []
    for members in groups.values():
        if len(members) < min_detections:
            continue
        det = [rows[i] for i in members]
        events.append(_summarize_event(det, [link_strength[i] for i in members], ref))
    events.sort(key=lambda e: e["total_frp"], reverse=True)
    return events


def _event_id(first: dict[str, Any]) -> str:
    raw = f"{first['_t'].isoformat()}|{first['lat']:.3f}|{first['lon']:.3f}"
    return "EV-" + hashlib.sha1(raw.encode()).hexdigest()[:10].upper()


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _summarize_event(det: list[dict[str, Any]], strengths: list[float], ref: datetime) -> dict[str, Any]:
    det.sort(key=lambda r: r["_t"])
    first, last = det[0], det[-1]
    frps = [float(r["frp"]) for r in det if r.get("frp") is not None]
    total_frp = sum(frps)
    weights = [max(float(r.get("frp") or 0), 0.1) for r in det]
    wsum = sum(weights)
    centroid = (sum(r["lat"] * w for r, w in zip(det, weights)) / wsum, sum(r["lon"] * w for r, w in zip(det, weights)) / wsum)
    sensors = sorted({str(r["sensor"]) for r in det})
    families = sorted({sensor_family(s) for s in sensors})
    n = len(det)

    if n == 1:
        confidence, conf_note = None, "Single detection: no association to assess."
    else:
        mean_strength = sum(strengths) / n
        confidence = min(0.99, 0.35 + 0.35 * mean_strength + (0.15 if len(families) > 1 else 0) + 0.15 * min(1.0, n / 10))
        confidence = round(confidence, 2)
        conf_note = "Heuristic: how tightly detections are linked in space and time, with credit for multi-sensor agreement and more observations."

    bins = behaviour_bins(det)
    behaviour = infer_behaviour(det, bins, ref)
    lats = [r["lat"] for r in det]
    lons = [r["lon"] for r in det]
    return {
        "event_id": _event_id(first),
        "first_detection": first["_t"],
        "latest_detection": last["_t"],
        "duration_hours": round((last["_t"] - first["_t"]).total_seconds() / 3600, 2),
        "observation_count": n,
        "sensors": sensors,
        "sensor_families": families,
        "satellites": sorted({str(r.get("satellite") or "") for r in det} - {""}),
        "total_frp": round(total_frp, 2),
        "max_frp": round(max(frps), 2) if frps else None,
        "frp_trend": behaviour["metrics"].get("frp_trend"),
        "centroid": {"lat": round(centroid[0], 5), "lon": round(centroid[1], 5)},
        "bbox": [min(lons), min(lats), max(lons), max(lats)],
        "extent_km2": detections_extent_km2(det),
        "max_span_km": round(max((haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) for a in det[:200] for b in det[:200]), default=0.0), 2),
        "hull": hull_lonlat(det),
        "association_confidence": confidence,
        "association_note": conf_note,
        "behaviour": behaviour,
        "timeline": bins,
        "detections": [_clean(r) for r in det],
    }


def behaviour_bins(det: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per 12 h overpass window: detections, FRP, cumulative extent, centroid."""
    start = det[0]["_t"]
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in det:
        buckets[int((r["_t"] - start).total_seconds() // (BIN_HOURS * 3600))].append(r)
    out = []
    extent = IncrementalExtent(det[0]["lat"], det[0]["lon"])
    for idx in sorted(buckets):
        rows = buckets[idx]
        frp = sum(float(r.get("frp") or 0) for r in rows)
        out.append(
            {
                "window_start": (start + timedelta(hours=idx * BIN_HOURS)).isoformat(),
                "detections": len(rows),
                "total_frp": round(frp, 2),
                "cumulative_extent_km2": extent.add(rows),
                "centroid": [round(sum(r["lat"] for r in rows) / len(rows), 5), round(sum(r["lon"] for r in rows) / len(rows), 5)],
                "sensors": sorted({str(r["sensor"]) for r in rows}),
            }
        )
    return out


def _slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mx = (n - 1) / 2
    my = sum(values) / n
    den = sum((i - mx) ** 2 for i in range(n))
    return sum((i - mx) * (v - my) for i, v in enumerate(values)) / den if den else 0.0


def infer_behaviour(det: list[dict[str, Any]], bins: list[dict[str, Any]], ref: datetime) -> dict[str, Any]:
    first, last = det[0]["_t"], det[-1]["_t"]
    age_h = (ref - first).total_seconds() / 3600
    since_last_h = (ref - last).total_seconds() / 3600
    recent = bins[-4:]
    frp_series = [log1p(b["total_frp"]) for b in recent]
    frp_slope = _slope(frp_series)
    last_frp = recent[-1]["total_frp"]
    prev_frp = sum(b["total_frp"] for b in recent[:-1]) / max(1, len(recent) - 1) if len(recent) > 1 else None
    frp_ratio = (last_frp / prev_frp) if prev_frp else None
    ext_prev = bins[-2]["cumulative_extent_km2"] if len(bins) > 1 else 0.0
    ext_last = bins[-1]["cumulative_extent_km2"]
    growth = (ext_last / ext_prev) if ext_prev else None
    active_days = len({r["_t"].date() for r in det})
    move_km = haversine_km(bins[0]["centroid"][0], bins[0]["centroid"][1], bins[-1]["centroid"][0], bins[-1]["centroid"][1]) if len(bins) > 1 else 0.0
    move_bearing = bearing_deg(bins[0]["centroid"][0], bins[0]["centroid"][1], bins[-1]["centroid"][0], bins[-1]["centroid"][1]) if move_km > 0.5 else None

    reasons = []
    if age_h <= 24 and len(bins) <= 2:
        state = "Onset"
        reasons.append(f"First detected {age_h:.0f} h ago with {len(det)} detection(s).")
    elif since_last_h > 36:
        state = "Decaying" if (frp_ratio is not None and frp_ratio < 1) or len(bins) > 1 else "Uncertain"
        reasons.append(f"No detection for {since_last_h:.0f} h; the fire may have weakened, or cloud/overpass gaps may be hiding it.")
    elif len(det) < 3 or len(bins) < 2:
        state = "Uncertain"
        reasons.append("Too few observations to infer a trend.")
    elif growth is not None and growth >= 1.3 and ext_last - ext_prev >= 1.0:
        state = "Expanding"
        reasons.append(f"Detection extent grew from {ext_prev:.1f} to {ext_last:.1f} km2 in the latest overpass window.")
    elif frp_ratio is not None and frp_ratio >= 1.5 and last_frp >= 20:
        state = "Intensifying"
        reasons.append(f"Latest-window FRP {last_frp:.0f} MW is {frp_ratio:.1f}x the preceding windows.")
    elif frp_ratio is not None and frp_ratio <= 0.5:
        state = "Decaying"
        reasons.append(f"Latest-window FRP fell to {frp_ratio:.0%} of the preceding windows.")
    elif active_days >= 3:
        state = "Persistent"
        reasons.append(f"Detected on {active_days} separate days with no strong trend.")
    else:
        state = "Stable"
        reasons.append("FRP and extent roughly steady across recent overpass windows.")
    if move_bearing is not None:
        reasons.append(f"Detection centroid shifted {move_km:.1f} km toward {move_bearing:.0f} deg.")

    return {
        "state": state,
        "label_type": "Inferred Fire Behaviour State",
        "reasons": reasons,
        "metrics": {
            "age_hours": round(age_h, 1),
            "hours_since_last_detection": round(since_last_h, 1),
            "overpass_windows": len(bins),
            "active_days": active_days,
            "frp_trend": "rising" if frp_slope > 0.25 else "falling" if frp_slope < -0.25 else "flat",
            "frp_log_slope_per_window": round(frp_slope, 3),
            "latest_to_previous_frp_ratio": round(frp_ratio, 3) if frp_ratio is not None else None,
            "extent_growth_ratio": round(growth, 3) if growth is not None else None,
            "centroid_movement_km": round(move_km, 2),
            "centroid_movement_bearing_deg": round(move_bearing, 1) if move_bearing is not None else None,
        },
        "caveat": "Inferred from satellite detections (FRP, count, extent, persistence, movement). Not a direct measurement of fire spread.",
    }


def event_summary(event: dict[str, Any]) -> dict[str, Any]:
    """Compact form for map layers (no per-detection payload)."""
    return {k: v for k, v in event.items() if k not in {"detections", "timeline"}}
