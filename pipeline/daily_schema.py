"""Lossless FIRMS ingestion boundary. No inter-sensor temperature conversion."""
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone

CORE = 'latitude longitude brightness scan track acq_date acq_time satellite instrument confidence version bright_t31 frp daynight'.split()
NORMALIZED_COLUMNS = CORE + 'bright_ti4 bright_ti5 source_dataset processing_type observation_datetime_utc ingested_at_utc record_id source_values content_hash'.split()
SOURCES = {
    'MODIS_NRT': ('modis', 'MODIS', None),
    'VIIRS_SNPP_NRT': ('viirs_snpp', 'VIIRS', 'N'),
    'VIIRS_NOAA20_NRT': ('viirs_noaa20', 'VIIRS', 'N20'),
    'VIIRS_NOAA21_NRT': ('viirs_noaa21', 'VIIRS', 'N21'),
}
ALIASES = {'S-NPP': 'N', 'Suomi NPP': 'N', 'SNPP': 'N', 'NOAA-20': 'N20', 'NOAA-21': 'N21', 'T': 'Terra', 'A': 'Aqua'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def parse_csv(text):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')), strict=True)
    required = {'latitude', 'longitude', 'acq_date', 'acq_time', 'confidence', 'version', 'frp', 'scan', 'track', 'daynight'}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError('FIRMS response is not a supported CSV: required columns missing')
    rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError('Incomplete or malformed CSV row')
    return rows


def normalize(row, source, ingested_at=None):
    _, instrument, platform = SOURCES[source]
    original = dict(row)
    row = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
    satellite = ALIASES.get(row.get('satellite'), row.get('satellite')) or platform
    if satellite not in ({'Terra', 'Aqua'} if instrument == 'MODIS' else {platform}):
        raise ValueError('Source and satellite identity disagree')
    if row.get('instrument') and row['instrument'].upper() != instrument:
        raise ValueError('Source and instrument identity disagree')
    when = None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y'):
        try:
            when = datetime.strptime(row['acq_date'], fmt)
            break
        except ValueError:
            pass
    if when is None:
        raise ValueError('Invalid acquisition date')
    hhmm = str(row['acq_time'])
    if not hhmm.isdigit() or len(hhmm) > 4:
        raise ValueError('Invalid UTC HHMM acquisition time')
    hhmm = hhmm.zfill(4)
    when = when.replace(hour=int(hhmm[:2]), minute=int(hhmm[2:]), tzinfo=timezone.utc)
    for field, lower, upper in [('latitude', -90, 90), ('longitude', -180, 180)]:
        number = float(row[field])
        if not math.isfinite(number) or not lower <= number <= upper:
            raise ValueError(f'Invalid {field}')
    for field in ('brightness', 'bright_t31', 'bright_ti4', 'bright_ti5', 'frp', 'scan', 'track'):
        if row.get(field) not in (None, ''):
            number = float(row[field])
            if not math.isfinite(number) or number < 0:
                raise ValueError(f'Invalid {field}')
    confidence = row.get('confidence', '').lower()
    if instrument == 'VIIRS':
        if confidence not in ('l', 'n', 'h'):
            raise ValueError('Invalid VIIRS confidence')
    elif not 0 <= float(confidence) <= 100:
        raise ValueError('Invalid MODIS confidence')
    result = {k: row.get(k) or None for k in CORE}
    result.update(acq_date=when.date().isoformat(), acq_time=hhmm, satellite=satellite, instrument=instrument)
    result.update(bright_ti4=row.get('bright_ti4') or None, bright_ti5=row.get('bright_ti5') or None)
    if instrument == 'VIIRS':
        result.update(brightness=None, bright_t31=None)
    version = row.get('version', '').upper()
    result.update(source_dataset=source, processing_type='URT' if 'URT' in version else 'RT' if 'RT' in version and 'NRT' not in version else 'NRT',
                  observation_datetime_utc=when.isoformat(), ingested_at_utc=ingested_at or datetime.now(timezone.utc).isoformat())
    # Version, FRP and confidence can change on revision. Coordinates are used at
    # original decimal precision; relocated pixels cannot be safely inferred as revisions.
    from decimal import Decimal
    result['record_id'] = digest([source, satellite, instrument, when.isoformat(),
                                  str(Decimal(row['latitude']).normalize()), str(Decimal(row['longitude']).normalize())])
    result['source_values'] = json.dumps(original, sort_keys=True)
    result['content_hash'] = digest({k: v for k, v in result.items() if k not in ('ingested_at_utc', 'source_values')})
    return result
