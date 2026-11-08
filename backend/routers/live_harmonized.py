"""Run the established procedure in its geospatial Python environment."""
import asyncio
import hashlib
import json
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from firms_client import fetch_recent_hotspots, recent_source_status, FirmsAPIError
from config import DEFAULT_SENSORS

router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]
_lock = asyncio.Lock()


def compute(rows):
    encoded = json.dumps(jsonable_encoder(rows), sort_keys=True)
    key = hashlib.sha256(('live-v1' + encoded).encode()).hexdigest()[:24]
    folder = ROOT / '.runlogs' / 'live_harmonized'
    folder.mkdir(parents=True, exist_ok=True)
    source, target = folder / f'{key}.input.json', folder / f'{key}.json'
    if not target.exists():
        source.write_text(encoded, encoding='utf-8')
        proc = subprocess.run([os.getenv('FLAMESEEK_PIPELINE_PYTHON', r'E:\anaconda\envs\flameseek\python.exe'),
                               '-m', 'pipeline.live_globe', str(source), str(target)],
                              cwd=ROOT, capture_output=True, text=True, timeout=300)
        if proc.returncode:
            raise RuntimeError(proc.stderr[-2000:])
    return json.loads(target.read_text(encoding='utf-8'))


@router.get('/harmonized_hotspots')
async def harmonized_hotspots(days: int = Query(1, ge=1, le=5), limit: int = Query(4000, ge=1, le=20000)):
    try:
        rows = await fetch_recent_hotspots(None, DEFAULT_SENSORS, days, include_demo=False)
        source_status = recent_source_status()
        async with _lock:
            result = await asyncio.to_thread(compute, rows)
    except (FirmsAPIError, RuntimeError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(502, detail={'message': f'Procedure harmonization unavailable: {exc}'}) from exc
    points = sorted(result['hotspots'], key=lambda p: p.get('frp') or 0, reverse=True)
    return {'hotspots': points[:limit], 'raw_hotspots': rows, 'metadata': {**result['metadata'],
            'returned_hotspot_count': min(limit, len(points)), 'data_source': source_status}}
