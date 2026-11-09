"""Daily ingestion CLI; scheduler is external to FastAPI workers."""
import argparse
import csv
import io
import json
import logging
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from pipeline.daily_schema import SOURCES, ALIASES
from pipeline.daily_store import Store, run_lock

ROOT = Path(__file__).resolve().parents[1]


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def load_env(root):
    # Environment takes precedence. Only server-side key/configuration is loaded.
    path = Path(root) / 'backend/.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if key.strip().startswith(('FIRMS_', 'FLAMESEEK_')):
                    os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


def import_existing(store, root):
    """Bootstrap the four existing flat exports without changing source files."""
    groups = {}
    for file in sorted((Path(root) / 'data/raw').glob('*.csv')):
        with file.open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle):
                sat = ALIASES.get(row.get('satellite'), row.get('satellite'))
                source = 'MODIS_NRT' if row.get('instrument', '').upper() == 'MODIS' else {'N': 'VIIRS_SNPP_NRT', 'N20': 'VIIRS_NOAA20_NRT', 'N21': 'VIIRS_NOAA21_NRT'}.get(sat)
                if source is None:
                    raise ValueError('Existing CSV has unknown satellite identity')
                raw_date = row['acq_date']
                day = datetime.strptime(raw_date, '%m/%d/%Y').date() if '/' in raw_date else date.fromisoformat(raw_date)
                groups.setdefault((source, day), []).append(row)
    for (source, day), rows in groups.items():
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
        store.ingest(source, day, buffer.getvalue(), rows, utcnow())
    return len(groups)


def run(root=ROOT, *, client=None, today=None, backfill_days=3, lookback=3,
        sources=None, publish_only=False, seed=False, start=None, end=None):
    from pipeline.daily_client import FirmsClient, FirmsClientError, FirmsConfigurationError
    from pipeline.daily_publish import publish
    root = Path(root)
    today = today or datetime.now(timezone.utc).date()
    sources = sources or list(SOURCES)
    if lookback < 1 or backfill_days < 1 or any(s not in SOURCES for s in sources):
        raise ValueError('Invalid lookback, backfill or source configuration')
    with run_lock(root):
        store = Store(root)
        previous = store.state()
        state = {**previous, 'run_id': uuid.uuid4().hex, 'last_attempted_run': utcnow(), 'status': 'running',
                 'failure': None, 'failures': [], 'counts': dict(downloaded=0, inserted=0, duplicated=0, updated=0, rejected=0),
                 'enabled_sources': sources}
        store.save_state(state)
        try:
            if seed:
                state['seeded_source_days'] = import_existing(store, root)
            if not publish_only:
                client = client or FirmsClient(os.getenv('FIRMS_MAP_KEY', ''))
                available = client.availability()
                state['source_availability'] = {source: {'start': str(limits[0]), 'end': str(limits[1])} for source, limits in available.items() if source in sources}
                until = end or today
                if start and start > until:
                    raise ValueError('Start date must not be after end date')
                state['unavailable_source_days'] = []
                for source in sources:
                    dates = [date.fromisoformat(r[0]) for r in store.con.execute('SELECT day FROM downloads WHERE source=?', (source,))]
                    # Recover holes from the beginning of collected coverage, and
                    # refresh overlapping source-days even after a partial failure.
                    first = start or min(min(dates, default=until), until - timedelta(days=backfill_days - 1))
                    refresh_from = until - timedelta(days=lookback - 1)
                    known = set(dates)
                    day = first
                    while day <= until:
                        if day not in known or day >= refresh_from:
                            limits = available.get(source)
                            if not limits or not limits[0] <= day <= limits[1]:
                                state['unavailable_source_days'].append({'source': source, 'day': str(day)})
                            else:
                                rows = []
                                try:
                                    text, rows = client.fetch(source, day)
                                    stats = store.ingest(source, day, text, rows, utcnow())
                                    for key, value in stats.items():
                                        state['counts'][key] += value
                                    logging.getLogger('flameseek.daily').info(json.dumps({'event': 'ingested', 'source': source, 'day': str(day), **stats}))
                                except Exception as exc:
                                    # Never include request URLs, response text or keys.
                                    state['failures'].append({'source': source, 'day': str(day), 'error_type': type(exc).__name__,
                                                              'reason': str(exc) if isinstance(exc, FirmsClientError) else 'Source-day validation or persistence failed; existing data retained'})
                                    state['counts']['downloaded'] += len(rows)
                                    if isinstance(exc, ValueError):
                                        state['counts']['rejected'] += len(rows)
                        day += timedelta(days=1)
                state['last_successful_ingestion'] = utcnow() if not state['failures'] and not state['unavailable_source_days'] else previous.get('last_successful_ingestion')
            store.export_dirty()
            state['affected_partitions'] = [dict(r) for r in store.con.execute('SELECT source,day FROM dirty ORDER BY day,source')]
            if state['affected_partitions'] or publish_only or not previous.get('latest_published_snapshot'):
                meta = publish(store, root)
            else:
                manifest_path = root / 'data/processed/snapshot_manifest.json'
                meta = json.loads(manifest_path.read_text(encoding='utf-8'))['windows']['daily']
            state.update(latest_published_snapshot=meta, latest_observation_time=meta['last_observation_time'],
                         processed_record_counts={'raw': meta['raw_observation_count'], 'detections': meta['n_detections'], 'events': meta['n_events']})
            incomplete = bool(state['failures'] or state.get('unavailable_source_days'))
            state['status'] = 'partial' if incomplete else 'success'
            state['last_published_run'] = utcnow()
            if not incomplete:
                state['last_successful_run'] = utcnow()
            state['failure'] = 'Some source dates unavailable or failed; retained previous observations and published verified data' if incomplete else None
            state['finished_at'] = utcnow()
            store.save_state(state)
            return state
        except BaseException as exc:
            safe_reason = str(exc) if isinstance(exc, (FirmsClientError, FirmsConfigurationError)) else f'{type(exc).__name__}: daily workflow incomplete; see source-day status and retry'
            state.update(status='failed', failure=safe_reason, finished_at=utcnow())
            store.save_state(state)
            raise
        finally:
            store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', 'backfill', 'publish', 'status', 'import-existing'])
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--days', type=int, default=3)
    parser.add_argument('--lookback', type=int, default=None)
    parser.add_argument('--start', type=date.fromisoformat)
    parser.add_argument('--end', type=date.fromisoformat)
    parser.add_argument('--sources', nargs='+', choices=list(SOURCES))
    args = parser.parse_args()
    load_env(args.root)
    if args.command == 'status':
        path = args.root / 'data/metadata/pipeline_status.json'
        print(path.read_text(encoding='utf-8') if path.exists() else '{"status":"not_started"}')
        return
    folder = args.root / 'data/logs'
    folder.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(message)s', handlers=[logging.StreamHandler(), logging.FileHandler(folder / 'daily.jsonl', encoding='utf-8')])
    try:
        state = run(args.root, backfill_days=args.days,
                    lookback=args.lookback or int(os.getenv('FIRMS_DAILY_LOOKBACK_DAYS', '3')),
                    sources=args.sources or [s.strip() for s in os.getenv('FIRMS_DAILY_SOURCES', ','.join(SOURCES)).split(',') if s.strip()],
                    publish_only=args.command in ('publish', 'import-existing'), seed=args.command == 'import-existing',
                    start=args.start, end=args.end)
        print(json.dumps({'status': state['status'], 'counts': state['counts'], 'failure': state['failure']}))
        if state['status'] != 'success':
            sys.exit(2)
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'message': 'Run incomplete; inspect pipeline status and retry'}))
        sys.exit(1)


if __name__ == '__main__':
    main()
