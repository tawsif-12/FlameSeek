"""A day whose detections all fall outside the place leaves zero rows; quality control must still work."""
from pipeline import ingest, quality
from pipeline.config import load_settings


def test_quality_run_on_zero_rows(tmp_path):
    (tmp_path / "VIIRS_SNPP_SP.csv").write_text(
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight,type\n"
        "22.7,88.5,311.2,0.46,0.39,2021-11-08,1932,N,VIIRS,n,2,292.0,1.28,N,0\n")
    cfg = load_settings()
    det = ingest.standardize(ingest.load_raw(tmp_path), cfg).iloc[:0]
    qc = quality.run(det, cfg, bbox=[0, 0, 1, 1], partial=[], coverage={}, quiet=True)
    for key in ("clean", "lowconf", "removed"):
        assert qc[key].empty and "p_conf" in qc[key].columns
