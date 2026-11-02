"""Export website data from outputs already on disk (no new science, no typed numbers).

    E:\\anaconda\\envs\\flameseek\\python.exe tools\\export_site_data.py

Writes frontend/public/site-data/site.json and copies the figures the site shows.
Every value carries a label, a status and the file it came from; anything missing
is exported as {"status": "awaiting data"} instead of a number.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "frontend/public/site-data"
AWAIT = {"status": "awaiting data"}


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT)).replace("\\", "/")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def num(text: str) -> float:
    return float(text.replace(",", ""))


def value(v, label, status, source, unit=None, interval=None, note=None):
    out = {"value": v, "label": label, "status": status, "source": source}
    if unit:
        out["unit"] = unit
    if interval is not None:
        out["interval"] = interval
    if note:
        out["note"] = note
    return out


def meta():
    m = read_json(ROOT / "data/processed/snapshot_manifest.json") or {}
    keep = ("window", "data_version", "last_observation_time", "now", "now_basis", "is_live", "start", "end",
            "n_events", "n_detections", "lambda_status", "status")
    return {"default_window": m.get("default_window"),
            "windows": {w: {k: d.get(k) for k in keep} for w, d in (m.get("windows") or {}).items()},
            "source": "data/processed/snapshot_manifest.json"}


def headline():
    path = ROOT / "outputs/phase1_report.md"
    if not path.exists():
        return AWAIT
    text = path.read_text(encoding="utf-8")
    src = rel(path)

    def row(label):
        m = re.search(r"\|\s*\**" + re.escape(label) + r"[^|]*\**\s*\|\s*\**([\d,]+)\**\s*\|", text)
        return num(m.group(1)) if m else None
    raw, low, clean, events = (row("Raw rows read"), row("Low-confidence rows stored separately"),
                               row("Clean detections"), row("Fire events"))
    version = re.search(r"Data version: `([^`]+)`", text)
    return {"data_version": version.group(1) if version else None,
            "raw_detections": value(raw, "Raw FIRMS detection rows read", "computed", src),
            "low_confidence": value(low, "Low-confidence rows stored separately", "computed", src),
            "clean_detections": value(clean, "Clean detections (nominal + high confidence)", "computed", src),
            "events": value(events, "Harmonized fire events", "computed", src)}


def energy():
    path = ROOT / "outputs/phase1_report.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    before = re.search(r"before gridding: \*\*([\d,.]+) MW", text)
    after = re.search(r"after gridding: \*\*([\d,.]+) MW", text)
    rel_diff = re.search(r"Relative difference: ([\d.e+-]+) \(tolerance ([\d.e+-]+)\) -> \*\*(\w+)", text)
    if not (before and after and rel_diff):
        return AWAIT
    src = rel(path)
    return {"before": value(num(before.group(1)), "Total FRP of clean detections before gridding", "computed", src, "MW"),
            "after": value(num(after.group(1)), "Total FRP over all cell-overpass rows after gridding", "computed", src, "MW"),
            "relative_difference": value(float(rel_diff.group(1)), "Relative difference", rel_diff.group(3).lower(), src,
                                         note=f"tolerance {rel_diff.group(2)}")}


def drift():
    path = ROOT / "outputs/stages/stage2_sync.json"
    d = read_json(path)
    if not d or not d.get("drift"):
        return AWAIT
    return {"rows": [{"year": r["year"], "platform": r["platform"], "n": r["n"], "median_lst_h": r["median_lst_h"]}
                     for r in d["drift"]],
            "label": "Median daytime local solar time of detections, |latitude| ≤ 30°",
            "nominal_lst_h": 13.5, "nominal_note": "Aqua / S-NPP / NOAA-20 / NOAA-21 design crossing time 13:30",
            "status": "computed", "source": rel(path)}


def why_differ():
    """One sentence built from the measured drift rows (no typed times)."""
    d = read_json(ROOT / "outputs/stages/stage2_sync.json") or {}
    med = {(r["year"], r["platform"]): r["median_lst_h"] for r in d.get("drift", [])}
    hm = lambda h: f"{int(h):02d}:{round(h % 1 * 60):02d}"  # noqa: E731
    a26, a16, s16 = med.get((2026, "Aqua")), med.get((2016, "Aqua")), med.get((2016, "S-NPP"))
    if None in (a26, a16, s16):
        return "awaiting data"
    return (f"v1 pairs Aqua with VIIRS in 2026, when Aqua's median detection time had drifted to {hm(a26)} local solar time, "
            f"so the two sensors see the same fire at different points of its daily cycle. v2 uses 2016, when Aqua "
            f"({hm(a16)}) and S-NPP ({hm(s16)}) crossed at nearly the same time, so the fit measures sensor differences "
            f"rather than timing.")


def calibrations():
    path = ROOT / "outputs/phase3c_calibration_selection.json"
    d = read_json(path)
    if not d:
        return AWAIT
    rows = [{"version": r["version"], "n": r["sample_size"], "a": r["a"], "b": r["b"], "a_interval": r["a_interval"],
             "b_interval": r["b_interval"], "status": r["status"], "fitted": r["fitted"], "domain": r["domain"],
             "reason": r["reason"]} for r in d["calibrations"]]
    return {"rows": rows, "model": "log10 FRP_VIIRS = a + b · log10 FRP_Aqua", "interval": "90% bootstrap",
            "why_differ": why_differ(),
            "recommendations": d["recommendations"], "source": rel(path)}


def detection_limits():
    out = []
    p = ROOT / "params/detection_curve_v3_sync2016.json"
    d = read_json(p)
    if d and d["fit"].get("fitted"):
        f = d["fit"]
        out.append(value(f["f50_nadir_mw"], "MODIS (Aqua) 50% detection power at nadir, 2016", d["status"], rel(p), "MW",
                         f["f50_nadir_ci"], "logistic fit; 90% bootstrap interval"))
    else:
        out.append({**AWAIT, "label": "MODIS (Aqua) 50% detection power at nadir, 2016", "source": rel(p)})
    s = ROOT / "outputs/stages/stage2_summary.json"
    st = read_json(s) or {}
    for key, label in (("bangladesh_f50", "Himawari 50% detection power, Bangladesh viewing angle"),
                       ("near_nadir_f50", "Himawari 50% detection power, near nadir")):
        f = st.get(key)
        if f and f.get("frp50_mw") is not None:
            out.append(value(f["frp50_mw"], label, f["label"], rel(s), "MW", f["bracket_mw"],
                             "descriptive interpolation; bracket = tested grid, not a confidence interval"))
        else:
            out.append({**AWAIT, "label": label, "source": rel(s)})
    return out


def geo_assignment():
    p = ROOT / "outputs/geo_platform_assignment.json"
    d = read_json(p)
    if not d:
        return AWAIT
    return {"regions": [{"region": r["region"], "n_cells": r["n_cells"], "assignment_counts": r["assignment_counts"],
                         "mean_selected_vza_deg": r.get("mean_selected_vza_deg")} for r in d["regions"]],
            "figure": "site-data/figures/geo_platform_assignment.png",
            "label": "Geostationary platform assigned to each 0.1° cell by smallest viewing angle",
            "status": "computed (geometry only)", "source": rel(p)}


def naus():
    diag = read_json(ROOT / "outputs/naus_diagnostics/summary.json")
    fix = read_json(ROOT / "outputs/naus_detector_fix.json")
    if not diag:
        return AWAIT
    out = {"status": "method demonstration – not applied",
           "published_peak": value(diag["fits"]["as_published"]["peak_h"], "Published diurnal peak (local solar time)",
                                   "detection artifact (D71)", "outputs/naus_diagnostics/summary.json", "h",
                                   diag["fits"]["as_published"]["peak_90"]),
           "findings": [
               "The daytime split-window cloud test classed clear hot land as cloud, so the fit had no mid-day data.",
               "Evening detections are real fire locations; the published evening peak is where visibility returns, not a burning peak.",
               "Replacing that cloud test with a near-infrared (B04) reflectance test un-hid daytime fires (cloud fix works).",
               "Daytime false alarms remain: most new midday detections are never confirmed by polar satellites.",
           ],
           "source": "outputs/naus_diurnal_check.md; outputs/naus_detector_fix.md"}
    if fix:
        b, a, c = fix["test_before"], fix["test_after"], fix["checks"]
        src = "outputs/naus_detector_fix.json"
        out["checks"] = [
            {"label": "VIIRS fires at 12–14 h classed as cloud (test days)", "before": b["M1_cloud_share_viirs_12_14h"],
             "after": a["M1_cloud_share_viirs_12_14h"], "passed": c["C1_cloud_gap_halved"], "unit": "share", "source": src},
            {"label": "Daytime detection rate, VIIRS fires ≥ 20 MW (test days)", "before": b["M2_day_detection_by_frp"][-1]["rate"],
             "after": a["M2_day_detection_by_frp"][-1]["rate"], "passed": c["C2_rate_rises_with_frp_and_top_bin_up"],
             "unit": "share", "source": src},
            {"label": "Midday Himawari detections never confirmed (test days)", "before": b["M3_never_confirmed_share_09_13h"],
             "after": a["M3_never_confirmed_share_09_13h"], "passed": c["C3_never_confirmed_down_20pts_and_le_50pct"],
             "unit": "share", "source": src, "n_before": b["M3_n"], "n_after": a["M3_n"]}]
    out["figure"] = "site-data/figures/naus_diurnal_diagnostics.png"
    return out


def awaiting():
    items = []
    gate = read_json(ROOT / "outputs/stages/stage5_sync_gate.json") or {}
    opp = ((gate.get("windows") or {}).get("sync_2016") or {}).get("opportunities") or {}
    if "TLE" not in str(opp.get("basis", "")):
        items.append({"item": "Archived 2016 orbital elements (TLEs)",
                      "effect": "2016 observation opportunities are a lower bound, so 2016 λ is biased high",
                      "status": opp.get("basis", "awaiting data")})
    met = (read_json(ROOT / "outputs/phase3c_status.json") or {}).get("part_d", {})
    if met.get("status") != "completed":
        items.append({"item": "Meteosat LSA SAF FRP-PIXEL for South Asia",
                      "effect": "No South Asia diurnal shape, South Asia transfer calibration or FRE",
                      "status": met.get("status", "awaiting data")})
    g14 = ((gate.get("windows") or {}).get("sync_2014") or {}).get("gate", {})
    if g14.get("status") != "evaluated":
        items.append({"item": "FIRMS 2014 synchronized window", "effect": "No second window to check calibration v2 against",
                      "status": g14.get("status", "awaiting data")})
    items.append({"item": "Northern Australia daytime detector", "effect": "Diurnal curve, transfer and FRE there are not applied",
                  "status": "limitation after one fix round (D74)"})
    return items


def translation():
    from pipeline import translate
    return {"words": translate.WORDS, "status": "provisional display rules", "source": "pipeline/translate.py"}


SOURCES = [
    {"name": "NASA FIRMS (MODIS C6.1 and VIIRS 375 m active fire)", "url": "https://firms.modaps.eosdis.nasa.gov/",
     "use": "Fire detections, current 2026 window and 2016 archive"},
    {"name": "NOAA Open Data Dissemination – Himawari-9 AHI on AWS", "url": "https://registry.opendata.aws/noaa-himawari/",
     "use": "Geostationary bands B04, B07, B14, B15 for Northern Australia and Bangladesh"},
    {"name": "CelesTrak orbital elements", "url": "https://celestrak.org/", "use": "2026 observation opportunities"},
    {"name": "EUMETSAT LSA SAF (Meteosat FRP-PIXEL)", "url": "https://lsa-saf.eumetsat.int/",
     "use": "Planned South Asia geostationary source — awaiting data"},
    {"name": "Esri World Imagery and reference labels", "url": "https://www.esri.com/",
     "use": "Fire Events map basemap (same tiles as the Fire DNA page)"},
]


def cfg():
    from pipeline.config import load_settings
    return load_settings()


def regions():
    c = cfg()
    boxes = c["overpasses"]["pilot_boxes"]
    return {"Indo-Gangetic Plain": boxes["Indo-Gangetic Plain"], "Bangladesh": boxes["Bangladesh"],
            "Northern Australia": c["phase3c"]["northern_australia"]["box"]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "figures").mkdir(exist_ok=True)
    for name in ("geo_platform_assignment.png", "naus_diurnal_diagnostics.png"):
        src = ROOT / "outputs/figures" / name
        if src.exists():
            shutil.copy2(src, OUT / "figures" / name)
    site = {"exported_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "meta": meta(), "headline": headline(), "energy": energy(), "drift": drift(),
            "calibration": calibrations(), "detection_limits": detection_limits(),
            "geo_assignment": geo_assignment(), "naus": naus(), "awaiting": awaiting(),
            "translation": translation(), "sources": SOURCES,
            "regions": regions(),
            "regions_source": "config/settings.yaml (overpasses.pilot_boxes, phase3c.northern_australia.box)",
            "intensity_classes_mw": cfg()["translation"]["intensity_mw"],
            "intensity_source": "config/settings.yaml (translation.intensity_mw)"}
    (OUT / "site.json").write_text(json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {rel(OUT / 'site.json')}")
    return site


if __name__ == "__main__":
    main()
