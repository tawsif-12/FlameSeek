import csv
import io
import json
import sqlite3
from datetime import date
from pathlib import Path
import pytest
from pipeline.daily import run
from pipeline.daily_client import FirmsClient
from pipeline.daily_schema import CORE, normalize, parse_csv
from pipeline.daily_store import Store, run_lock


def observation(day='2026-11-08', **changes):
    return {**dict(zip(CORE, ['24.000000', '90.000000', '330.125', '1', '1', day, '0005', 'Aqua', 'MODIS', '90', '6.1NRT', '290.125', '12.45', 'N'])), **changes}


def csv_text(rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]) if rows else CORE)
    writer.writeheader(); writer.writerows(rows)
    return buffer.getvalue()


class FakeClient:
    def __init__(self, rows=None, fail=False):
        self.rows = rows or {}; self.fail = fail; self.calls = []

    def availability(self):
        return {'MODIS_NRT': (date(2026, 1, 1), date(2026, 11, 9))}

    def fetch(self, source, day):
        self.calls.append((source, day))
        if self.fail:
            raise TimeoutError('secret URL must never appear in state')
        rows = self.rows.get(str(day), [])
        return csv_text(rows), rows


def execute(root, client, **kwargs):
    return run(root, client=client, today=date(2026, 11, 9), sources=['MODIS_NRT'], backfill_days=2, **kwargs)


def snapshot(root):
    manifest = json.loads((root / 'data/processed/snapshot_manifest.json').read_text())
    return root / 'data/processed/snapshots' / manifest['windows']['daily']['snapshot_file']


def test_url_and_csv_validation():
    client = FirmsClient('test-key')
    assert client.url('MODIS_NRT', 3) == 'https://firms.modaps.eosdis.nasa.gov/api/area/csv/test-key/MODIS_NRT/world/3'
    assert client.url('VIIRS_NOAA21_NRT', start='2026-11-09').endswith('/VIIRS_NOAA21_NRT/world/1/2026-11-09')
    for text in ('Invalid MAP_KEY', 'latitude,longitude\n24,90', csv_text([observation()]) + '24,90\n'):
        with pytest.raises(ValueError):
            parse_csv(text)
    assert parse_csv(csv_text([])) == []


def test_normalization():
    row = normalize(observation(), 'MODIS_NRT')
    assert list(row)[:14] == CORE
    assert row['acq_time'] == '0005'
    assert row['observation_datetime_utc'] == '2026-11-08T00:05:00+00:00'
    assert row['brightness'] == '330.125'
    viirs = normalize(observation(satellite='N20', instrument='VIIRS', confidence='n', bright_ti4='340.12345', bright_ti5='295.2'), 'VIIRS_NOAA20_NRT')
    assert viirs['brightness'] is None and viirs['bright_t31'] is None
    assert viirs['bright_ti4'] == '340.12345' and viirs['confidence'] == 'n'
    missing = normalize(observation(satellite='N20', instrument='VIIRS', confidence='h', frp=''), 'VIIRS_NOAA20_NRT')
    assert missing['bright_ti4'] is None and missing['frp'] is None
    assert normalize(observation(latitude='24.0'), 'MODIS_NRT')['record_id'] == row['record_id']


@pytest.mark.parametrize('changes', [{'latitude': '91'}, {'longitude': 'nan'}, {'acq_time': '2400'}, {'acq_time': '1260'}, {'satellite': 'N20'}, {'frp': '-1'}])
def test_invalid_observations(changes):
    with pytest.raises(ValueError):
        normalize(observation(**changes), 'MODIS_NRT')


def test_idempotence_revision_raw_retention(tmp_path):
    store = Store(tmp_path)
    try:
        row = observation()
        assert store.ingest('MODIS_NRT', '2026-11-08', csv_text([row]), [row], 'now')['inserted'] == 1
        assert store.ingest('MODIS_NRT', '2026-11-08', csv_text([row]), [row], 'later')['duplicated'] == 1
        row = observation(frp='15.123', version='6.2NRT')
        assert store.ingest('MODIS_NRT', '2026-11-08', csv_text([row]), [row], 'later')['updated'] == 1
        store.export_dirty()
        assert len(store.records()) == 1
        assert len(list((tmp_path / 'data/raw').rglob('*.parquet'))) == 3
        assert store.records()[0]['frp'] == '15.123'
        stale = observation(frp='5', version='6.1NRT')
        assert store.ingest('MODIS_NRT', '2026-11-08', csv_text([stale]), [stale], 'later')['duplicated'] == 1
        assert store.records()[0]['frp'] == '15.123'
    finally:
        store.close()


def test_full_pipeline_history_midnight_stability_and_recovery(tmp_path):
    first = observation(acq_time='2359')
    state = execute(tmp_path, FakeClient({'2026-11-08': [first]}))
    assert state['status'] == 'success'
    with sqlite3.connect(snapshot(tmp_path)) as con:
        event_id = con.execute('SELECT fire_id FROM events').fetchone()[0]
    later = observation('2026-11-09', acq_time='0001', frp='20')
    state = execute(tmp_path, FakeClient({'2026-11-08': [first], '2026-11-09': [later]}))
    assert state['counts']['inserted'] == 1 and state['counts']['duplicated'] == 1
    with sqlite3.connect(snapshot(tmp_path)) as con:
        assert con.execute('SELECT fire_id FROM events').fetchone()[0] == event_id
        assert con.execute('SELECT count(*) FROM events').fetchone()[0] == 1
        assert con.execute('SELECT count(*) FROM raw_observations').fetchone()[0] == 2
        assert con.execute('SELECT count(*) FROM event_spatial_index').fetchone()[0] == 1
        payload = json.loads(con.execute('SELECT payload FROM events').fetchone()[0])
        assert payload['n_detections'] == 2
    failed = execute(tmp_path, FakeClient(fail=True))
    assert failed['status'] == 'partial' and failed['last_successful_run'] == state['last_successful_run']
    assert 'secret URL' not in json.dumps(failed)
    recovered = execute(tmp_path, FakeClient({'2026-11-08': [first], '2026-11-09': [later]}))
    assert recovered['counts']['inserted'] == 0
    # Late arriving new pixel and revised original are both recovered.
    revised = observation(acq_time='2359', frp='30', version='6.2NRT')
    late = observation(longitude='91')
    state = execute(tmp_path, FakeClient({'2026-11-08': [revised, late]}))
    assert state['counts']['updated'] == 1 and state['counts']['inserted'] == 1
    assert state['latest_published_snapshot']['raw_observation_count'] == 3


def test_empty_valid_response_and_lock(tmp_path):
    assert execute(tmp_path, FakeClient())['latest_published_snapshot']['n_events'] == 0
    with run_lock(tmp_path):
        with pytest.raises(RuntimeError):
            with run_lock(tmp_path):
                pass


def test_publication_failure_retains_pointer_and_dirty(tmp_path, monkeypatch):
    execute(tmp_path, FakeClient({'2026-11-08': [observation()]}))
    old = snapshot(tmp_path)
    import pipeline.daily_publish as publisher
    original = publisher.atomic_json
    def fail(path, value):
        raise OSError('publication interrupted')
    monkeypatch.setattr(publisher, 'atomic_json', fail)
    with pytest.raises(OSError):
        execute(tmp_path, FakeClient({'2026-11-09': [observation('2026-11-09')]}))
    assert snapshot(tmp_path) == old
    store = Store(tmp_path)
    assert store.con.execute('SELECT count(*) FROM dirty').fetchone()[0] > 0
    store.close()
    monkeypatch.setattr(publisher, 'atomic_json', original)
    assert execute(tmp_path, None, publish_only=True)['status'] == 'success'


def test_client_quota_retry_and_secret_redaction():
    import urllib.error
    calls, sleeps = [], []
    def opener(request, timeout):
        calls.append(request.full_url)
        if 'mapkey_status' in request.full_url:
            return io.BytesIO(b'{"transaction_limit":5000,"current_transactions":1}')
        if len(calls) == 2:
            raise urllib.error.URLError('network interruption containing secret')
        return io.BytesIO(csv_text([observation()]).encode())
    client = FirmsClient('secret', opener=opener, sleep=sleeps.append)
    assert len(client.fetch('MODIS_NRT', date(2026, 11, 8))[1]) == 1
    assert sleeps == [1]
    def limit(request, timeout):
        return io.BytesIO(b'{"transaction_limit":5000,"current_transactions":4900}')
    with pytest.raises(RuntimeError, match='quota reserve'):
        FirmsClient('secret', opener=limit).fetch('MODIS_NRT', date(2026, 11, 8))
    def invalid(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, 'secret', {}, None)
    with pytest.raises(RuntimeError) as exc:
        FirmsClient('secret', opener=invalid)._get('https://example/secret')
    assert 'secret' not in str(exc.value)


def test_invalid_source_day_transaction_is_not_committed(tmp_path):
    store = Store(tmp_path)
    row = observation()
    store.ingest('MODIS_NRT', '2026-11-08', csv_text([row]), [row], 'now')
    with pytest.raises(ValueError):
        store.ingest('MODIS_NRT', '2026-11-08', csv_text([row]), [row, observation(latitude='100')], 'later')
    assert len(store.records()) == 1
    with pytest.raises(ValueError):
        store.ingest('MODIS_NRT', '2026-11-09', csv_text([row]), [row], 'later')
    store.close()


def test_identical_run_skips_geospatial_rebuild(tmp_path, monkeypatch):
    rows = {'2026-11-08': [observation()]}
    execute(tmp_path, FakeClient(rows))
    old = snapshot(tmp_path)
    def unexpected(*args):
        raise AssertionError('Unchanged observations should not be reclustered')
    monkeypatch.setattr('pipeline.daily_publish.publish', unexpected)
    state = execute(tmp_path, FakeClient(rows))
    assert state['status'] == 'success' and snapshot(tmp_path) == old


def test_missing_key_run_state(tmp_path, monkeypatch):
    monkeypatch.delenv('FIRMS_MAP_KEY', raising=False)
    with pytest.raises(ValueError):
        execute(tmp_path, None)
    status = json.loads((tmp_path / 'data/metadata/pipeline_status.json').read_text())
    assert status['status'] == 'failed'
    assert not (tmp_path / 'data/processed/snapshot_manifest.json').exists()


def test_client_quota_retry_and_secret_redaction():
    import urllib.error
    calls, sleeps = [], []
    def opener(request, timeout):
        calls.append(request.full_url)
        if 'mapkey_status' in request.full_url:
            return io.BytesIO(b'{"transaction_limit":5000,"current_transactions":1}')
        if len(calls) == 2:
            raise urllib.error.URLError('network interruption containing secret')
        return io.BytesIO(csv_text([observation()]).encode())
    client = FirmsClient('secret', opener=opener, sleep=sleeps.append)
    assert len(client.fetch('MODIS_NRT', date(2026, 11, 8))[1]) == 1
    assert sleeps == [1]
    def limit(request, timeout):
        return io.BytesIO(b'{"transaction_limit":5000,"current_transactions":4900}')
    with pytest.raises(RuntimeError, match='quota reserve'):
        FirmsClient('secret', opener=limit).fetch('MODIS_NRT', date(2026, 11, 8))
    def invalid(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, 'secret', {}, None)
    with pytest.raises(RuntimeError) as exc:
        FirmsClient('secret', opener=invalid)._get('https://example/secret')
    assert 'secret' not in str(exc.value)


def test_invalid_source_day_transaction_is_not_committed(tmp_path):
    store = Store(tmp_path)
    row = observation()
    store.ingest('MODIS_NRT', '2026-11-08', csv_text([row]), [row], 'now')
    with pytest.raises(ValueError):
        store.ingest('MODIS_NRT', '2026-11-08', csv_text([row]), [row, observation(latitude='100')], 'later')
    assert len(store.records()) == 1
    with pytest.raises(ValueError):
        store.ingest('MODIS_NRT', '2026-11-09', csv_text([row]), [row], 'later')
    store.close()


def test_identical_run_skips_geospatial_rebuild(tmp_path, monkeypatch):
    rows = {'2026-11-08': [observation()]}
    execute(tmp_path, FakeClient(rows))
    old = snapshot(tmp_path)
    def unexpected(*args):
        raise AssertionError('Unchanged observations should not be reclustered')
    monkeypatch.setattr('pipeline.daily_publish.publish', unexpected)
    state = execute(tmp_path, FakeClient(rows))
    assert state['status'] == 'success' and snapshot(tmp_path) == old


def test_missing_key_run_state(tmp_path, monkeypatch):
    monkeypatch.delenv('FIRMS_MAP_KEY', raising=False)
    with pytest.raises(ValueError):
        execute(tmp_path, None)
    status = json.loads((tmp_path / 'data/metadata/pipeline_status.json').read_text())
    assert status['status'] == 'failed'
    assert not (tmp_path / 'data/processed/snapshot_manifest.json').exists()
