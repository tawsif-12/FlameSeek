"""Summaries of retrieved records without inferred passes or detection chances."""
from collections import defaultdict
from datetime import datetime, timezone
import math

LABELS = {"terra": "Terra MODIS", "aqua": "Aqua MODIS", "snpp": "Suomi NPP VIIRS", "noaa20": "NOAA-20 VIIRS", "noaa21": "NOAA-21 VIIRS", "modis_unknown": "MODIS (platform unspecified)"}


def summarize_records(rows, daily, failed_chunks):
    by_platform = defaultdict(list)
    for row in rows:
        sensor = str(row.get("sensor", ""))
        if sensor == "modis":
            satellite = str(row.get("satellite") or "").strip().lower()
            key = "terra" if satellite.startswith("t") else "aqua" if satellite.startswith("a") else "modis_unknown"
        else:
            key = {"viirs_snpp": "snpp", "viirs_noaa20": "noaa20", "viirs_noaa21": "noaa21"}.get(sensor)
        if key is None:
            continue
        stamp = row["acq_datetime"]
        if isinstance(stamp, str):
            stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        by_platform[key].append(stamp.astimezone(timezone.utc))
    platforms = []
    for key, stamps in by_platform.items():
        platforms.append({"id": key, "label": LABELS[key], "detections": len(stamps), "detection_days": len({t.date() for t in stamps}), "first_detection": min(stamps).isoformat(), "last_detection": max(stamps).isoformat()})
    both = sum(d["modis_count"] > 0 and d["viirs_count"] > 0 for d in daily)
    one = sum((d["modis_count"] > 0) != (d["viirs_count"] > 0) for d in daily)
    cloud_days = sum(isinstance(d["observation"].get("cloud_cover_pct"), (int, float)) and math.isfinite(d["observation"]["cloud_cover_pct"]) for d in daily)
    return {
        "version": 1,
        "source": "NASA FIRMS retrieved records after confidence filtering; dates are UTC. Counts are satellite detections, not unique fires.",
        "platforms": sorted(platforms, key=lambda p: p["id"]),
        "days": {"both_families_detected": both, "one_family_detected": one, "no_detections_in_retrieved_records": len(daily) - both - one},
        "cloud_proxy_days": cloud_days,
        "total_days": len(daily),
        "failed_download_chunks": len(failed_chunks),
        "coverage_status": "unavailable",
        "coverage_note": "Actual satellite observation masks are not connected. Retrieved records cannot establish clear views, missed passes, fire absence, or detection probability. Cloud values are ERA5 estimates at the area centre, not satellite cloud masks.",
    }
