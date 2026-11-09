"""Independent synchronous FIRMS client; secret URLs never enter logs/errors."""
import json
import http.client
import logging
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pipeline.daily_schema import SOURCES, parse_csv

LOG = logging.getLogger('flameseek.daily')
BASE = 'https://firms.modaps.eosdis.nasa.gov'


class FirmsClientError(RuntimeError):
    """Only safe, locally authored messages, never response text or secret URLs."""


class FirmsConfigurationError(ValueError):
    """Safe key-configuration errors without the key value."""


def retry_after(value):
    try:
        delay = float(value)
    except (TypeError, ValueError):
        try:
            delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError):
            delay = 60
    return max(1, min(600, delay))


class FirmsClient:
    def __init__(self, key, timeout=120, retries=3, opener=None, sleep=time.sleep):
        if not key or key.upper().startswith(('YOUR_', 'DEMO')):
            raise FirmsConfigurationError('FIRMS_MAP_KEY is missing or a placeholder; configure the server environment')
        self.key, self.timeout, self.retries = key, timeout, retries
        self.opener, self.sleep = opener or urllib.request.urlopen, sleep

    def url(self, source, day_range=1, start=None):
        if source not in SOURCES or not 1 <= day_range <= 5:
            raise ValueError('Unsupported source or day range (1..5)')
        suffix = '/' + date.fromisoformat(str(start)).isoformat() if start else ''
        return f'{BASE}/api/area/csv/{self.key}/{source}/world/{day_range}{suffix}'

    def _get(self, url):
        for attempt in range(self.retries + 1):
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'FlameSeek daily ingestion/1.0'})
                with self.opener(request, timeout=self.timeout) as response:
                    return response.read().decode('utf-8-sig')
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise FirmsClientError(f'FIRMS HTTP {exc.code}; request not committed') from None
                delay = max(2 ** attempt, retry_after(exc.headers.get('Retry-After', '60')) if exc.code == 429 else 0)
            except (OSError, UnicodeError, http.client.HTTPException):
                if attempt == self.retries:
                    raise FirmsClientError('FIRMS connection or response decoding failed; request not committed') from None
                delay = 2 ** attempt
            LOG.warning(json.dumps({'event': 'request_retry', 'attempt': attempt + 1, 'delay_seconds': delay}))
            self.sleep(delay)

    def availability(self):
        text = self._get(f'{BASE}/api/data_availability/csv/{self.key}/ALL')
        import csv, io
        try:
            result = {r['data_id']: (date.fromisoformat(r['min_date']), date.fromisoformat(r['max_date'])) for r in csv.DictReader(io.StringIO(text))}
            if not result:
                raise ValueError()
            return result
        except (KeyError, ValueError):
            raise FirmsClientError('FIRMS availability response invalid; no downloads attempted') from None

    def fetch(self, source, day):
        # Whole-world responses consume multiple transactions. Query authoritative
        # shared-key usage before EACH request rather than counting HTTP calls.
        try:
            usage = json.loads(self._get(f'{BASE}/mapserver/mapkey_status/?MAP_KEY={self.key}'))
            if int(usage['transaction_limit']) - int(usage['current_transactions']) < 500:
                raise FirmsClientError('FIRMS quota reserve reached; retry on next run')
        except (ValueError, KeyError, TypeError):
            raise FirmsClientError('Cannot validate FIRMS quota; retry on next run') from None
        LOG.info(json.dumps({'event': 'download', 'source': source, 'day': str(day)}))
        text = self._get(self.url(source, start=day))
        return text, parse_csv(text)
