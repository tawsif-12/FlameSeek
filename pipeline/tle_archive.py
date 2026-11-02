"""Archived TLEs for historical windows (data/raw/tle/<year>/, from tools/fetch_spacetrack_tle.py).

A platform is usable only when a TLE epoch lies within `max_epoch_offset_days` of the
window midpoint. Accepted TLEs are propagated with the same Step 6A code as 2026.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from pipeline.config import ROOT


def tle_epoch(line1: str) -> pd.Timestamp:
    yy, doy = int(line1[18:20]), float(line1[20:32])
    year = 2000 + yy if yy < 57 else 1900 + yy
    return pd.Timestamp(datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1))


def parse(path: Path) -> list[dict]:
    lines = [ln.rstrip() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    out = []
    for i, ln in enumerate(lines[:-1]):
        nxt = lines[i + 1]
        if ln.startswith("1 ") and nxt.startswith("2 ") and ln[2:7] == nxt[2:7]:
            out.append({"norad_id": int(ln[2:7]), "line1": ln, "line2": nxt,
                        "epoch": tle_epoch(ln), "source": f"{path.relative_to(ROOT)} (archive)"})
    return out


def select(cfg: dict) -> dict:
    """{'tles': {platform: tle}, 'missing': {platform: reason}, 'files': [...]} for cfg['window']."""
    a, w = cfg["tle_archive"], cfg["window"]
    mid = pd.Timestamp(w["start"], tz="UTC") + (pd.Timestamp(w["end"], tz="UTC") + pd.Timedelta(days=1)
                                                 - pd.Timestamp(w["start"], tz="UTC")) / 2
    folder = ROOT / a["dir"] / str(w["start"].year)
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".tle", ".txt", ".3le", ".2le")) if folder.exists() else []
    records = [r for f in files for r in parse(f)]
    ids = cfg["overpasses"]["norad_ids"]
    tles, missing = {}, {}
    for plat in a["platforms"]:
        cand = [r for r in records if r["norad_id"] == ids[plat]]
        if not cand:
            missing[plat] = f"no TLE for NORAD {ids[plat]} in {folder.relative_to(ROOT)}"
            continue
        best = min(cand, key=lambda r: abs(r["epoch"] - mid))
        off = abs(best["epoch"] - mid)
        if off > pd.Timedelta(days=a["max_epoch_offset_days"]):
            missing[plat] = f"nearest epoch {best['epoch']} is {off} from window midpoint"
            continue
        tles[plat] = {**best, "platform": plat}
    return {"tles": tles, "missing": missing, "files": [str(f.relative_to(ROOT)) for f in files],
            "complete": not missing}


def compute(cfg: dict, cells: pd.DataFrame, t0, t1, tles: dict) -> pd.DataFrame:
    from pipeline import overpasses
    frames = [overpasses.passes_for_platform(p, t, cells, t0, t1, cfg) for p, t in tles.items()]
    ov = pd.concat([f for f in frames if len(f)], ignore_index=True)
    ov["cloud_adjusted"] = bool(cfg["overpasses"]["cloud_adjusted"])
    ov["opportunity_basis"] = "TLE-propagated (archived epoch)"
    return ov
