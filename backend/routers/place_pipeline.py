"""Run the FlameSeek harmonization pipeline for a searched place (Fire Intelligence).

POST /api/place_pipeline {aoi, history_years} starts a background job:
  1. download the NASA FIRMS archive for the place (MODIS + Suomi-NPP), reusing the same cached
     chunks as Fire Memory, and keep each chunk's original CSV text;
  2. write it as the pipeline's raw input in data/raw/places/<place_id>/;
  3. run `python -m pipeline.place_run` in the pipeline's own Python environment (FLAMESEEK_PIPELINE_PYTHON),
     relaying its stage progress;
  4. return data/places/<place_id>/place_summary.json, saved for reuse when no chunk failed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import BACKEND_DIR, MAX_AOI_DEGREES_SPAN, SENSOR_START_DATES
from firms_client import fetch_hotspots_with_report, quota_wait_status, snap_bbox
from geo import AOI
from http_utils import disk_read, disk_write
from jobs import Job, start_job
from schemas import AOIModel

router = APIRouter()
PROJECT_ROOT = BACKEND_DIR.parent
PIPELINE_PYTHON = os.getenv("FLAMESEEK_PIPELINE_PYTHON", r"E:\anaconda\envs\flameseek\python.exe")
SENSORS = ["modis", "viirs_snpp"]
CACHE_VERSION = 2  # bump when place_summary.json changes
CACHE_TTL_SECONDS = 7 * 86400


class PlacePipelineRequest(BaseModel):
    aoi: AOIModel
    history_years: int = Field(default=5, ge=1, le=26)
    refresh: bool = False


def _place_id(payload: PlacePipelineRequest, start, end) -> str:
    key = json.dumps([CACHE_VERSION, payload.aoi.model_dump(mode="json"), start.isoformat(), end.isoformat(), SENSORS], sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def _write_raw(raw_sink: list[tuple[str, str]], folder: Path) -> dict[str, int]:
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    by_source: dict[str, list[str]] = defaultdict(list)
    headers: dict[str, str] = {}
    for source, text in raw_sink:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            continue
        headers.setdefault(source, lines[0])
        by_source[source].extend(lines[1:])
    counts = {}
    for source, rows in by_source.items():
        (folder / f"{source}.csv").write_text("\n".join([headers[source], *rows]) + "\n", encoding="utf-8")
        counts[source] = len(rows)
    return counts


def _run_pipeline(job: Job, args: list[str]) -> Path:
    """Blocking: run the pipeline subprocess and relay its PROGRESS lines to the job."""
    proc = subprocess.Popen([PIPELINE_PYTHON, "-m", "pipeline.place_run", *args], cwd=str(PROJECT_ROOT),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    summary, tail = None, []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        tail = (tail + [line])[-25:]
        if line.startswith("PROGRESS "):
            parts = line.split(" ", 3)
            frac = float(parts[1])
            stage = parts[2] if len(parts) > 2 else ""
            note = parts[3] if len(parts) > 3 else ""
            job.message = f"FlameSeek pipeline: {stage} {note}".strip()
            job.progress = max(job.progress, 0.6 + 0.38 * frac)
        elif line.startswith("SUMMARY "):
            summary = Path(line[len("SUMMARY "):].strip())
    code = proc.wait()
    if code != 0 or summary is None or not summary.exists():
        raise RuntimeError("Pipeline failed: " + " | ".join(tail[-6:]))
    return summary


async def run_place_pipeline(job: Job, payload: PlacePipelineRequest) -> dict[str, Any]:
    aoi = AOI.from_payload(payload.aoi.model_dump())
    west, south, east, north = aoi.bbox
    if (east - west) > MAX_AOI_DEGREES_SPAN or (north - south) > MAX_AOI_DEGREES_SPAN:
        raise ValueError(f"Area too large: choose an area under {MAX_AOI_DEGREES_SPAN} degrees across.")
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    try:
        start = end.replace(year=end.year - payload.history_years) + timedelta(days=1)
    except ValueError:
        start = end.replace(year=end.year - payload.history_years, day=28) + timedelta(days=1)
    start = max(start, SENSOR_START_DATES["modis"])
    place_id = _place_id(payload, start, end)
    if not payload.refresh:
        cached = disk_read("place_pipeline", place_id, ".json", CACHE_TTL_SECONDS)
        if cached is not None:
            await job.update("Loaded saved pipeline run for this place", 0.95)
            result = json.loads(cached)
            result["served_from_cache"] = True
            return result

    counts = {"done": 0, "total": 0}

    async def on_progress(done: int, total: int) -> None:
        counts.update(done=done, total=total)
        await job.update(f"Downloading NASA FIRMS archive: {done}/{total} requests", 0.02 + 0.56 * done / max(total, 1))

    async def quota_notice() -> None:
        while True:
            await asyncio.sleep(3)
            wait = quota_wait_status()
            if wait:
                used = f" ({wait['usage'][0]:,} of {wait['usage'][1]:,} used)" if wait["usage"] else ""
                await job.update(f"Waiting for NASA FIRMS request quota{used}: resumes automatically. {counts['done']}/{counts['total']} requests done", None)

    raw_sink: list[tuple[str, str]] = []
    await job.update("Planning NASA FIRMS archive requests", 0.01)
    notice = asyncio.create_task(quota_notice())
    try:
        _, report = await fetch_hotspots_with_report(snap_bbox(aoi.bbox), start, end, SENSORS, progress=on_progress, raw_sink=raw_sink)
    finally:
        notice.cancel()

    raw_dir = PROJECT_ROOT / "data" / "raw" / "places" / place_id
    rows_by_source = await asyncio.to_thread(_write_raw, raw_sink, raw_dir)
    if not rows_by_source:
        raise RuntimeError("NASA FIRMS returned no archive files for this place and period.")
    args = ["--id", place_id, "--raw-dir", str(raw_dir), "--start", start.isoformat(), "--end", end.isoformat(),
            "--bbox", ",".join(f"{v:.6f}" for v in aoi.bbox)]
    geometry = payload.aoi.model_dump(mode="json").get("geometry")
    if geometry:
        gpath = raw_dir.parent / f"{place_id}.geometry.json"
        gpath.write_text(json.dumps(geometry), encoding="utf-8")
        args += ["--geometry", str(gpath)]
    await job.update("FlameSeek pipeline: starting", 0.6)
    summary_path = await asyncio.to_thread(_run_pipeline, job, args)
    result = json.loads(summary_path.read_text(encoding="utf-8"))
    result["provenance"] = {"firms_requests": report["requests"], "failed_chunks": len(report["failed_chunks"]),
                            "raw_rows_by_source": rows_by_source, "sensors": SENSORS, "place_id": place_id,
                            "generated_at": datetime.now(timezone.utc).isoformat()}
    if not report["failed_chunks"]:
        disk_write("place_pipeline", place_id, json.dumps(result, default=str), ".json")
    return result


@router.post("/place_pipeline")
async def place_pipeline(payload: PlacePipelineRequest) -> dict[str, Any]:
    try:
        AOI.from_payload(payload.aoi.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_aoi", "message": str(exc)}) from exc
    if not Path(PIPELINE_PYTHON).exists():
        raise HTTPException(status_code=503, detail={"error": "pipeline_unavailable",
                                                     "message": "The FlameSeek pipeline environment was not found (set FLAMESEEK_PIPELINE_PYTHON)."})
    job = start_job("place_pipeline", payload.model_dump(mode="json"), lambda job: run_place_pipeline(job, payload))
    return job.to_dict()
