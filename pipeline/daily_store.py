"""Transactional canonical observations plus immutable raw/revision Parquet."""
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from pipeline.daily_schema import SOURCES, NORMALIZED_COLUMNS, normalize


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('w', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


@contextmanager
def run_lock(root):
    path = Path(root) / 'data/metadata/daily.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        try:
            handle.seek(0)
            if not handle.read(1):
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('Another daily pipeline run holds the lock') from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        path = self.root / 'data/metadata/observations.sqlite'
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.execute('PRAGMA journal_mode=WAL')
        self.con.execute('PRAGMA synchronous=FULL')
        self.con.executescript('''
            CREATE TABLE IF NOT EXISTS observations(record_id TEXT PRIMARY KEY,source TEXT,day TEXT,hash TEXT,payload TEXT);
            CREATE INDEX IF NOT EXISTS observations_day ON observations(day,source);
            CREATE TABLE IF NOT EXISTS downloads(source TEXT,day TEXT,attempted_at TEXT,rows INTEGER,raw_path TEXT,versions TEXT,PRIMARY KEY(source,day));
            CREATE TABLE IF NOT EXISTS dirty(source TEXT,day TEXT,PRIMARY KEY(source,day));
            CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,payload TEXT);
        ''')

    def close(self):
        self.con.close()

    def state(self):
        row = self.con.execute("SELECT payload FROM state WHERE key='run'").fetchone()
        return json.loads(row[0]) if row else {}

    def save_state(self, state):
        with self.con:
            self.con.execute("INSERT OR REPLACE INTO state VALUES('run',?)", (json.dumps(state),))
        atomic_json(self.root / 'data/metadata/pipeline_status.json', state)

    def ingest(self, source, day, text, rows, now):
        import pyarrow as pa
        import pyarrow.parquet as pq
        day = str(day)
        # Validate the entire source-day BEFORE committing any canonical records.
        records = [normalize(r, source, now) for r in rows]
        if any(r['acq_date'] != day for r in records):
            raise ValueError('Response contains observations outside requested UTC day')
        folder = self.root / 'data/raw' / SOURCES[source][0] / f'year={day[:4]}/month={day[5:7]}/day={day[8:10]}'
        folder.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        raw_path = folder / (token + '.parquet')
        # Original CSV bytes and all original source fields remain auditable.
        (folder / (token + '.csv')).write_bytes(text.encode('utf-8'))
        table = pa.Table.from_pylist(rows) if rows else pa.table({k: pa.array([], type=pa.string()) for k in (text.splitlines()[0].split(',') if text else [])})
        pq.write_table(table, raw_path.with_suffix('.tmp'))
        os.replace(raw_path.with_suffix('.tmp'), raw_path)
        stats = dict(downloaded=len(rows), inserted=0, duplicated=0, updated=0, rejected=0)
        with self.con:
            first_download = self.con.execute('SELECT 1 FROM downloads WHERE source=? AND day=?', (source, day)).fetchone() is None
            for record in records:
                previous = self.con.execute('SELECT hash FROM observations WHERE record_id=?', (record['record_id'],)).fetchone()
                if previous and previous[0] == record['content_hash']:
                    stats['duplicated'] += 1
                    continue
                # Prefer established NRT over later provisional RT/URT revisions.
                if previous:
                    old = json.loads(self.con.execute('SELECT payload FROM observations WHERE record_id=?', (record['record_id'],)).fetchone()[0])
                    priority = {'URT': 0, 'RT': 1, 'NRT': 2}
                    if priority[record['processing_type']] < priority[old['processing_type']]:
                        stats['duplicated'] += 1
                        continue
                    incoming_version = tuple(map(int, re.findall(r'\d+', record.get('version') or '')))
                    previous_version = tuple(map(int, re.findall(r'\d+', old.get('version') or '')))
                    if priority[record['processing_type']] == priority[old['processing_type']] and incoming_version < previous_version:
                        stats['duplicated'] += 1
                        continue
                stats['updated' if previous else 'inserted'] += 1
                self.con.execute('INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?)',
                                 (record['record_id'], source, day, record['content_hash'], json.dumps(record)))
            self.con.execute('INSERT OR REPLACE INTO downloads VALUES(?,?,?,?,?,?)',
                             (source, day, now, len(rows), str(raw_path.relative_to(self.root)), json.dumps(sorted({r.get('version', '') for r in rows}))))
            # Even a valid empty response updates coverage/freshness metadata.
            if first_download or stats['inserted'] or stats['updated']:
                self.con.execute('INSERT OR IGNORE INTO dirty VALUES(?,?)', (source, day))
        return stats

    def records(self):
        return [json.loads(r[0]) for r in self.con.execute('SELECT payload FROM observations ORDER BY day,record_id')]

    def export_dirty(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        for source, day in self.con.execute('SELECT source,day FROM dirty ORDER BY day,source').fetchall():
            records = [json.loads(r[0]) for r in self.con.execute('SELECT payload FROM observations WHERE source=? AND day=? ORDER BY record_id', (source, day))]
            folder = self.root / 'data/normalized' / SOURCES[source][0] / f'year={day[:4]}/month={day[5:7]}/day={day[8:10]}'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / 'part.parquet'
            schema = pa.schema([(name, pa.string()) for name in NORMALIZED_COLUMNS])
            table = pa.Table.from_pylist(records, schema=schema)
            pq.write_table(table, path.with_suffix('.tmp'))
            os.replace(path.with_suffix('.tmp'), path)

    def coverage(self):
        return [dict(r) for r in self.con.execute('SELECT source,day,attempted_at,rows FROM downloads ORDER BY day,source')]
