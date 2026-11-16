"""Inventory deployment data and verify snapshot and public dataset references."""
import argparse
import ast
import json
import os
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ('data', 'dataset', 'outputs', 'params', 'backend/cache', 'frontend/public/site-data')


def folder_size(folder):
    count = size = 0
    pending = [str(folder)]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    pending.append(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    count += 1
                    size += entry.stat().st_size
    return {'files': count, 'bytes': size}


def inspect(root=ROOT):
    report = {'folders': {}, 'snapshots': [], 'missing_public_datasets': [], 'errors': []}
    for name in FOLDERS:
        folder = root / name
        report['folders'][name] = folder_size(folder) if folder.is_dir() else {'files': 0, 'bytes': 0}
        print(f'Checked {name}: {report["folders"][name]}', flush=True)
        if not folder.is_dir():
            report['errors'].append(f'Missing directory: {name}')
    tree = ast.parse((root / 'backend/routers/datasets.py').read_text(encoding='utf-8'))
    paths = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PUBLIC_DATASETS' for t in node.targets))
    report['public_datasets'] = len(paths)
    report['missing_public_datasets'] = [p for p in paths if not (root / p).is_file()]
    report['errors'].extend(f'Missing public dataset: {p}' for p in report['missing_public_datasets'])
    manifest_path = root / 'data/processed/snapshot_manifest.json'
    if not manifest_path.is_file():
        report['errors'].append('Missing snapshot manifest')
    else:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        report['default_window'] = manifest.get('default_window')
        for window, entry in manifest.get('windows', {}).items():
            filename = entry.get('snapshot_file', window + '.sqlite')
            if Path(filename).name != filename:
                report['errors'].append(f'Invalid snapshot filename: {window}')
                continue
            path = root / 'data/processed/snapshots' / filename
            status = {'window': window, 'file': filename, 'exists': path.is_file()}
            if path.is_file():
                try:
                    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as con:
                        status['quick_check'] = con.execute('PRAGMA quick_check').fetchone()[0]
                    if status['quick_check'] != 'ok':
                        report['errors'].append(f'Corrupt snapshot: {window}')
                except sqlite3.Error as exc:
                    report['errors'].append(f'Cannot read snapshot {window}: {exc}')
            else:
                report['errors'].append(f'Missing snapshot: {window}')
            report['snapshots'].append(status)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = inspect()
    result = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result + '\n', encoding='utf-8')
    print(result)
    raise SystemExit(bool(report['errors']))
