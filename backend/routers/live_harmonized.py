"""Run the established procedure in its geospatial Python environment."""
import asyncio
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from firms_client import fetch_recent_hotspots, recent_source_status, recent_missing_sensors, FirmsAPIError
from config import DEFAULT_SENSORS
from http_utils import disk_read, disk_write

router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]
_lock = asyncio.Lock()
_snapshots = {}
_jobs = {}
_ready = {}
_errors = {}
_retry_after = {}
_harmonization_jobs = {}
_harmonization_errors = {}
_full_lock = asyncio.Lock()
FRESH_SECONDS = 15 * 60
MAX_CACHE_SECONDS = 6 * 60 * 60


def _save_snapshot(days, stamp, payload):
    disk_write('live_globe', f'days_{days}', json.dumps({'saved_at': stamp, 'payload': payload}))


def compute(rows):
    encoded = json.dumps(jsonable_encoder(rows), sort_keys=True)
    key = hashlib.sha256(('live-v2-full-workflow' + encoded).encode()).hexdigest()[:24]
    folder = ROOT / '.runlogs' / 'live_harmonized'
    folder.mkdir(parents=True, exist_ok=True)
    source, target = folder / f'{key}.input.json', folder / f'{key}.json'
    if not target.exists():
        source.write_text(encoded, encoding='utf-8')
        proc = subprocess.run([os.getenv('FLAMESEEK_PIPELINE_PYTHON', r'E:\anaconda\envs\flameseek\python.exe'),
                               '-m', 'pipeline.live_globe', str(source), str(target), str(folder/key)],
                              cwd=ROOT, capture_output=True, text=True, timeout=300)
        if proc.returncode:
            raise RuntimeError(proc.stderr[-2000:])
    payload = json.loads(target.read_text(encoding='utf-8'))
    payload['metadata']['harmonization_run'] = key
    return payload


def _run_folder(key):
    if not isinstance(key, str) or len(key)!=24 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('Invalid harmonization run')
    return ROOT/'.runlogs'/'live_harmonized'/key


def _full_workflow(key):
    folder = _run_folder(key)
    status = folder/'full'/'status.json'
    signature=_full_signature()
    if status.exists():
        previous=json.loads(status.read_text())
        if previous.get('finished') and previous.get('input_signature')==signature: return
    if not (folder/'detections.parquet').exists(): return
    command = [os.getenv('FLAMESEEK_PIPELINE_PYTHON', r'E:\anaconda\envs\flameseek\python.exe'),
               '-m','pipeline.harmonization',str(folder),str(folder/'full')]
    evidence = ROOT/'config'/'harmonization_evidence.json'
    if evidence.exists(): command += ['--evidence',str(evidence)]
    # Heavy orbital/grid/Monte Carlo work never runs on FastAPI's event loop.
    result = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=1800)
    (folder/'full.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode: raise RuntimeError(result.stderr[-1500:])
    if status.exists():
        report=json.loads(status.read_text()); report['input_signature']=signature
        temporary=status.with_suffix('.tmp'); temporary.write_text(json.dumps(report),encoding='utf-8'); temporary.replace(status)


def _full_signature():
    digest=hashlib.sha256()
    for relative in ['pipeline/harmonization.py','pipeline/grid.py','pipeline/calibration.py',
                     'pipeline/diurnal.py','config/settings.yaml','config/harmonization_evidence.json']:
        path=ROOT/relative
        if path.exists(): digest.update(path.read_bytes())
    manifest=ROOT/'config'/'harmonization_evidence.json'
    if manifest.exists():
        for relative in json.loads(manifest.read_text()).values():
            path=(manifest.parent/relative).resolve()
            if path.exists():
                stat=path.stat(); digest.update(f'{path}:{stat.st_size}:{stat.st_mtime_ns}'.encode())
    return digest.hexdigest()


async def _finish_harmonization(key):
    try:
        async with _full_lock:
            await asyncio.to_thread(_full_workflow,key)
    except Exception as exc:
        _harmonization_errors[key] = str(exc)


def _start_harmonization(key):
    job=_harmonization_jobs.get(key)
    changed=False
    if job is not None and job.done() and key not in _harmonization_errors:
        path=_run_folder(key)/'full'/'status.json'
        if path.exists(): changed=json.loads(path.read_text()).get('input_signature')!=_full_signature()
    if job is None or changed:
        _harmonization_jobs[key] = asyncio.create_task(_finish_harmonization(key))


def _harmonization_status(key):
    folder = _run_folder(key)
    path = folder/'full'/'status.json'
    result = json.loads(path.read_text()) if path.exists() else {'stages':[], 'full_harmonization_complete':False}
    job = _harmonization_jobs.get(key)
    result['running'] = job is not None and not job.done()
    result['run_id'] = key
    if key in _harmonization_errors: result['error'] = _harmonization_errors[key]
    return result


async def _upgrade_snapshot(days, stamp, payload):
    """Attach the new workflow to real cached observations without downloading again."""
    try:
        rows=payload.get('raw_hotspots')
        if not rows: return
        async with _lock:
            result=await asyncio.to_thread(compute,rows)
        current=_snapshots.get(days)
        if current is None or current[0]!=stamp: return
        updated={**payload,'hotspots':result['hotspots'],'metadata':{**payload['metadata'],**result['metadata'], 'processing_pending':False}}
        _snapshots[days]=(stamp,updated)
        key=result['metadata'].get('harmonization_run')
        if key: _start_harmonization(key)
        await asyncio.to_thread(_save_snapshot,days,stamp,updated)
    except Exception as exc:
        _errors[days]=str(exc)
        _retry_after[days]=time.time()+60


async def _refresh(days):
    try:
        rows = await fetch_recent_hotspots(None, DEFAULT_SENSORS, days, include_demo=False)
        source_status = recent_source_status()
        missing_sensors = recent_missing_sensors()
        observed_at = datetime.now(timezone.utc).isoformat()
        # Publish actual observations first, without pretending event merging is complete.
        payload = await asyncio.to_thread(jsonable_encoder, {
            'hotspots': [],
            'raw_hotspots': rows,
            'metadata': {'raw_hotspot_count': len(rows), 'data_source': source_status,
                         'unavailable_live_sensors': missing_sensors, 'partial_coverage': bool(missing_sensors),
                         'snapshot_at': observed_at, 'processing_pending': True},
        })
        _snapshots[days] = (time.time(), payload)
        _ready[days].set()
        async with _lock:
            result = await asyncio.to_thread(compute, rows)
        payload = {**payload, 'hotspots': sorted(result['hotspots'], key=lambda p: p.get('frp') or 0, reverse=True),
                   'metadata': {**payload['metadata'], **result['metadata'], 'processing_pending': False}}
        stamp = time.time()
        _snapshots[days] = (stamp, payload)
        key = result['metadata'].get('harmonization_run')
        if key: _start_harmonization(key)
        try:
            await asyncio.to_thread(_save_snapshot, days, stamp, payload)
        except OSError:
            pass  # A full or read-only cache must not discard successful observations.
        _errors.pop(days, None)
        _retry_after.pop(days, None)
    except Exception as exc:
        _errors[days] = str(exc)
        _retry_after[days] = time.time() + 60
        # Keep already downloaded real observations usable if processing fails.
        cached = _snapshots.get(days)
        if cached and cached[1]['metadata'].get('processing_pending'):
            payload = cached[1]
            _snapshots[days] = (cached[0], {**payload, 'metadata': {**payload['metadata'],
                'processing_pending': False, 'harmonization_unavailable': True}})
    finally:
        _ready[days].set()


def _start_refresh(days):
    if time.time() < _retry_after.get(days, 0) and days in _jobs:
        return _jobs[days]
    if days not in _jobs or _jobs[days].done():
        _ready[days] = asyncio.Event()
        _jobs[days] = asyncio.create_task(_refresh(days))
    return _jobs[days]


async def warm_harmonized(days=1):
    await asyncio.shield(_start_refresh(days))


def _read_snapshot(days):
    try:
        text = disk_read('live_globe', f'days_{days}', max_age_seconds=MAX_CACHE_SECONDS)
    except OSError:
        return None
    if text:
        try:
            saved = json.loads(text)
            if 0 <= time.time() - saved['saved_at'] <= MAX_CACHE_SECONDS:
                return saved['saved_at'], saved['payload']
        except (ValueError, KeyError, TypeError):
            pass
    return None


@router.get('/harmonized_hotspots')
async def harmonized_hotspots(days: int = Query(1, ge=1, le=5), limit: int | None = Query(None, ge=1, le=200000)):
    cached = _snapshots.get(days)
    if cached is None:
        cached = await asyncio.to_thread(_read_snapshot, days)
        if cached:
            _snapshots[days] = cached
    if cached and time.time() - cached[0] > MAX_CACHE_SECONDS:
        cached = None
        _snapshots.pop(days, None)
    stale = cached is not None and time.time() - cached[0] >= FRESH_SECONDS
    if cached is None or stale:
        _start_refresh(days)
    if cached is None:
        await _ready[days].wait()
        cached = _snapshots.get(days)
        if not cached:
            raise HTTPException(502, detail={'message': f'FIRMS observations unavailable: {_errors.get(days, "retry shortly")}'})
    stamp, payload = cached
    key = payload['metadata'].get('harmonization_run')
    if key: _start_harmonization(key)
    elif payload.get('raw_hotspots') and time.time()>=_retry_after.get(days,0) and (days not in _jobs or _jobs[days].done()):
        _jobs[days]=asyncio.create_task(_upgrade_snapshot(days,stamp,payload))
    # Legacy snapshots may contain a raw preview in hotspots. Never publish it
    # as merged output, including after a failed or incomplete pipeline run.
    merged_ready = not payload['metadata'].get('processing_pending') and not payload['metadata'].get('harmonization_unavailable')
    merged = [point for point in payload['hotspots'] if point.get('harmonized')] if merged_ready else []
    points = merged if limit is None else merged[:limit]
    metadata = {**payload['metadata'], 'returned_hotspot_count': len(points),
                'merged_ready': merged_ready, 'harmonization_scope': 'footprint_events_steps_1_4',
                'full_harmonization_complete': False,
                'cache_age_seconds': round(time.time() - stamp), 'stale_snapshot': bool(stale),
                'refresh_in_progress': days in _jobs and not _jobs[days].done()}
    if key:
        status = await asyncio.to_thread(_harmonization_status,key)
        metadata['harmonization'] = status
        metadata['full_harmonization_complete'] = status.get('full_harmonization_complete',False)
        metadata['harmonization_scope'] = 'ten_stage_workflow'
    if stale:
        metadata['data_source'] = 'cached_actual'
    if days in _errors:
        metadata['refresh_warning'] = 'Latest refresh failed; showing previously downloaded observations.'
    body = {**payload, 'hotspots': points, 'metadata': metadata}
    # Avoid FastAPI's repeated traversal of tens of thousands of already encoded rows.
    encoded = await asyncio.to_thread(json.dumps, body, separators=(',', ':'), allow_nan=False)
    return Response(encoded, media_type='application/json')


@router.get('/harmonization/{run_id}/status')
async def harmonization_status(run_id: str):
    try: return await asyncio.to_thread(_harmonization_status,run_id)
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc


@router.get('/harmonization/{run_id}/activity')
async def harmonization_activity(run_id: str, limit: int=Query(1000,ge=1,le=10000), offset: int=Query(0,ge=0)):
    try: folder=_run_folder(run_id)
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc
    # Parquet stays in the geospatial worker's environment. The report exports
    # JSON records for the API so its Python environment needs no extra libraries.
    path=folder/'full'/'activity.json'
    if not path.exists(): return {'status':'awaiting data','data':[], 'count':0}
    def read():
        rows=json.loads(path.read_text())
        return {'data':rows[offset:offset+limit],'count':len(rows),'offset':offset,'limit':limit,'has_more':offset+limit<len(rows)}
    return await asyncio.to_thread(read)
