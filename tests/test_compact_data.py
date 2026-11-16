import importlib.util
import json
from pathlib import Path
import sqlite3
import tarfile

import pytest

path = Path(__file__).resolve().parents[1] / 'deploy/compact_data.py'
spec = importlib.util.spec_from_file_location('compact_data', path)
compact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compact)


def fixture_root(root):
    for folder in ('backend/routers', 'data/processed/snapshots', 'dataset', 'data/raw', 'params', 'frontend/public/site-data'):
        (root / folder).mkdir(parents=True)
    (root / 'backend/routers/datasets.py').write_text("PUBLIC_DATASETS = ('dataset/input.csv',)\n")
    (root / 'dataset/input.csv').write_text('latitude,longitude\n24,90\n')
    (root / 'params/calibration.json').write_text('{}')
    (root / 'frontend/public/site-data/summary.json').write_text('{}')
    (root / 'data/raw/keep-local.csv').write_text('raw archive')
    (root / 'backend/.env').write_text('FIRMS_MAP_KEY=private-test-value')
    with sqlite3.connect(root / 'data/processed/snapshots/daily.sqlite') as con:
        con.execute('CREATE TABLE events (fire_id TEXT)')
        con.execute("INSERT INTO events VALUES ('real-event')")
    (root / 'data/processed/snapshots/old.sqlite').write_bytes(b'old generation')
    manifest = {'default_window': 'daily', 'windows': {'daily': {'snapshot_file': 'daily.sqlite'}}}
    (root / 'data/processed/snapshot_manifest.json').write_text(json.dumps(manifest))
    return root


def test_export_preserves_published_rows_and_excludes_raw_and_secrets(tmp_path):
    root = fixture_root(tmp_path / 'source')
    source = root / 'data/processed/snapshots/daily.sqlite'
    original = source.read_bytes()
    output = tmp_path / 'export'
    report = compact.export(root, output)
    assert source.read_bytes() == original
    assert report['snapshots']['data/processed/snapshots/daily.sqlite'] == {'events': 1}
    selected = {f['path'] for f in report['files']}
    assert 'dataset/input.csv' in selected
    assert 'data/raw/keep-local.csv' not in selected
    assert 'data/processed/snapshots/old.sqlite' not in selected
    assert 'backend/.env' not in selected
    with tarfile.open(output / 'flameseek-runtime.tar.gz') as archive:
        names = archive.getnames()
        assert './data/processed/snapshots/daily.sqlite' in names
        assert not any('.env' in name or 'keep-local.csv' in name for name in names)
    with pytest.raises(FileExistsError):
        compact.export(root, output)


def test_export_fails_for_missing_public_dataset(tmp_path):
    root = fixture_root(tmp_path / 'source')
    (root / 'dataset/input.csv').unlink()
    with pytest.raises(ValueError, match='Missing or out-of-root'):
        compact.select_files(root)


def test_export_rejects_snapshot_path_escape(tmp_path):
    root = fixture_root(tmp_path / 'source')
    manifest = root / 'data/processed/snapshot_manifest.json'
    manifest.write_text(json.dumps({'windows': {'daily': {'snapshot_file': '../private.sqlite'}}}))
    with pytest.raises(ValueError, match='Invalid snapshot filename'):
        compact.select_files(root)
