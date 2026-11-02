"""Day-partitioned pipeline: deterministic reruns, incremental skips, same results as batch."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from conftest import INTERIM, PROCESSED, real_outputs
from pipeline import events, footprints, grid, ingest, quality, stages
from pipeline import partitions as P
from pipeline.config import ROOT, load_settings

VIIRS_COLS = ["latitude", "longitude", "bright_ti4", "scan", "track", "acq_date", "acq_time", "satellite",
              "instrument", "confidence", "version", "bright_ti5", "frp", "daynight"]
MODIS_COLS = ["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time", "satellite",
              "instrument", "confidence", "version", "bright_t31", "frp", "daynight"]


def _v(lat, lon, day, t, frp, conf="n", sat="N", ver="2.0NRT"):
    return [lat, lon, 330.0, 0.39, 0.36, day, t, sat, "VIIRS", conf, ver, 290.0, frp, "D"]


def make_raw(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    v = []
    for di, day in enumerate(["2026-10-29", "2026-10-30", "2026-10-31"]):
        for k in range(3):  # persistent fire A: links across days
            v.append(_v(23.80 + 0.003 * k, 90.40, day, 730, 5.0 + k + di))
        v.append(_v(23.90, 90.90, day, 730, 2.0, conf="l"))            # low confidence
        v.append(_v(24.30, 89.70 + 0.05 * di, day, 1910, 3.0))         # night-ish small fires
    v.append(_v(23.45, 91.10, "2026-10-30", 820, 12.0, sat="N20"))     # fire B (NOAA-20)
    v.append(_v(23.45, 91.10, "2026-10-30", 820, 12.0, sat="N20"))     # exact duplicate row
    v.append(_v(23.45, 91.1001, "2026-10-30", 821, 11.0, sat="N20", ver="2.0URT"))  # URT copy
    pd.DataFrame(v, columns=VIIRS_COLS).to_csv(raw / "viirs.csv", index=False)
    m = [[23.451, 91.101, 340.0, 1.2, 1.1, "2026-10-30", 815, "Aqua", "MODIS", "75", "6.1NRT", 295.0, 30.0, "D"]]
    pd.DataFrame(m, columns=MODIS_COLS).to_csv(raw / "modis.csv", index=False)
    return raw


@pytest.fixture
def pcfg(tmp_path):
    raw = make_raw(tmp_path)
    c = load_settings(window="current_2026", partition_root=tmp_path / "parts")
    c["window"].update(start=date(2026, 10, 29), end=date(2026, 10, 31), raw_dir=raw, name="synthetic")
    c["paths"]["raw_dir"] = raw
    for k in ("window_processed", "window_interim"):
        c["paths"][k] = tmp_path / k
    c["paths"]["processed_dir"], c["paths"]["interim_dir"] = c["paths"]["window_processed"], c["paths"]["window_interim"]
    c["study_bbox"] = None
    return c


def run_all(cfg, force=False):
    stages.raw_split(cfg, force)
    days = stages.local_days(cfg)
    for d in days:
        stages.detect_day(cfg, d, force)
    for d in days:
        stages.link_day(cfg, d, force)
    for d in days:
        stages.grid_day(cfg, d, force)
    return stages.finalize(cfg, write_outputs=True)


def snapshot(root):
    out = {}
    for f in sorted(root.rglob("*.parquet")):
        out[str(f.relative_to(root))] = pd.read_parquet(f)
    return out


def test_rerun_is_identical_and_incremental(pcfg):
    root = pcfg["paths"]["partition_root"]
    run_all(pcfg)
    a = snapshot(root)
    assert any(k.startswith("detections") for k in a)
    mtimes = {f: f.stat().st_mtime_ns for f in root.rglob("part.parquet")}
    # Incremental: nothing is rewritten without --force.
    for d in stages.local_days(pcfg):
        assert stages.detect_day(pcfg, d)["skipped"] is True
        assert stages.link_day(pcfg, d)["skipped"] is True
        assert stages.grid_day(pcfg, d)["skipped"] is True
    assert {f: f.stat().st_mtime_ns for f in root.rglob("part.parquet")} == mtimes
    # Forced rerun: identical content in every partition.
    run_all(pcfg, force=True)
    b = snapshot(root)
    assert a.keys() == b.keys()
    for k in a:
        pd.testing.assert_frame_equal(a[k].reset_index(drop=True), b[k].reset_index(drop=True), check_like=False)


def test_same_results_as_batch(pcfg):
    fin = run_all(pcfg)
    # Batch reference on the same files.
    raw = ingest.load_raw(pcfg["paths"]["raw_dir"])
    det = ingest.standardize(raw, pcfg)
    qc = quality.run(det, pcfg, quiet=True)
    fp = footprints.run(qc["clean"], pcfg)
    ev = events.run(fp, pcfg)
    gr = grid.run(ev["detections"], {**pcfg, "_coverage": qc["coverage"]})

    # Timestamps read back through DuckDB must stay in UTC, whatever the computer's time zone.
    for t in (fin["detections"]["acq_datetime_utc"], fin["overpasses"]["acq_datetime_utc"]):
        assert t.dt.tz is not None and t.dt.tz.utcoffset(t.iloc[0]).total_seconds() == 0
    key = lambda df: set(zip(df["source_file"], df["source_row"]))  # noqa: E731
    assert key(fin["detections"]) == key(ev["detections"])
    assert np.isclose(fin["detections"]["frp_mw"].sum(), ev["detections"]["frp_mw"].sum())

    def groups(df):
        return {frozenset(zip(g["source_file"], g["source_row"])) for _, g in df.groupby("fire_id")}
    assert groups(fin["detections"]) == groups(ev["detections"])
    assert len(fin["events"]) == len(ev["events"])
    assert sorted(fin["events"]["FRP_VIIRS_max"].fillna(-1)) == sorted(ev["events"]["FRP_VIIRS_max"].fillna(-1))
    assert sorted(fin["events"]["sensor_flag"]) == sorted(ev["events"]["sensor_flag"])
    assert np.isclose(fin["grid_overpass"]["frp_mw"].sum(), gr["overpass"]["frp_mw"].sum())
    assert len(fin["pairs"]) == len(ev["pairs"])
    # Duplicate and URT copy removed; low-confidence kept aside.
    reasons = ";".join(fin["removed"]["flags"])
    assert "duplicate_detection" in reasons and "urt_duplicate_of_nrt" in reasons
    assert fin["n_lowconf"] == 3


@real_outputs
def test_real_window_matches_batch_snapshot():
    legacy = ROOT / "data" / "interim" / "legacy_batch"
    if not (legacy / "fire_events.csv").exists():
        pytest.skip("no batch snapshot")
    new = pd.read_parquet(PROCESSED / "detections_clean.parquet", columns=["frp_mw", "sensor"])
    old = pd.read_parquet(legacy / "detections_clean.parquet", columns=["frp_mw", "sensor"])
    assert len(new) == len(old)
    assert np.isclose(new["frp_mw"].sum(), old["frp_mw"].sum())
    ev_new = pd.read_csv(PROCESSED / "fire_events.csv", usecols=["sensor_flag"])
    ev_old = pd.read_csv(legacy / "fire_events.csv", usecols=["sensor_flag"])
    # Event counts may differ only where a cap split a multi-day component (decisions D38).
    assert abs(len(ev_new) - len(ev_old)) <= 0.001 * len(ev_old)
    go_new = pd.read_csv(INTERIM / "grid_overpass.csv", usecols=["frp_mw"])
    assert np.isclose(go_new["frp_mw"].sum(), old["frp_mw"].sum())
