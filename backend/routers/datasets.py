"""Downloads restricted to explicitly reviewed scientific CSV artifacts."""
import csv
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]
# Only these reviewed satellite measurements and analysis tables are public.
# New files are never exposed automatically.
PUBLIC_DATASETS = (
    'dataset/modis actual.csv',
    'dataset/viirs noa 20.csv',
    'dataset/viirs noa 21.csv',
    'dataset/viirs snpp.csv',
    'outputs/benchmark.csv',
    'outputs/himawari/detection_limit_phase3c.csv',
    'outputs/himawari/fre_daily.csv',
    'outputs/himawari/fre_overpasses.csv',
    'outputs/himawari/real_positive_controls.csv',
    'outputs/himawari/scan_statistics.csv',
    'outputs/himawari/transfer_detection_sample.csv',
    'outputs/himawari/transfer_pairs.csv',
    'outputs/himawari/viirs_event_cases.csv',
    'outputs/himawari/viirs_pixel_cases.csv',
    'outputs/naus_diagnostics/cloud_tests_by_hour.csv',
    'outputs/naus_diagnostics/hourly.csv',
    'outputs/naus_diagnostics/persistent_unmatched_locations.csv',
    'outputs/naus_diagnostics/threshold_effect_by_hour.csv',
    'outputs/naus_diagnostics/threshold_effect_day_night.csv',
    'outputs/naus_diagnostics/top10_unmatched_locations.csv',
    'outputs/naus_diagnostics/unmatched_by_1deg_cell.csv',
    'outputs/naus_diagnostics/viirs_case_status_by_hour.csv',
    'outputs/naus_diagnostics/viirs_detection_day_night.csv',
    'outputs/phase3c_naus/fire_events_fre.csv',
    'outputs/phase3c_naus/fre_daily.csv',
    'outputs/phase3c_naus/fre_overpasses.csv',
    'outputs/phase3c_naus/scan_statistics.csv',
    'outputs/phase3c_naus/transfer_pairs.csv',
    'outputs/phase3c_naus/viirs_cases.csv',
)


def dataset_file(path: str) -> Path:
    if path not in PUBLIC_DATASETS:
        raise HTTPException(404, 'Dataset not found')
    file = (ROOT / path).resolve()
    if not file.is_relative_to(ROOT) or not file.is_file():
        raise HTTPException(404, 'Dataset not found')
    return file


@router.get('/datasets')
def datasets():
    entries = []
    for path in PUBLIC_DATASETS:
        try:
            file = dataset_file(path)
            stat = file.stat()
            with file.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.reader(stream)
                columns = next(reader, [])
                has_rows = next(reader, None) is not None
        except (HTTPException, OSError):
            continue
        collection = 'Satellite input CSVs' if path.startswith('dataset/') else (
            {'himawari': 'Himawari', 'naus_diagnostics': 'Northern Australia diagnostics',
             'phase3c_naus': 'Northern Australia validation'}.get(file.parent.name, 'Benchmarks'))
        entries.append({'path': path, 'name': file.name, 'collection': collection,
                        'bytes': stat.st_size, 'columns': columns, 'has_rows': has_rows,
                        'modified': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()})
    return {'datasets': entries}


@router.get('/datasets/download/{path:path}')
def download(path: str):
    file = dataset_file(path)
    return FileResponse(file, filename=file.name, media_type='text/csv')
