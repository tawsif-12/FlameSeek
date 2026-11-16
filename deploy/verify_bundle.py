"""Verify every published bundle file against its recorded SHA-256 digest."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(root):
    root = root.resolve()
    report = json.loads((root / 'bundle-manifest.json').read_text(encoding='utf-8'))
    for entry in report['files']:
        path = (root / entry['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Missing or invalid file: {entry["path"]}')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if path.stat().st_size != entry['bytes'] or digest != entry['sha256']:
            raise ValueError(f'Checksum mismatch: {entry["path"]}')
    return len(report['files'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(f'Verified {verify(args.root)} files')
