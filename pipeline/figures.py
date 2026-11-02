"""Figures for Phase 1: raw vs harmonized map, and detections per platform per day."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Reference categorical palette (dataviz skill), light mode. Colour follows the
# entity, so each sensor_flag / platform keeps its slot even when absent.
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
FLAG_COLORS = {"VIIRS_only": "#2a78d6", "MODIS_only": "#eb6834", "both": "#1baf7a"}
PLATFORM_COLORS = {"S-NPP": "#2a78d6", "NOAA-20": "#eb6834", "NOAA-21": "#1baf7a",
                   "Terra": "#eda100", "Aqua": "#e87ba4"}
RAW_COLOR = "#52514e"


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    ax.grid(color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _basemap(ax):
    """Light basemap if tiles can be fetched; plain axes otherwise (figure still valid)."""
    try:
        import contextily as cx
        cx.add_basemap(ax, crs="EPSG:4326", source=cx.providers.Esri.WorldGrayCanvas,
                       attribution_size=5, zoom=2)
        return True
    except Exception as exc:  # offline or tile server error
        print(f"         basemap skipped ({type(exc).__name__}); plotting on plain axes")
        return False


def map_raw_vs_events(raw: pd.DataFrame, events: pd.DataFrame, out: Path, bbox) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(16, 3.6), facecolor=SURFACE, sharex=True, sharey=True)
    lon0, lat0, lon1, lat1 = bbox
    r = raw.dropna(subset=["latitude", "longitude"])

    ax = axes[0]
    _style(ax)
    ax.scatter(r["longitude"], r["latitude"], s=3, color=RAW_COLOR, alpha=0.6, linewidths=0)
    ax.set_title(f"Raw FIRMS rows: {len(r):,} (all files, before QC and de-duplication)",
                 color=INK, fontsize=10, loc="left")

    ax = axes[1]
    _style(ax)
    for flag, color in FLAG_COLORS.items():
        e = events[events["sensor_flag"] == flag]
        if len(e):
            size = 4 + 3 * np.sqrt(e["n_detections"].clip(upper=60))
            ax.scatter(e["centroid_lon"], e["centroid_lat"], s=size, color=color, alpha=0.75,
                       linewidths=0.3, edgecolors=SURFACE, label=f"{flag} ({len(e):,})")
        else:
            ax.scatter([], [], s=12, color=color, label=f"{flag} (0)")
    ax.set_title(f"Harmonized fire events: {len(events):,} (marker size = detections per event)",
                 color=INK, fontsize=10, loc="left")
    leg = ax.legend(loc="lower left", fontsize=8, frameon=True, title="sensor_flag", title_fontsize=8)
    leg.get_frame().set_edgecolor(GRID)
    for t in leg.get_texts():
        t.set_color(INK)

    for ax in axes:
        ax.set_xlim(lon0, lon1)
        ax.set_ylim(lat0, lat1)
        ax.set_aspect("equal")
        ax.set_xlabel("Longitude (°)", color=INK2, fontsize=8)
    axes[0].set_ylabel("Latitude (°)", color=INK2, fontsize=8)
    for ax in axes:
        _basemap(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def bar_platform_day(raw_std: pd.DataFrame, clean: pd.DataFrame, out: Path, partial_days=()) -> None:
    """Grouped bars: detections per platform per UTC day, all parsed rows vs. kept rows."""
    def table(df):
        return df.dropna(subset=["platform", "utc_date"]).groupby(["utc_date", "platform"]).size()

    bar_platform_day_counts(table(raw_std), table(clean), out, partial_days)


def bar_platform_day_counts(raw_t: pd.Series, clean_t: pd.Series, out: Path, partial_days=()) -> None:
    """Same chart from pre-counted Series indexed by (utc_date, platform)."""
    days = sorted(raw_t.index.get_level_values(0).unique())
    platforms = [p for p in PLATFORM_COLORS if p in raw_t.index.get_level_values(1)]
    fig, ax = plt.subplots(figsize=(max(6, 2.2 * len(days) * len(platforms) / 3 + 3), 4.2),
                           facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="x", visible=False)
    width = 0.8 / max(len(platforms), 1)
    x = np.arange(len(days))
    for k, p in enumerate(platforms):
        rv = [raw_t.get((d, p), 0) for d in days]
        cv = [clean_t.get((d, p), 0) for d in days]
        pos = x - 0.4 + width * (k + 0.5)
        # Outline = all parsed rows (incl. duplicates and low confidence); fill = kept for harmonization.
        ax.bar(pos, rv, width * 0.92, color="none", edgecolor=PLATFORM_COLORS[p], linewidth=1.2)
        ax.bar(pos, cv, width * 0.92, color=PLATFORM_COLORS[p], label=p)
        for xi, a, b in zip(pos, rv, cv):
            ax.text(xi, a, f"{b:,} / {a:,}", ha="center", va="bottom", fontsize=7, color=INK2)
    ax.set_xticks(x, [f"{d}\n(partial day)" if d in partial_days else d for d in days])
    ax.set_ylabel("Detections", color=INK2, fontsize=9)
    ax.set_title("Detections per platform per day (UTC)", color=INK, fontsize=10, loc="left", pad=16)
    ax.text(0, 1.01, "Fill = kept after QC; outline = all parsed rows; labels = kept / parsed",
            transform=ax.transAxes, fontsize=7.5, color=INK2, va="bottom")
    leg = ax.legend(fontsize=8, frameon=False, ncol=1, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    for t in leg.get_texts():
        t.set_color(INK)
    ax.margins(y=0.15)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)
