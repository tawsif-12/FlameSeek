"""Forecast evaluation: Brier score, Brier Skill Score and reliability diagram."""
from __future__ import annotations

import numpy as np
import pandas as pd


def brier(p, y) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    return float(np.mean((p - y) ** 2))


def brier_skill(p, y, p_ref) -> float:
    """BSS = 1 - BS / BS_ref. p_ref: reference probabilities (scalar or array)."""
    ref = brier(np.broadcast_to(np.asarray(p_ref, float), np.shape(y)), y)
    return float(1 - brier(p, y) / ref) if ref > 0 else np.nan


def reliability(p, y, bins: int = 10) -> pd.DataFrame:
    p, y = np.asarray(p, float), np.asarray(y, float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        rows.append({"bin": b, "p_lo": edges[b], "p_hi": edges[b + 1], "n": int(m.sum()),
                     "mean_p": float(p[m].mean()) if m.any() else np.nan,
                     "obs_freq": float(y[m].mean()) if m.any() else np.nan})
    return pd.DataFrame(rows)


def plot_reliability(table: pd.DataFrame, out, title: str = "Reliability diagram") -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pipeline.figures import INK, INK2, SURFACE, _style
    fig, ax = plt.subplots(figsize=(5.2, 5), facecolor=SURFACE)
    _style(ax)
    t = table[table["n"] > 0]
    ax.plot([0, 1], [0, 1], color=INK2, linestyle=":", linewidth=1, label="perfect reliability")
    ax.plot(t["mean_p"], t["obs_freq"], color="#2a78d6", linewidth=2, marker="o",
            markersize=5, label="forecast")
    for _, r in t.iterrows():
        ax.annotate(f"{r['n']:,}", (r["mean_p"], r["obs_freq"]), xytext=(4, -10), textcoords="offset points",
                    fontsize=7, color=INK2)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Forecast probability", color=INK2, fontsize=8.5)
    ax.set_ylabel("Observed frequency", color=INK2, fontsize=8.5)
    ax.set_title(title, color=INK, fontsize=9.5, loc="left")
    leg = ax.legend(fontsize=8, frameon=False, loc="upper left")
    for tx in leg.get_texts():
        tx.set_color(INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)
