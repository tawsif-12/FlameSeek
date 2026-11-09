"""Adapter to existing Steps 1-4 and immutable, compatible R-Tree snapshots."""
import json
import sqlite3
import uuid
import gc
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from pipeline.daily_store import atomic_json
from pipeline.daily_schema import CORE


def publish(store, root):
    import pandas as pd
    from pipeline import ingest, quality, footprints, events, snapshot
    from pipeline.config import load_settings
    root = Path(root)
    raw_count = store.con.execute('SELECT count(*) FROM observations').fetchone()[0]
    coverage = store.coverage()
    if not coverage:
        raise ValueError('No successfully downloaded dates to publish')
    generation = 'daily_' + uuid.uuid4().hex
    work = root / 'data/work' / generation
    processed = work / 'data/processed/windows/daily'
    interim = work / 'data/interim/windows/daily'
    processed.mkdir(parents=True)
    interim.mkdir(parents=True)
    cfg = load_settings()
    cfg['window'] = dict(name='daily', start=date.fromisoformat(min(c['day'] for c in coverage)), end=date.fromisoformat(max(c['day'] for c in coverage)))
    cfg['data_version'] = generation
    previous_manifest_path = root / 'data/processed/snapshot_manifest.json'
    manifest = json.loads(previous_manifest_path.read_text(encoding='utf-8')) if previous_manifest_path.exists() else dict(windows={}, translation=cfg['translation'])
    previous_meta = manifest.get('windows', {}).get('daily', {})
    old_members = {}
    old_file = previous_meta.get('snapshot_file')
    if old_file:
        with closing(sqlite3.connect(root / 'data/processed/snapshots' / old_file)) as con:
            old_members = dict(con.execute('SELECT record_id,fire_id FROM observation_members'))
    result = None
    membership = []
    limitations = ['Steps 1-4 footprint/event reconstruction only; calibrated latent activity, diurnal correction and forecasts unavailable',
                   'Missing satellite coverage is unknown, not evidence of no fire',
                   'Publication rebuilds accumulated observations; incremental geospatial processing is not yet implemented']
    if raw_count:
        # Read only processing columns, not full provenance JSON copies. Original
        # values stay in the canonical index and raw Parquet; history is streamed.
        fields = CORE + ['bright_ti4', 'bright_ti5']
        select = ','.join("json_extract(payload,'$." + field + "') AS " + field for field in fields)
        frame = pd.read_sql_query('SELECT record_id,source AS source_file,' + select + ' FROM observations ORDER BY day,record_id', store.con)
        record_ids = frame.pop('record_id').tolist()
        frame['source_row'] = range(2, len(frame) + 2)
        for field in ('latitude', 'longitude', 'scan', 'track', 'frp', 'brightness', 'bright_t31', 'bright_ti4', 'bright_ti5'):
            frame[field] = pd.to_numeric(frame[field], errors='coerce')
        det = ingest.standardize(frame, cfg)
        del frame
        qc = quality.run(det, cfg, bbox=[-180, -90, 180, 90], quiet=True)
        del det
        for name in ('lowconf', 'removed'):
            qc[name].to_parquet(processed / (name + '.parquet'), index=False)
        limitations.extend(qc.get('not_applied', []))
        clean = qc['clean']
        del qc
        if not clean.empty:
            fp = footprints.run(clean, cfg)
            del clean
            result = events.run(fp, cfg)
            del fp
    if result:
        # Reconcile using shared source-aware detection identities, never component
        # rank. A merge retains one deterministic old ID; a split retains it on one piece.
        groups = []
        for fid, group in result['detections'].groupby('fire_id'):
            members = [record_ids[int(i)] for i in group.det_id]
            candidates = sorted({old_members[m] for m in members if m in old_members})
            groups.append((fid, members, candidates))
        used, mapping = set(), {}
        for fid, members, candidates in sorted(groups, key=lambda g: (not bool(g[2]), min(g[1]))):
            stable = next((v for v in candidates if v not in used), 'FD' + min(members)[:24])
            used.add(stable); mapping[fid] = stable
            membership.extend((m, stable) for m in members)
        for name in ('events', 'detections', 'overpasses', 'pairs'):
            if 'fire_id' in result[name]:
                result[name]['fire_id'] = result[name]['fire_id'].map(mapping)
        result['events'].to_csv(processed / 'fire_events.csv', index=False)
        result['overpasses'].to_csv(interim / 'event_overpasses.csv', index=False)
        result['detections'].drop(columns='geometry').to_parquet(processed / 'detections_clean.parquet', index=False)
        result['detections'].to_parquet(interim / 'footprints.geoparquet', index=False)
        del result, groups, old_members
        gc.collect()
        meta = snapshot.build_window('daily', root=work, cfg=cfg)
        candidate = work / 'data/processed/snapshots/daily.sqlite'
    else:
        # Explicit empty, valid dataset; no invented events or calibrated grid.
        candidate = work / 'empty.sqlite'
        with closing(sqlite3.connect(candidate)) as con:
            con.executescript('CREATE TABLE events(fire_id TEXT PRIMARY KEY,start_time TEXT,end_time TEXT,lon REAL,lat REAL,payload TEXT); CREATE TABLE overpasses(fire_id TEXT,platform TEXT,time TEXT,frp REAL); CREATE TABLE detections(fire_id TEXT,lon REAL,lat REAL,time TEXT,platform TEXT,sensor TEXT,frp REAL,conf_class TEXT); CREATE TABLE footprints(fire_id TEXT PRIMARY KEY,geojson TEXT); CREATE TABLE grid(cell_id TEXT,day TEXT,lon REAL,lat REAL,payload TEXT); CREATE TABLE metadata(key TEXT PRIMARY KEY,payload TEXT);')
            snapshot.create_event_spatial_index(con)
        meta = dict(n_events=0, n_detections=0, n_grid_rows=0, n_overpasses=0, n_footprints=0)
    now = datetime.now(timezone.utc).isoformat()
    source_latest = dict(store.con.execute("SELECT source,max(json_extract(payload,'$.observation_datetime_utc')) FROM observations GROUP BY source"))
    latest = max(source_latest.values(), default=None)
    meta.update(window='daily', data_version=generation, snapshot_file=generation + '.sqlite',
                start=cfg['window']['start'].isoformat(), end=cfg['window']['end'].isoformat(),
                now=now, now_basis='publication UTC timestamp', published_at=now,
                last_observation_time=latest, is_live=False, processing_type='NRT (may include RT/URT)',
                status='published near-real-time observations and reconstructed events',
                lambda_status='awaiting calibration and observation coverage', lambda_limitation='; '.join(map(str, limitations)),
                translation_status='calibrated forecast unavailable', source_coverage=coverage,
                raw_observation_count=raw_count, latest_observations_by_source=source_latest, limitations=limitations)
    with closing(sqlite3.connect(candidate)) as con:
        con.execute('CREATE TABLE raw_observations(record_id TEXT PRIMARY KEY,source TEXT,processing_type TEXT,time TEXT,lon REAL,lat REAL,frp REAL)')
        con.executemany('INSERT INTO raw_observations VALUES(?,?,?,?,?,?,?)',
                        store.con.execute("SELECT record_id,source,json_extract(payload,'$.processing_type'),json_extract(payload,'$.observation_datetime_utc'),CAST(json_extract(payload,'$.longitude') AS REAL),CAST(json_extract(payload,'$.latitude') AS REAL),CAST(json_extract(payload,'$.frp') AS REAL) FROM observations"))
        con.execute('CREATE INDEX raw_location_time ON raw_observations(lon,lat,time)')
        con.execute('CREATE TABLE observation_members(record_id TEXT PRIMARY KEY,fire_id TEXT)')
        con.executemany('INSERT INTO observation_members VALUES(?,?)', membership)
        con.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('meta', json.dumps(meta)))
        con.commit()
        if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Snapshot integrity check failed')
        if con.execute('SELECT count(*) FROM events').fetchone()[0] != meta['n_events']:
            raise RuntimeError('Snapshot event count mismatch')
        if con.execute('SELECT count(*) FROM event_spatial_index').fetchone()[0] != meta['n_events']:
            raise RuntimeError('Snapshot R-Tree count mismatch')
        if con.execute('SELECT count(*) FROM detections').fetchone()[0] != len(membership):
            raise RuntimeError('Snapshot membership count mismatch')
    dest = root / 'data/processed/snapshots' / meta['snapshot_file']
    dest.parent.mkdir(parents=True, exist_ok=True)
    candidate.replace(dest)
    # One atomic pointer publishes metadata AND the immutable database together.
    # Existing generations and historical windows remain available for rollback.
    manifest.setdefault('windows', {})['daily'] = meta
    manifest['default_window'] = 'daily'
    atomic_json(previous_manifest_path, manifest)
    with store.con:
        store.con.execute('DELETE FROM dirty')
    return meta
