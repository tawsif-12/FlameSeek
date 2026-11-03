"""Fire Intelligence place-pipeline job: raw input writing, progress relay, availability check."""
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import place_pipeline as pp


class FakeJob:
    progress = 0.0
    message = ""


def test_write_raw_merges_chunks_per_source_with_one_header(tmp_path):
    sink = [("MODIS_SP", "latitude,longitude\n1,2\n3,4\n"), ("MODIS_SP", "latitude,longitude\n5,6\n"),
            ("VIIRS_SNPP_SP", "latitude,longitude\n"), ("VIIRS_SNPP_SP", "latitude,longitude\n7,8\n")]
    counts = pp._write_raw(sink, tmp_path / "raw")
    assert counts == {"MODIS_SP": 3, "VIIRS_SNPP_SP": 1}
    assert (tmp_path / "raw" / "MODIS_SP.csv").read_text().splitlines() == ["latitude,longitude", "1,2", "3,4", "5,6"]


def test_run_pipeline_relays_progress_and_returns_summary(tmp_path, monkeypatch):
    summary = tmp_path / "place_summary.json"
    summary.write_text("{}")
    script = tmp_path / "fake.py"
    script.write_text(f"print('PROGRESS 0.5 link linking events')\nprint('SUMMARY {summary.as_posix()}')\n")
    monkeypatch.setattr(pp, "PIPELINE_PYTHON", sys.executable)
    monkeypatch.setattr(pp.subprocess, "Popen", _redirect(script))
    job = FakeJob()
    assert pp._run_pipeline(job, []) == summary
    assert job.message == "FlameSeek pipeline: link linking events"
    assert job.progress == pytest.approx(0.6 + 0.38 * 0.5)


def test_run_pipeline_failure_reports_output_tail(tmp_path, monkeypatch):
    script = tmp_path / "fake.py"
    script.write_text("print('boom'); raise SystemExit(3)\n")
    monkeypatch.setattr(pp.subprocess, "Popen", _redirect(script))
    with pytest.raises(RuntimeError, match="boom"):
        pp._run_pipeline(FakeJob(), [])


def test_endpoint_reports_missing_pipeline_environment(monkeypatch):
    monkeypatch.setattr(pp, "PIPELINE_PYTHON", str(Path("Z:/missing/python.exe")))
    app = FastAPI()
    app.include_router(pp.router, prefix="/api")
    r = TestClient(app).post("/api/place_pipeline", json={"aoi": {"bbox": [88.6, 21.5, 89.9, 22.5]}, "history_years": 1})
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "pipeline_unavailable"


def _redirect(script):
    real = pp.subprocess.Popen

    def popen(cmd, **kw):
        return real([sys.executable, str(script)], **kw)
    return popen
