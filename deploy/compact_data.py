"""Export the website's published data without raw archives or pipeline intermediates.

Original files are read only. SQLite is copied through its backup API and compacted
on the COPY. Never use this export as a replacement for the full scientific archive.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def public_datasets(root):
    tree = ast.parse((root / 'backend/routers/datasets.py').read_text(encoding='utf-8'))
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'PUBLIC_DATASETS' for t in n.targets))


def select_files(root):
    manifest_path = root / 'data/processed/snapshot_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    paths = {'data/processed/snapshot_manifest.json', *public_datasets(root)}
    for window, entry in manifest['windows'].items():
        filename = entry.get('snapshot_file', window + '.sqlite')
        if Path(filename).name != filename:
            raise ValueError(f'Invalid snapshot filename for {window}')
        paths.add('data/processed/snapshots/' + filename)
    for folder in ('params', 'frontend/public/site-data', 'data/interim/tle'):
        paths.update(p.relative_to(root).as_posix() for p in (root / folder).glob('*.json'))
    for relative in ('data/processed/drift_by_year.csv', 'data/metadata/pipeline_status.json'):
        if (root / relative).is_file():
            paths.add(relative)
    # Additional independent calibration/opportunity inputs, if explicitly configured.
    evidence = root / 'config/harmonization_evidence.json'
    if evidence.exists():
        paths.add(evidence.relative_to(root).as_posix())
        for value in json.loads(evidence.read_text(encoding='utf-8')).values():
            paths.add((evidence.parent / value).resolve().relative_to(root).as_posix())
    for relative in paths:
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f'Missing or out-of-root runtime input: {relative}')
    return sorted(paths), manifest_path.read_bytes()


def sqlite_copy(source, target):
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst, pages=1024)
            # SQLite VACUUM needs a disk-backed temporary copy. Keep it beside
            # the export rather than filling a small system temp partition.
            temp_dir = target.parent / '.sqlite-tmp'
            temp_dir.mkdir(exist_ok=True)
            quoted = str(temp_dir).replace("'", "''")
            dst.execute(f"PRAGMA temp_store_directory='{quoted}'")
            dst.execute('VACUUM')
            if dst.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError(f'Invalid SQLite copy: {source.name}')
            tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts = {}
            for table in ('events', 'detections', 'footprints', 'overpasses', 'grid', 'raw_observations'):
                if table in tables:
                    before = src.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                    after = dst.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                    if before != after:
                        raise ValueError(f'SQLite row count changed: {source.name}/{table}')
                    counts[table] = after
    return counts


def export(root, output):
    root, output = root.resolve(), output.resolve()
    paths, original_manifest = select_files(root)
    # Fail rather than overwrite an earlier export or touch original datasets.
    output.mkdir(parents=True, exist_ok=False)
    runtime = output / 'runtime'
    report = {'profile': 'published-website', 'files': [], 'snapshots': {},
              'omitted': ['raw satellite archives', 'pipeline intermediates and partitions',
                          'unreferenced snapshot generations', 'canonical ingestion database',
                          'rebuildable HTTP/history/model caches', 'logs and secrets'],
              'live_firms': 'unchanged; backend FIRMS_MAP_KEY and network required',
              'predictions': 'existing on-demand code; history/weather fetched again; validation may withhold results',
              'daily_ingestion': 'disabled; this export is not an ingestion checkpoint'}
    for relative in paths:
        source, target = root / relative, runtime / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = source.stat()
        if source.suffix == '.sqlite':
            print(f'Backing up and checking {relative}', flush=True)
            report['snapshots'][relative] = sqlite_copy(source, target)
        else:
            shutil.copy2(source, target)
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError(f'Input changed during export: {relative}; retry after writers finish')
        with target.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        report['files'].append({'path': relative, 'bytes': target.stat().st_size, 'sha256': digest})
    if (root / 'data/processed/snapshot_manifest.json').read_bytes() != original_manifest:
        raise ValueError('Snapshot manifest changed during export; retry after ingestion finishes')
    report['runtime_bytes'] = sum(f['bytes'] for f in report['files'])
    inventory = root / 'deploy/data-inventory.json'
    if inventory.exists():
        original = json.loads(inventory.read_text())
        report['previous_full_inventory_bytes'] = sum(v['bytes'] for v in original['folders'].values())
        report['reduction_percent'] = round(100 * (1-report['runtime_bytes']/report['previous_full_inventory_bytes']), 2)
    (runtime / 'bundle-manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    # Mutable runtime folders start empty. Do not ship caches with stale provider data.
    for folder in ('backend/cache', 'data/raw', 'data/places', 'outputs'):
        (runtime / folder).mkdir(parents=True, exist_ok=True)
    archive = output / 'flameseek-runtime.tar.gz'
    print('Compressing published website bundle', flush=True)
    with tarfile.open(archive, 'w:gz', compresslevel=1) as tar:
        tar.add(runtime, arcname='.', recursive=True)
    report['archive_bytes'] = archive.stat().st_size
    with archive.open('rb') as stream:
        report['archive_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('files', 'snapshots')}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'deploy/bundles/compact')
    args = parser.parse_args()
    export(ROOT, args.output)
