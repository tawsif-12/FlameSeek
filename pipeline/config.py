"""Load config/settings.yaml, resolve paths against the repository root, and select a window."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS = ROOT / "config" / "settings.yaml"


def load_settings(path: str | Path = DEFAULT_SETTINGS, window: str | None = None,
                  partition_root: str | Path | None = None) -> dict:
    """Read the YAML settings and turn every entry under `paths` into an absolute Path.

    window: name under `windows:` (default: `default_window`). Sets cfg["window"] with its
    dates, raw folder and bbox, and the window's output folders:
      data/processed/windows/<name>/   window tables (fire_events.csv, grid_daily.csv, ...)
      data/interim/windows/<name>/     window intermediates
      outputs/ (default window) or outputs/windows/<name>/ (other windows) for reports/figures
    partition_root: override for the day partitions (used by the benchmark).
    """
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg["paths"] = {k: (ROOT / v).resolve() for k, v in cfg["paths"].items()}
    cfg["processing_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    wins = cfg.get("windows") or {}
    name = window or cfg.get("default_window")
    if name is not None:
        if name not in wins:
            raise KeyError(f"Unknown window '{name}'. Defined: {', '.join(wins)}")
        w = dict(wins[name])
        w["name"] = name
        w["start"] = _as_date(w["start"])
        w["end"] = _as_date(w["end"])
        w["raw_dir"] = (ROOT / w.get("raw_dir", "data/raw")).resolve()
        cfg["window"] = w
        cfg["data_version"] = w.get("data_version", cfg["data_version"])
        cfg["paths"]["raw_dir"] = w["raw_dir"]
        if w.get("bbox"):
            cfg["study_bbox"] = list(w["bbox"])
        cfg["paths"]["window_processed"] = ROOT / "data" / "processed" / "windows" / name
        cfg["paths"]["window_interim"] = ROOT / "data" / "interim" / "windows" / name
        out = ROOT / "outputs" if name == cfg.get("default_window") else ROOT / "outputs" / "windows" / name
        cfg["paths"]["window_outputs"] = out
        cfg["paths"]["figures_dir"] = out / "figures"
        cfg["paths"]["report"] = out / "phase1_report.md"
        cfg["paths"]["inspection_report"] = out / "raw_inspection_report.md"
        # Legacy names used by older modules point at the window folders.
        cfg["paths"]["processed_dir"] = cfg["paths"]["window_processed"]
        cfg["paths"]["interim_dir"] = cfg["paths"]["window_interim"]
    part = cfg.get("partitions") or {}
    cfg["paths"]["partition_root"] = (Path(partition_root) if partition_root
                                      else ROOT / part.get("root", "data/processed")).resolve()
    return cfg


def _as_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def ensure_dirs(cfg: dict) -> None:
    """Create output folders. Never touches the raw data folder."""
    for key in ("interim_dir", "processed_dir", "figures_dir"):
        cfg["paths"][key].mkdir(parents=True, exist_ok=True)
    cfg["paths"]["report"].parent.mkdir(parents=True, exist_ok=True)
