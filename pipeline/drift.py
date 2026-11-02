"""Phase 2b: overpass-time drift history for the MODIS and VIIRS platforms.

For every year, the same sample is taken: daytime FIRMS detections on
`window_start` + `window_days` (late October, the season of the 2026 data) in
the band |lat| <= `lat_band`. 2013-2025 come from the FIRMS standard-processing
(SP) archive; 2026 comes from the local Phase 2 data (data/raw), so it uses the
same method.

Per platform and year:
  lst_median   median local solar time, lst = (h_UTC + lon/15) mod 24
Per year:
  aqua_snpp_dt median |Δt| between an Aqua detection and the nearest S-NPP
               detection of the same fire (<= pair_radius_km, same UTC day, daytime)

Derived:
  first_drift_year  first year a MODIS platform's median LST is more than
                    drift_threshold_min from its early-archive value (median of
                    the baseline years)
  calibration years years with aqua_snpp_dt <= calib_max_dt_min and enough pairs
"""
from __future__ import annotations

import io
import re
import time
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.neighbors import BallTree  # noqa: E402

from pipeline.config import ROOT  # noqa: E402
from pipeline.figures import GRID, INK, INK2, PLATFORM_COLORS, SURFACE, _style  # noqa: E402
from pipeline.inspect_raw import PLATFORM_CODES, parse_acq_date, read_firms_csv  # noqa: E402

API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{area}/{days}/{date}"
SOURCES = {"MODIS_SP": 2000, "VIIRS_SNPP_SP": 2012, "VIIRS_NOAA20_SP": 2018, "VIIRS_NOAA21_SP": 2023}


def map_key() -> str:
    import os
    k = os.environ.get("FIRMS_MAP_KEY")
    if not k:
        env = ROOT / "backend" / ".env"
        m = re.search(r"^FIRMS_MAP_KEY=(.+)$", env.read_text(), re.M) if env.exists() else None
        k = m.group(1).strip() if m else None
    if not k:
        raise RuntimeError("FIRMS_MAP_KEY not set (environment or backend/.env)")
    return k


def fetch_year(source: str, year: int, d: dict, cache_dir: Path) -> Path | None:
    """Download one archive sample once; cached files are never modified again."""
    start = f"{year}-{d['window_start']}"
    area = f"-180,{-d['lat_band']},180,{d['lat_band']}"
    out = cache_dir / f"{source}_{start}_{d['window_days']}d_lat{d['lat_band']}.csv"
    if out.exists() and out.stat().st_size > 0:
        return out
    url = API.format(key=map_key(), source=source, area=area, days=d["window_days"], date=start)
    req = urllib.request.Request(url, headers={"User-Agent": "FlameSeek/1.0 (research pipeline)"})
    for attempt in range(3):
        try:
            text = urllib.request.urlopen(req, timeout=180).read().decode()
            break
        except Exception as exc:  # network hiccup or rate limit
            if attempt == 2:
                print(f"[drift] {source} {year}: download failed ({type(exc).__name__})")
                return None
            time.sleep(5 * (attempt + 1))
    if not text.lstrip().startswith("latitude"):
        print(f"[drift] {source} {year}: unexpected reply: {text[:80]!r}")
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


def load_sample(path: Path, year: int, d: dict) -> pd.DataFrame:
    df = read_firms_csv(path)
    date = parse_acq_date(df["acq_date"])
    start = pd.Timestamp(f"{year}-{d['window_start']}")
    keep = date.between(start, start + pd.Timedelta(days=d["window_days"] - 1)) & df["latitude"].abs().le(d["lat_band"])
    df, date = df[keep], date[keep]
    hhmm = pd.to_numeric(df["acq_time"], errors="coerce")
    t = date + pd.to_timedelta(hhmm // 100, unit="h") + pd.to_timedelta(hhmm % 100, unit="m")
    out = pd.DataFrame({"platform": df["satellite"].astype(str).str.strip().map(PLATFORM_CODES),
                        "t": t, "lat": df["latitude"], "lon": df["longitude"],
                        "daynight": df["daynight"].astype(str).str.upper(), "year": year})
    out["lst"] = (out["t"].dt.hour + out["t"].dt.minute / 60 + out["lon"] / 15) % 24
    return out[out["daynight"] == "D"].dropna(subset=["platform", "t"])


def pair_dt(df: pd.DataFrame, radius_km: float) -> tuple[float, int]:
    """Median |Δt| (min) between each Aqua detection and the nearest S-NPP detection of the
    same UTC day within radius_km."""
    a, s = df[df["platform"] == "Aqua"], df[df["platform"] == "S-NPP"]
    dts = []
    for day, ad in a.groupby(a["t"].dt.date):
        sd = s[s["t"].dt.date == day]
        if sd.empty:
            continue
        tree = BallTree(np.radians(sd[["lat", "lon"]].to_numpy()), metric="haversine")
        dist, idx = tree.query(np.radians(ad[["lat", "lon"]].to_numpy()), k=1)
        ok = dist[:, 0] * 6371.0088 <= radius_km
        dt = (sd["t"].to_numpy()[idx[ok, 0]] - ad["t"].to_numpy()[ok]) / np.timedelta64(1, "m")
        dts.append(np.abs(dt))
    if not dts:
        return np.nan, 0
    v = np.concatenate(dts)
    return (float(np.median(v)), len(v)) if len(v) else (np.nan, 0)


def history(cfg: dict) -> dict:
    d = cfg["drift"]
    cache = ROOT / d["archive_dir"]
    frames = []
    for year in range(d["first_year"], d["last_archive_year"] + 1):
        for source, first in SOURCES.items():
            if year < first:
                continue
            p = fetch_year(source, year, d, cache)
            if p is not None:
                frames.append(load_sample(p, year, d))
    # The current year from the local Phase 2 files (same window and band).
    cur = []
    for f in sorted(cfg["paths"]["raw_dir"].glob("*.csv")):
        cur.append(load_sample(f, d["current_year"], d))
    frames += cur
    det = pd.concat(frames, ignore_index=True)

    lst = (det.groupby(["year", "platform"])["lst"].agg(["median", "size"])
              .rename(columns={"median": "lst_median", "size": "n_day_detections"}).reset_index())
    pairs = pd.DataFrame([{"year": y, **dict(zip(("aqua_snpp_dt_median_min", "n_pairs"),
                                                  pair_dt(g, d["pair_radius_km"])))}
                          for y, g in det.groupby("year")])

    first_drift, baseline = {}, {}
    for plat in ("Terra", "Aqua", "S-NPP"):
        s = lst[lst["platform"] == plat].set_index("year")["lst_median"]
        base = float(s.loc[[y for y in d["baseline_years"] if y in s.index]].median())
        baseline[plat] = base
        moved = s[(s - base).abs() * 60 > d["drift_threshold_min"]]
        first_drift[plat] = int(moved.index.min()) if len(moved) else None

    calib = pairs[(pairs["aqua_snpp_dt_median_min"] <= d["calib_max_dt_min"])
                  & (pairs["n_pairs"] >= d["min_pairs_per_year"])]["year"].astype(int).tolist()
    return {"lst": lst, "pairs": pairs, "baseline": baseline, "first_drift": first_drift,
            "calibration_years": calib, "n_detections": len(det)}


def hhmm(h: float) -> str:
    if not np.isfinite(h):
        return "–"
    m = int(round(h * 60)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def plot(res: dict, phase2_ref: dict, out: Path, cfg: dict) -> None:
    d = cfg["drift"]
    lst = res["lst"]
    fig, ax = plt.subplots(figsize=(10, 5), facecolor=SURFACE)
    _style(ax)
    for plat in ("Terra", "Aqua", "S-NPP", "NOAA-20", "NOAA-21"):
        s = lst[lst["platform"] == plat].sort_values("year")
        if s.empty:
            continue
        ax.plot(s["year"], s["lst_median"], color=PLATFORM_COLORS[plat], linewidth=2, marker="o",
                markersize=5, label=plat)
        last = s.iloc[-1]
        if plat in ("Terra", "Aqua"):
            ax.annotate(f"{plat} {hhmm(last['lst_median'])}", (last["year"], last["lst_median"]),
                        xytext=(6, 0), textcoords="offset points", va="center", fontsize=8, color=INK)
    v = lst[(lst["year"] == lst["year"].max()) & lst["platform"].isin(["S-NPP", "NOAA-20", "NOAA-21"])]["lst_median"]
    if len(v):
        ax.annotate(f"VIIRS {hhmm(v.min())}–{hhmm(v.max())}", (lst["year"].max(), v.mean()), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=8, color=INK)
    for plat, h in phase2_ref.items():
        ax.scatter([d["current_year"]], [h], marker="D", s=40, facecolor="none",
                   edgecolor=PLATFORM_COLORS.get(plat, INK2), linewidth=1.3, zorder=4)
    ax.scatter([], [], marker="D", facecolor="none", edgecolor=INK2, label="2026 computed overpass (Phase 2)")
    years = sorted({y for p, y in res["first_drift"].items() if y and p in ("Terra", "Aqua")})
    for y0 in years:
        who = " & ".join(p for p in ("Terra", "Aqua") if res["first_drift"].get(p) == y0)
        ax.axvline(y0 - 0.5, color=INK2, linestyle=":", linewidth=1)
        ax.text(y0 - 0.45, 16.85, f"{who} drifted\n(> 30 min) from {y0}", fontsize=7.5, color=INK2, va="top")
    for y in res["calibration_years"]:
        ax.axvspan(y - 0.5, y + 0.5, color=GRID, alpha=0.6, zorder=0, linewidth=0)
    ax.set_yticks(range(8, 18))
    ax.set_yticklabels([f"{h:02d}:00" for h in range(8, 18)])
    ax.set_ylim(7.5, 17)
    ax.set_xlim(d["first_year"] - 0.6, d["current_year"] + 1.4)
    ax.set_xlabel("Year (late-October sample)", color=INK2, fontsize=8.5)
    ax.set_ylabel("Median local solar time of daytime detections", color=INK2, fontsize=8.5)
    ax.set_title("Overpass time drift: median local solar time per platform and year. Shaded = calibration "
                 "years; dotted = first drifted year", color=INK, fontsize=9.5, loc="left")
    leg = ax.legend(fontsize=8, frameon=False, loc="upper left", ncol=3, bbox_to_anchor=(0.0, 0.93))
    for t in leg.get_texts():
        t.set_color(INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)
