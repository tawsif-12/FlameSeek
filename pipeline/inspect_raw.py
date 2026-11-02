"""Task 3: describe every raw file before anything is processed.

The sensor of each row is read from the `instrument` column, never from the
file name. The report also flags files that are byte-identical copies of each
other and files whose name disagrees with their content.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import pandas as pd

PLATFORM_CODES = {"N": "S-NPP", "N20": "NOAA-20", "N21": "NOAA-21",
                  "Terra": "Terra", "T": "Terra", "Aqua": "Aqua", "A": "Aqua"}


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_firms_csv(path: Path) -> pd.DataFrame:
    """Read a FIRMS CSV as text-safe columns (utf-8-sig strips the BOM FIRMS exports carry)."""
    return pd.read_csv(path, encoding="utf-8-sig", dtype={"satellite": str, "confidence": str,
                                                           "version": str, "daynight": str})


def parse_acq_date(s: pd.Series) -> pd.Series:
    """FIRMS writes YYYY-MM-DD; files re-saved by Excel use M/D/YYYY. Accept both."""
    iso = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    us = pd.to_datetime(s, format="%m/%d/%Y", errors="coerce")
    return iso.fillna(us)


def _fmt_counts(series: pd.Series) -> str:
    vc = series.fillna("<blank>").astype(str).value_counts().sort_index()
    return ", ".join(f"`{k}`: {v}" for k, v in vc.items())


def inspect_firms(raw_dir: Path) -> tuple[list[str], dict]:
    lines: list[str] = []
    facts: dict = {"files": {}, "problems": []}
    files = sorted(raw_dir.glob("*.csv"))
    if not files:
        facts["problems"].append(f"No CSV files found in {raw_dir}.")
        return [f"No CSV files in `{raw_dir}`."], facts

    hashes = defaultdict(list)
    sensors_present = set()
    for f in files:
        df = read_firms_csv(f)
        digest = md5(f)
        hashes[digest].append(f.name)
        blank = df["latitude"].isna() | df["acq_date"].isna()
        d = parse_acq_date(df["acq_date"])
        instruments = sorted(df["instrument"].dropna().unique())
        sensors_present.update(instruments)
        facts["files"][f.name] = {"rows": len(df), "blank_rows": int(blank.sum()),
                                  "instruments": instruments, "md5": digest}

        lines += [f"### `{f.name}`", "",
                  f"- Rows: **{len(df)}** (of which {int(blank.sum())} blank/unparseable)",
                  f"- MD5: `{digest}`",
                  f"- Columns ({len(df.columns)}): {', '.join(df.columns)}",
                  f"- Date range (acq_date): {d.min():%Y-%m-%d} to {d.max():%Y-%m-%d}"
                  f" ({d.dt.date.nunique()} day(s)); raw date format example `{df['acq_date'].dropna().iloc[0]}`",
                  f"- acq_time range (HHMM UTC): {int(df['acq_time'].min())} to {int(df['acq_time'].max())}",
                  f"- `instrument`: {_fmt_counts(df['instrument'])}",
                  f"- `satellite`: {_fmt_counts(df['satellite'])}",
                  f"- `version`: {_fmt_counts(df['version'])}",
                  f"- `confidence`: {_fmt_counts(df['confidence'])}",
                  f"- scan: {df['scan'].min()} to {df['scan'].max()} km; "
                  f"track: {df['track'].min()} to {df['track'].max()} km",
                  f"- Latitude {df['latitude'].min()} to {df['latitude'].max()}; "
                  f"longitude {df['longitude'].min()} to {df['longitude'].max()}",
                  f"- `type` column present: {'yes' if 'type' in df.columns else 'no (NRT file)'}"]

        # Detections per platform per day, platform decided from the content.
        ok = df[~blank].assign(day=d[~blank].dt.strftime("%Y-%m-%d"),
                               platform=df["satellite"].map(PLATFORM_CODES).fillna(df["satellite"]))
        ppd = ok.groupby(["platform", "day"]).size()
        lines.append("- Detections per platform per day: " +
                     "; ".join(f"{p} {day}: {n}" for (p, day), n in ppd.items()))

        # Name vs content check.
        name = f.name.lower()
        if "modis" in name and "MODIS" not in instruments:
            msg = (f"`{f.name}` is named MODIS but its `instrument` column says "
                   f"{instruments}; it is treated as {instruments} data.")
            facts["problems"].append(msg)
            lines.append(f"- **Problem:** {msg}")
        if "viirs" in name and "VIIRS" not in instruments:
            msg = f"`{f.name}` is named VIIRS but contains {instruments}."
            facts["problems"].append(msg)
            lines.append(f"- **Problem:** {msg}")
        if blank.any():
            msg = f"`{f.name}` has {int(blank.sum())} blank row(s); removed in Step 2 with a reason code."
            facts["problems"].append(msg)
        lines.append("")

    for digest, names in hashes.items():
        if len(names) > 1:
            msg = (f"Files {', '.join(f'`{n}`' for n in names)} are byte-identical (MD5 {digest}). "
                   "Their rows are duplicates; Step 2 keeps one copy of each detection.")
            facts["problems"].append(msg)

    facts["sensors_present"] = sorted(sensors_present)
    if "MODIS" not in sensors_present:
        msg = ("**No MODIS data is present.** No raw row has instrument = MODIS, so the run "
               "continues with VIIRS only. MODIS_only/both events, Aqua-VIIRS pairs and MODIS "
               "footprint ranges cannot be produced until real MODIS files are added.")
        facts["problems"].insert(0, msg)
    return lines, facts


def inspect_himawari(him_dir: Path) -> list[str]:
    """List what is in the Himawari folder so the later Himawari step can be planned."""
    if not him_dir.exists():
        return [f"`{him_dir.name}/` does not exist under `data/raw/`. No Himawari data is present yet, "
                "so file count, format, time range, bands and segments cannot be listed."]
    files = [p for p in him_dir.rglob("*") if p.is_file()]
    if not files:
        return [f"`{him_dir}` exists but is empty."]
    exts = pd.Series([p.suffix.lower() or "<none>" for p in files]).value_counts()
    lines = [f"- Files: {len(files)}; total size {sum(p.stat().st_size for p in files) / 1e6:.1f} MB",
             "- Formats: " + ", ".join(f"`{k}` x{v}" for k, v in exts.items())]
    # Standard AHI L1b HSD name: HS_H09_20261102_0000_B07_FLDK_R20_S0110.DAT
    import re
    pat = re.compile(r"HS_(H0\d)_(\d{8})_(\d{4})_B(\d{2})_(\w+?)_R(\d{2})_S(\d{2})(\d{2})")
    parsed = [m.groups() for p in files if (m := pat.search(p.name))]
    if parsed:
        t = pd.to_datetime([f"{g[1]}{g[2]}" for g in parsed], format="%Y%m%d%H%M")
        lines += [f"- Satellites: {sorted({g[0] for g in parsed})}",
                  f"- Time range (UTC): {t.min()} to {t.max()} ({t.nunique()} time slots)",
                  f"- Bands: {sorted({'B' + g[3] for g in parsed})}",
                  f"- Areas: {sorted({g[4] for g in parsed})}; segments: {sorted({g[5] for g in parsed})}"]
    else:
        lines.append("- File names do not follow the AHI HSD pattern; bands/segments not parsed. "
                     "Examples: " + ", ".join(p.name for p in files[:5]))
    return lines


def build_report(cfg: dict) -> tuple[str, dict]:
    raw_dir = cfg["paths"]["raw_dir"]
    lines, facts = inspect_firms(raw_dir)
    out = ["# Raw data inspection", "", f"Folder: `{raw_dir}`", "",
           "## Data problems found", ""]
    out += [f"- {p}" for p in facts["problems"]] or ["- None"]
    out += ["", "## FIRMS files", ""] + lines
    out += ["## Himawari (later phase, not processed in this run)", ""]
    out += inspect_himawari(cfg["paths"]["himawari_dir"])
    return "\n".join(out) + "\n", facts


if __name__ == "__main__":
    from pipeline.config import ensure_dirs, load_settings
    cfg = load_settings()
    ensure_dirs(cfg)
    text, _ = build_report(cfg)
    cfg["paths"]["inspection_report"].write_text(text, encoding="utf-8")
    print(text)
