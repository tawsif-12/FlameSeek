"""D72: recompute every figure that used himawari.nearby() before its unit fix.

    E:\\anaconda\\envs\\flameseek\\python.exe run_nearby_fix_rerun.py

Recomputes from stored detections (no Himawari reprocessing, no refit):
- Phase 3c Northern Australia reference_match / commission (phase3c.py:31)
- Phase 3 South Asia reference_match / commission (run_phase3.py:148; tuning :132)
- event-specific AHI ratios in both transfer-pair tables (transfer.py:94)
Writes corrected values back to the derived files and old-vs-new to
outputs/nearby_fix_rerun.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import himawari as hw, naus_diagnostics as nd, transfer
from pipeline.config import ROOT, load_settings


def read_parts(root: Path) -> list[tuple[Path, pd.DataFrame]]:
    return [(p, pd.read_parquet(p)) for p in sorted(root.rglob("part.parquet"))]


def commission(parts, refs, label):
    old = pd.concat([d.reference_match for _, d in parts]) if parts else pd.Series(dtype=bool)
    new_all = []
    for path, d in parts:
        if len(d):
            d = d.copy()
            d["reference_match"] = hw.nearby(d, refs, 60, 2)
            if "transient_suspect" in d:
                d["transient_suspect"] = d["transient_suspect"] & ~d["reference_match"]
            d.to_parquet(path, index=False)
        new_all.append(d.reference_match)
    new = pd.concat(new_all) if new_all else pd.Series(dtype=bool)
    rate = lambda s: float((~s.astype(bool)).mean()) if len(s) else None  # noqa: E731
    return {"figure": label, "n_pixels": int(len(new)), "old": rate(old), "new": rate(new)}


def ratios(pairs_path: Path, detections: pd.DataFrame, settings, label):
    pairs = pd.read_csv(pairs_path)
    if pairs.empty:
        return {"figure": label, "n_pairs": 0, "old_n_finite": 0, "new_n_finite": 0}
    for c in ("acq_datetime_utc_modis", "acq_datetime_utc_viirs"):
        pairs[c] = pd.to_datetime(pairs[c], utc=True)
    old = pairs["event_specific_ahi_ratio"].astype(float)
    new = pd.Series(transfer.event_specific_ratios(pairs, detections, settings), index=pairs.index, dtype=float)
    pairs["event_specific_ahi_ratio"] = new
    pairs.to_csv(pairs_path, index=False)
    both = old.notna() & new.notna()
    return {"figure": label, "n_pairs": int(len(pairs)), "old_n_finite": int(old.notna().sum()),
            "new_n_finite": int(new.notna().sum()),
            "old_median": float(old.median()) if old.notna().any() else None,
            "new_median": float(new.median()) if new.notna().any() else None,
            "max_abs_change_where_both": float((old[both] - new[both]).abs().max()) if both.any() else None}


def main():
    cfg = load_settings()
    refs = pd.read_parquet(cfg["paths"]["window_processed"] / "detections_clean.parquet")
    refs["acq_datetime_utc"] = pd.to_datetime(refs.acq_datetime_utc, utc=True)
    rows = []

    naus_root = ROOT / "data/processed/geo_fires/platform=Himawari/region=Northern_Australia"
    rows.append(commission(read_parts(naus_root), refs, "Phase 3c N. Australia commission (unmatched share)"))
    sa_refs = refs[refs.acq_datetime_utc.dt.date.between(cfg["window"]["start"], cfg["window"]["end"])]
    rows.append(commission(read_parts(ROOT / "data/processed/himawari_fires"), sa_refs,
                           "Phase 3 South Asia commission (unmatched share)"))
    tuning = json.loads((ROOT / "outputs/himawari/threshold_selection.json").read_text())
    rows.append({"figure": "Phase 3 tuning-alternative commission", "n_alternatives_scored": len(tuning["alternatives"]),
                 "old": None, "new": None, "note": "no alternative was scored (trigger not reached); nothing to recompute"})

    fires = pd.concat([d for _, d in read_parts(naus_root)], ignore_index=True)
    fires["acq_datetime_utc"] = pd.to_datetime(fires.acq_datetime_utc, utc=True)
    rows.append(ratios(ROOT / "outputs/phase3c_naus/transfer_pairs.csv", fires, nd.regional_cfg(cfg)["himawari"],
                       "N. Australia transfer event-specific AHI ratios"))
    sa = pd.concat([d for _, d in read_parts(ROOT / "data/processed/himawari_fires")], ignore_index=True)
    if len(sa):
        sa["acq_datetime_utc"] = pd.to_datetime(sa.acq_datetime_utc, utc=True)
    rows.append(ratios(ROOT / "outputs/himawari/transfer_pairs.csv", sa, cfg["himawari"],
                       "South Asia transfer event-specific AHI ratios"))
    rows.append({"figure": "Phase 3b positive controls (himawari_verify.py:164)", "note":
                 "single-scan comparison at the nearest hourly step (|dt| <= 30 min by construction); unaffected; not rerun"})
    rows.append({"figure": "Phase 3 VIIRS detection rates (run_phase3.py:71)", "note":
                 "single-scan comparison; unaffected"})

    # Keep the stage summaries consistent with the corrected commission.
    naus_new = rows[0]["new"]
    for path, keys in [(ROOT / "outputs/stages/stage2_summary.json", ["naus_commission"]),
                       (ROOT / "outputs/phase3c_status.json", ["part_b", "commission_rate"])]:
        if path.exists():
            doc = json.loads(path.read_text(encoding="utf-8"))
            tgt = doc
            for k in keys[:-1]:
                tgt = tgt.get(k, {})
            if keys[-1] in tgt:
                tgt[keys[-1]] = naus_new
                tgt[keys[-1] + "_note"] = "corrected for the himawari.nearby() unit bug (D72); ±60 min, 2 km"
                hw.json_write(path, doc)
    hw.json_write(ROOT / "outputs/nearby_fix_rerun.json", {"rows": rows})
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
