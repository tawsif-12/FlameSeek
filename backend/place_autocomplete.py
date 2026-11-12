"""Fresh Photon suggestions; fetch full OSM boundaries only after selection."""
import os
import re

from geocode import NOMINATIM, place_results
from http_utils import request_json

PHOTON_URL = os.getenv('PHOTON_SEARCH_URL', 'https://photon.komoot.io/api/')


async def suggest_places(query: str, limit: int = 8):
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


async def resolve_place(place_id: str):
    _, kind, number = place_id.split(':')
    code = {'node': 'N', 'way': 'W', 'relation': 'R'}[kind] + number
    data = await request_json(f'{NOMINATIM}/lookup', service='Nominatim boundary lookup',
                              params={'osm_ids': code, 'format': 'jsonv2', 'polygon_geojson': 1,
                                      'polygon_threshold': 0.005, 'addressdetails': 1, 'namedetails': 1,
                                      'accept-language': 'en,bn'},
                              ttl_seconds=0, timeout=15, retries=0)
    results = place_results(data, '')
    return next((result for result in results if result.get('place_id') == place_id), None)
