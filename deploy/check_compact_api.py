"""Exercise the existing read-only API against an exported runtime tree, offline."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import snapshot, datasets, pipeline_status


def check(root):
    root = root.resolve()
    snapshot.ROOT = root
    snapshot.MANIFEST_PATH = root / 'data/processed/snapshot_manifest.json'
    datasets.ROOT = root
    pipeline_status.ROOT = root
    app = FastAPI()
    app.include_router(snapshot.router)
    app.include_router(datasets.router, prefix='/api')
    app.include_router(pipeline_status.router, prefix='/api')
    checks = []
    manifest = json.loads(snapshot.MANIFEST_PATH.read_text())
    bundle = json.loads((root / 'bundle-manifest.json').read_text())
    expected = {f['path']: f['sha256'] for f in bundle['files']}
    with TestClient(app) as client:
        for window in manifest['windows']:
            for route in ('/meta', '/fires', '/detections', '/grid/lambda'):
                response = client.get(route, params={'window': window, 'limit': 1, 'bbox': '88,20,93,27'})
                if response.status_code != 200:
                    raise ValueError(f'{route}/{window} returned {response.status_code}')
                checks.append(route + ':' + window)
        listing = client.get('/api/datasets')
        entries = listing.json()['datasets']
        if len(entries) != len(datasets.PUBLIC_DATASETS):
            raise ValueError('Incomplete public dataset catalogue')
        for entry in entries:
            response = client.get('/api/datasets/download/' + entry['path'])
            if response.status_code != 200 or hashlib.sha256(response.content).hexdigest() != expected[entry['path']]:
                raise ValueError('CSV download mismatch: ' + entry['path'])
        checks.append(f'{len(entries)} CSV downloads with matching SHA256')
        response = client.post('/api/pipeline/history', json={'bbox': [88, 20, 93, 27]})
        if response.status_code != 200:
            raise ValueError('Accumulated history API returned ' + str(response.status_code))
        checks.append('Accumulated history API')
    return {'status': 'passed', 'checks': checks}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.root), indent=2))
