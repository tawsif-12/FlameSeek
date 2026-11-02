"""Download anonymous NOAA HSD data using FlameSeek's configured UTC windows.

Default sampling is hourly; --test-hour YYYY-MM-DDTHH downloads six 10-minute
scans in one hour. JSON reports retain every missing file and access error.
"""
import argparse
import bz2
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import struct
import time

import s3fs
import yaml

ROOT = Path(__file__).resolve().parent
BANDS = ['B07', 'B14', 'B15']
SEGMENTS = ['S0310', 'S0410']
H9_START = datetime(2022, 12, 13, 5)  # JMA operational handover, UTC


def window_dates(name):
    cfg = yaml.safe_load((ROOT / 'config/settings.yaml').read_text(encoding='utf-8'))
    w = cfg['windows'][name]
    start, end = date.fromisoformat(str(w['start'])), date.fromisoformat(str(w['end']))
    if end < start:
        raise ValueError('Window end precedes start')
    return [start + timedelta(days=i) for i in range((end-start).days+1)]


def bucket_for(when):
    if not isinstance(when, datetime):
        when = datetime.combine(when, datetime.min.time())
    return ('noaa-himawari9', 'H09') if when >= H9_START else ('noaa-himawari8', 'H08')


def verify(local, item):
    if local.stat().st_size != item['size']:
        raise ValueError('Compressed size differs from S3')
    raw = local.read_bytes()
    etag = item.get('ETag', '').strip('"')
    md5 = hashlib.md5(raw).hexdigest()
    if len(etag) == 32 and '-' not in etag and md5 != etag:
        raise ValueError('S3 ETag / MD5 mismatch')
    data = bz2.decompress(raw)  # validates the bzip2 stream CRC as well
    endian = '<' if data[5] == 0 else '>'
    header, body = struct.unpack_from(endian+'II', data, 70)
    if len(data) != header + body:
        raise ValueError('HSD header/data lengths do not match decompressed file')
    blocks = {}
    offset = 0
    for _ in range(struct.unpack_from(endian+'H', data, 3)[0]):
        number, length = struct.unpack_from(endian+'BH', data, offset)
        blocks[number] = data[offset:offset+length]
        offset += length
    bits, columns, lines = struct.unpack_from(endian+'HHH', blocks[2], 3)
    full_disk = '_S0101.' in local.name
    expected_lines = 5500 if full_disk else 550
    if bits != 16 or columns != 5500 or lines != expected_lines or body != columns*lines*2:
        raise ValueError('Unexpected R20 segment dimensions')
    segment = int(local.name.split('_S')[1][:2])
    total, actual, first_line = struct.unpack_from(endian+'BBH', blocks[7], 3)
    expected_segment = (1, 1, 1) if full_disk else (10, segment, (segment-1)*550+1)
    if (total, actual, first_line) != expected_segment:
        raise ValueError('Segment header disagrees with filename')
    return {'md5': md5, 'sha256': hashlib.sha256(raw).hexdigest(),
            'uncompressed_bytes': len(data), 'columns': columns, 'lines': lines,
            'first_line': first_line, 'projection_hex': blocks[3].hex()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--window', required=True)
    ap.add_argument('--every', type=int, choices=[10,20,30,60], default=60)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--test-hour', help='UTC YYYY-MM-DDTHH; all six 10-minute scans')
    ap.add_argument('--report', help='JSON report path relative to project')
    ap.add_argument('--workers', type=int, default=12, help='Concurrent file transfers (1-32)')
    args = ap.parse_args()
    if not 1 <= args.workers <= 32:
        ap.error('--workers must be between 1 and 32')
    days = window_dates(args.window)
    if args.test_hour:
        hour = datetime.strptime(args.test_hour, '%Y-%m-%dT%H')
        if hour.date() not in days:
            ap.error('Test hour must lie inside the configured window')
        slots = [hour + timedelta(minutes=m) for m in range(0,60,10)]
    else:
        slots = [datetime.combine(d, datetime.min.time()) + timedelta(minutes=m)
                 for d in days for m in range(0,1440,args.every)]
    fs = s3fs.S3FileSystem(anon=True, client_kwargs={'region_name':'us-east-1'},
                         config_kwargs={'retries': {'max_attempts': 3},
                                        'connect_timeout':20, 'read_timeout':60})
    report = {'window':args.window, 'every_minutes':10 if args.test_hour else args.every,
              'dry_run':args.dry_run, 'test_hour':args.test_hour,
              'started_utc':datetime.now(timezone.utc).isoformat(),
              'files':[], 'missing':[], 'errors':[], 'expected_files':0,
              'archive_layout_notes':[]}
    def listing(slot):
        bucket, sat = bucket_for(slot)
        prefix = f'{bucket}/AHI-L1b-FLDK/{slot:%Y/%m/%d/%H%M}/'
        names = [f'HS_{sat}_{slot:%Y%m%d_%H%M}_{b}_FLDK_R20_{s}.DAT.bz2'
                 for b in BANDS for s in SEGMENTS]
        try:
            items = {x['name'].split('/')[-1]:x for x in fs.ls(prefix, detail=True)}
            # Early H08 archive stores a whole disk (S0101), not ten segments.
            # Use actual listed files rather than marking valid archives absent.
            for band in BANDS:
                whole = f'HS_{sat}_{slot:%Y%m%d_%H%M}_{band}_FLDK_R20_S0101.DAT.bz2'
                split = [n for n in names if f'_{band}_' in n]
                if whole in items and not any(n in items for n in split):
                    names = [n for n in names if n not in split] + [whole]
            found = [items[n] for n in names if n in items]
            return found, [prefix+n for n in names if n not in items], None, len(names)
        except FileNotFoundError:
            return [], [prefix+n for n in names], None, len(names)
        except Exception as exc:
            return [], [], {'prefix':prefix, 'error':repr(exc)}, len(names)
    with ThreadPoolExecutor(max_workers=6) as pool:
        for i, (found, missing, error, expected) in enumerate(pool.map(listing, slots),1):
            report['expected_files'] += expected
            if expected != len(BANDS)*len(SEGMENTS):
                report['archive_layout_notes'].append(f'{slots[i-1].isoformat()}: whole-disk S0101 fallback')
            report['files'].extend(found)
            report['missing'].extend(missing)
            if error:
                report['errors'].append(error)
            if i % 24 == 0 or i == len(slots):
                print(f'Listed {i}/{len(slots)} scans; {len(report["files"])} files', flush=True)
    report['available_files'] = len(report['files'])
    report['total_bytes'] = sum(x['size'] for x in report['files'])
    def download(item):
        name = item['name'].split('/')[-1]
        day = datetime.strptime(name.split('_')[2], '%Y%m%d')
        local = ROOT / 'data/raw/himawari' / args.window / day.strftime('%Y/%m/%d') / name
        local.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(3):
            try:
                if local.exists():
                    try:
                        return {'key':item['name'], 'status':'existing_verified', **verify(local,item)}
                    except Exception:
                        pass  # replace invalid local file only after new file passes verification
                partial = local.with_suffix(local.suffix+'.part')
                fs.get(item['name'], str(partial))
                # Verification needs the original filename for its segment identifier.
                integrity = verify(partial,item)
                partial.replace(local)
                return {'key':item['name'], 'status':'downloaded_verified', **integrity}
            except Exception as exc:
                last_error = repr(exc)
                time.sleep(attempt+1)
        return {'key':item['name'], 'status':'failed', 'error':last_error}
    if not args.dry_run:
        report['downloads'] = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for i, result in enumerate(pool.map(download, report['files']),1):
                report['downloads'].append(result)
                if result['status'] == 'failed':
                    report['errors'].append(result)
                    print(f'FAILED: {result}', flush=True)
                if i % 12 == 0 or i == len(report['files']):
                    print(f'Verified {i}/{len(report["files"])} files', flush=True)
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    label = 'dry_run' if args.dry_run else ('test_hour' if args.test_hour else 'download')
    path = ROOT / (args.report or f'outputs/himawari/{args.window}_{label}.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    print(f'{report["available_files"]}/{report["expected_files"]} files; '
          f'{report["total_bytes"]:,} bytes ({report["total_bytes"]/1e9:.3f} GB); '
          f'{len(report["missing"])} missing; {len(report["errors"])} errors. Report: {path}', flush=True)
    return 1 if report['missing'] or report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
