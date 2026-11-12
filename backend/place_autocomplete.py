"""Fresh Photon suggestions; fetch full OSM boundaries only after selection."""
import asyncio
import math
import os
import time
import re

from geocode import NOMINATIM, place_results, search_places
from http_utils import ExternalServiceError, request_json

PHOTON_URL = os.getenv('PHOTON_SEARCH_URL', 'https://photon.komoot.io/api/')


async def _photon_suggestions(query: str, limit: int = 8):
    # The older English spelling is still widely used for Chattogram.
    provider_query = re.sub(r'\bchittagong\b', 'Chattogram', query, flags=re.I)
    data = await request_json(PHOTON_URL, service='Photon place suggestions',
                              params={'q': provider_query, 'limit': limit, 'lang': 'en'},
                              ttl_seconds=0, timeout=8, retries=0)
    records = []
    for feature in (data or {}).get('features', []):
        props = feature.get('properties') or {}
        coords = (feature.get('geometry') or {}).get('coordinates')
        label = props.get('name')
        if not label or not coords or len(coords) < 2:
            continue
        lon, lat = coords[:2]
        extent = props.get('extent')
        parent = list(dict.fromkeys(props[key] for key in ('district', 'city', 'county', 'state', 'country') if props.get(key) and props[key] != label))
        records.append({'name': label, 'display_name': ', '.join([label, *parent]),
                        'lon': lon, 'lat': lat,
                        'osm_type': {'N': 'node', 'W': 'way', 'R': 'relation'}.get(props.get('osm_type')),
                        'osm_id': props.get('osm_id'), 'category': props.get('osm_key'),
                        'type': props.get('osm_value'), 'addresstype': props.get('type') or props.get('osm_value'),
                        'address': {key: props[key] for key in ('city', 'county', 'state', 'country') if props.get(key)},
                        'boundingbox': [extent[3], extent[1], extent[0], extent[2]] if extent else [lat, lat, lon, lon]})
    results = place_results(records, provider_query)
    for result in results:
        result['requires_resolution'] = bool(result.get('place_id'))
    return results


GEOCODING_URL = 'https://geocoding-api.open-meteo.com/v1'
_photon_retry_after = 0.0


def _geonames_place(item):
    name = item.get('name')
    if not name or item.get('id') is None or item.get('longitude') is None or item.get('latitude') is None:
        return None
    lon, lat = item['longitude'], item['latitude']
    parent = list(dict.fromkeys(item[key] for key in ('admin2', 'admin1', 'country') if item.get(key) and item[key] != name))
    code = item.get('feature_code', '')
    kind = 'country' if code.startswith('PCL') else 'administrative' if code.startswith('ADM') else 'city'
    return {'place_id': f"geonames:{item['id']}", 'place_name': name,
            'name': ', '.join([name, *parent]), 'parent_region': ', '.join(parent),
            'category': 'place', 'type': kind, 'addresstype': kind,
            'bbox': [lon, lat, lon, lat], 'center': [lon, lat],
            'geometry': None, 'requires_resolution': True}


async def _geonames_suggestions(query, limit):
    query = re.sub(r'\bchittagong\b', 'Chattogram', query, flags=re.I)
    data = await request_json(f'{GEOCODING_URL}/search', service='Open-Meteo place suggestions',
                              params={'name': query, 'count': limit, 'language': 'en'},
                              ttl_seconds=0, timeout=6, retries=0)
    return [place for item in (data or {}).get('results', []) if (place := _geonames_place(item))]


async def _available_photon(query, limit):
    global _photon_retry_after
    try:
        return await _photon_suggestions(query, limit)
    except ExternalServiceError:
        # Skip an unhealthy host briefly; never reuse old suggestion results.
        _photon_retry_after = time.monotonic() + 60
        raise


async def suggest_places(query: str, limit: int = 8):
    # Race independent live providers so a blocked host cannot hold up typing.
    tasks = [asyncio.create_task(_geonames_suggestions(query, limit))]
    if time.monotonic() >= _photon_retry_after:
        tasks.append(asyncio.create_task(_available_photon(query, limit)))
    error = None
    succeeded = False
    try:
        for completed in asyncio.as_completed(tasks):
            try:
                results = await completed
                succeeded = True
                if results:
                    return results
            except ExternalServiceError as exc:
                error = exc
        if not succeeded and error:
            raise error
        return []
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def resolve_place(place_id: str):
    if place_id.startswith('geonames:'):
        data = await request_json(f'{GEOCODING_URL}/get', service='Open-Meteo location lookup',
                                  params={'id': place_id.split(':')[1], 'language': 'en'},
                                  ttl_seconds=0, timeout=8, retries=0)
        point = _geonames_place(data or {})
        if not point:
            return None
        # Query OSM only after selection, never for every keystroke.
        candidates = await search_places(', '.join(filter(None, [data['name'], data.get('country')])), fresh=True)
        lon, lat = point['center']
        def distance(candidate):
            x, y = candidate['center']
            return math.hypot((x - lon) * math.cos(math.radians(lat)), y - lat)
        nearby = [candidate for candidate in candidates if distance(candidate) < 0.5]
        # An extent or point is never passed off as a real administrative boundary.
        return min(nearby, key=distance) if nearby else point
    _, kind, number = place_id.split(':')
    code = {'node': 'N', 'way': 'W', 'relation': 'R'}[kind] + number
    data = await request_json(f'{NOMINATIM}/lookup', service='Nominatim boundary lookup',
                              params={'osm_ids': code, 'format': 'jsonv2', 'polygon_geojson': 1,
                                      'polygon_threshold': 0.005, 'addressdetails': 1, 'namedetails': 1,
                                      'accept-language': 'en'},
                              ttl_seconds=0, timeout=15, retries=0)
    results = place_results(data, '')
    return next((result for result in results if result.get('place_id') == place_id), None)
