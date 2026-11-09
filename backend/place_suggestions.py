"""Local autocomplete over previously retrieved OSM places, without network calls."""
import json
import time
import unicodedata
from difflib import SequenceMatcher

from config import CACHE_DIR
from geocode import place_results

_records = []
_loaded_at = 0.0


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


def cached_places(query: str, limit: int = 8):
    global _records, _loaded_at
    if time.monotonic() - _loaded_at > 30:
        records = {}
        for path in (CACHE_DIR / 'nominatim').rglob('*.txt'):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            # Search arrays have named places and bounding geometry; reverse
            # lookups are deliberately excluded from autocomplete.
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict) or not item.get('display_name') or not item.get('lat') or not item.get('lon'):
                    continue
                key = (item.get('osm_type'), item.get('osm_id'))
                if key not in records or item.get('geojson'):
                    records[key] = item
        _records = list(records.values())
        _loaded_at = time.monotonic()
    target = normalized(query)
    if len(target) < 2:
        return []
    ranked = []
    for item in _records:
        names = [item.get('name', ''), item['display_name'].split(',')[0], *(item.get('namedetails') or {}).values()]
        names = [normalized(name) for name in names if name]
        score = max((1.0 if target == name else .95 if name.startswith(target) else .85 if target in name else SequenceMatcher(None, target, name).ratio() if len(target) >= 4 else 0 for name in names), default=0)
        if score >= .7:
            ranked.append((score, item))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return place_results([item for _, item in ranked[:limit]], query)
