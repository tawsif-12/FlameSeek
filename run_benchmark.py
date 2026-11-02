"""Scaling benchmark: 1, 3 and 5 days, global and Indo-Gangetic Plain bbox.

    python run_benchmark.py [--window current_2026] [--workers 1]

Each run uses its own partition root (data/bench/<tag>/parts) and --force, so nothing is
skipped. Records wall time and peak memory per stage in outputs/benchmark.csv, fits
time = a + b * days per stage, and extrapolates to 1 year and 15 years. Plot:
outputs/figures/scaling.png.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import run_pipeline  # noqa: E402
from pipeline.config import ROOT, load_settings  # noqa: E402
from pipeline.figures import INK, INK2, SURFACE, _style  # noqa: E402

REGIONS = {"global": None, "igp": [73.0, 24.0, 89.0, 32.5]}
STAGES = ["raw_split", "detect", "link", "grid", "finalize"]


def dir_bytes(p):
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def main(window=None, workers=1, ndays=(1, 3, 5)) -> pd.DataFrame:
    base = load_settings(window=window)
    w0 = base["window"]["start"]
    rows = []
    for region, bbox in REGIONS.items():
        for n in ndays:
            tag = f"bench_{region}_{n}d"
            root = ROOT / "data" / "bench" / tag
            if root.exists():
                shutil.rmtree(root)
            # bbox override through the settings dict
            import yaml
            orig = run_pipeline.load_settings

            def patched(path, window=None, partition_root=None, _bbox=bbox):
                c = orig(path, window=window, partition_root=partition_root)
                c["study_bbox"] = _bbox
                return c
            run_pipeline.load_settings = patched
            try:
                r = run_pipeline.main(window, force=True, workers=workers, skip_inspect=True, make_report=False,
                                      partition_root=root / "parts", start=w0, end=w0 + timedelta(days=n - 1),
                                      tag=tag)
            finally:
                run_pipeline.load_settings = orig
            n_det = len(r["finalize"]["detections"])
            n_ev = len(r["finalize"]["events"])
            store = dir_bytes(root / "parts")
            for s in r["stages"]:
                rows.append({"region": region, "days": n, "stage": s["stage"], "seconds": s["seconds"],
                             "peak_mb": s["peak_mb"], "n_detections": n_det, "n_events": n_ev,
                             "partition_mb": store / 2**20, "workers": workers})
            rows.append({"region": region, "days": n, "stage": "total", "seconds": r["total_seconds"],
                         "peak_mb": max(s["peak_mb"] for s in r["stages"]), "n_detections": n_det,
                         "n_events": n_ev, "partition_mb": store / 2**20, "workers": workers})
            del yaml
    df = pd.DataFrame(rows)
    out = ROOT / "outputs" / "benchmark.csv"
    df.to_csv(out, index=False)
    plot(df, ROOT / "outputs" / "figures" / "scaling.png")
    print(extrapolate(df).to_string(index=False))
    return df


def extrapolate(df: pd.DataFrame) -> pd.DataFrame:
    """Linear fit seconds = a + b*days per region and stage; R², and 1-year / 15-year projections."""
    rows = []
    for (region, stage), g in df.groupby(["region", "stage"]):
        x, y = g["days"].to_numpy(float), g["seconds"].to_numpy(float)
        b, a = np.polyfit(x, y, 1)
        pred = a + b * x
        r2 = 1 - ((y - pred) ** 2).sum() / max(((y - y.mean()) ** 2).sum(), 1e-12)
        # Growth exponent from a log-log fit (1 = linear).
        k = np.polyfit(np.log(x), np.log(np.maximum(y, 1e-3)), 1)[0] if len(x) > 1 else np.nan
        mem = g["peak_mb"].to_numpy()
        rows.append({"region": region, "stage": stage, "sec_per_day": b, "fixed_sec": a, "r2_linear": r2,
                     "loglog_exponent": k, "peak_mb_min": mem.min(), "peak_mb_max": mem.max(),
                     "proj_1y_hours": (a + b * 365) / 3600, "proj_15y_hours": (a + b * 365 * 15) / 3600})
    return pd.DataFrame(rows)


def plot(df: pd.DataFrame, out) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), facecolor=SURFACE)
    colors = {"raw_split": "#1baf7a", "detect": "#2a78d6", "link": "#eda100", "grid": "#e87ba4",
              "finalize": "#6250d6", "total": "#0b0b0b"}
    for ax, metric, label in ((axes[0], "seconds", "Wall time (s)"), (axes[1], "peak_mb", "Peak memory (MB)")):
        _style(ax)
        for (region, stage), g in df.groupby(["region", "stage"]):
            if stage not in colors:
                continue
            ls = "-" if region == "global" else "--"
            ax.plot(g["days"], g[metric], ls, color=colors[stage], marker="o", markersize=4, linewidth=1.8,
                    label=f"{stage} ({region})" if region == "global" or stage == "total" else None)
        ax.set_xlabel("Days processed", color=INK2, fontsize=8.5)
        ax.set_ylabel(label, color=INK2, fontsize=8.5)
        ax.set_xticks(sorted(df["days"].unique()))
    axes[0].set_title("Runtime per stage. Solid = global, dashed = Indo-Gangetic Plain", color=INK, fontsize=9.5,
                      loc="left")
    axes[1].set_title("Peak memory per stage (process + workers)", color=INK, fontsize=9.5, loc="left")
    leg = axes[0].legend(fontsize=7.5, frameon=False, ncol=2)
    for t in leg.get_texts():
        t.set_color(INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", default=None)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    main(a.window, a.workers)
