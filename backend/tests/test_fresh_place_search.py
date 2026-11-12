import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

import geocode
import place_autocomplete as autocomplete
from routers import places


def test_live_suggestions_bypass_cache_and_preserve_osm_identity(monkeypatch):
    calls = []

    async def provider(url, **kwargs):
        calls.append((url, kwargs))
        return {'features': [{'properties': {'name': 'Chattogram District', 'osm_type': 'R',
                    'osm_id': 3824577, 'osm_key': 'boundary', 'osm_value': 'administrative',
                    'type': 'county', 'country': 'Bangladesh', 'extent': [91, 23, 93, 21]},
                    'geometry': {'type': 'Point', 'coordinates': [92, 22]}}]}

    monkeypatch.setattr(autocomplete, 'request_json', provider)
    for _ in range(2):
        result = asyncio.run(autocomplete.suggest_places('chittagong'))[0]
        assert result['place_id'] == 'osm:relation:3824577'
        assert result['bbox'] == [91, 21, 93, 23]
        assert result['geometry'] is None  # A provider extent is not a boundary.
        assert result['requires_resolution'] is True
    assert len(calls) == 2
    assert all(options['ttl_seconds'] == 0 and not options.get('disk_namespace') for _, options in calls)
    assert calls[0][1]['params']['q'] == 'Chattogram'


def test_search_routes_always_request_fresh_data(monkeypatch):
    calls = []

    async def suggest(query):
        calls.append(('suggest', query))
        return [{'name': f'Live result {len(calls)}'}]

    async def search(query, *, fresh):
        assert fresh is True
        calls.append(('search', query))
        return []

    monkeypatch.setattr(places, 'suggest_places', suggest)
    monkeypatch.setattr(places, 'search_places', search)
    app = FastAPI()
    app.include_router(places.router, prefix='/api')
    with TestClient(app) as client:
        first = client.get('/api/places/search', params={'q': 'chittagong', 'suggest': 'true'})
        second = client.get('/api/places/search', params={'q': 'chittagong', 'suggest': 'true'})
        assert first.json()['results'] != second.json()['results']
        assert first.headers['cache-control'] == second.headers['cache-control'] == 'no-store'
        assert first.json()['source'] == 'live'
        assert client.get('/api/places/search', params={'q': 'Dhaka'}).status_code == 200
    assert calls == [('suggest', 'chittagong'), ('suggest', 'chittagong'), ('search', 'Dhaka')]


def test_selected_boundary_is_fetched_fresh_and_bad_ids_are_rejected(monkeypatch):
    calls = []
    boundary = {'type': 'Polygon', 'coordinates': [[[91, 21], [93, 21], [93, 23], [91, 23], [91, 21]]]}

    async def provider(url, **kwargs):
        calls.append(kwargs)
        return [{'osm_type': 'relation', 'osm_id': 3824577, 'display_name': 'Chattogram District, Bangladesh',
                 'lat': '22', 'lon': '92', 'geojson': boundary}]

    monkeypatch.setattr(autocomplete, 'request_json', provider)
    app = FastAPI()
    app.include_router(places.router, prefix='/api')
    with TestClient(app) as client:
        response = client.get('/api/places/resolve', params={'place_id': 'osm:relation:3824577'})
        assert response.json()['result']['geometry'] == boundary
        assert response.headers['cache-control'] == 'no-store'
        assert client.get('/api/places/resolve', params={'place_id': 'arbitrary-url'}).status_code == 422
    assert calls[0]['params']['osm_ids'] == 'R3824577'
    assert calls[0]['ttl_seconds'] == 0


def test_manual_search_can_bypass_existing_search_cache(monkeypatch):
    options = []

    async def provider(url, **kwargs):
        options.append(kwargs)
        return []

    monkeypatch.setattr(geocode, 'request_json', provider)
    asyncio.run(geocode.search_places('Dhaka', fresh=True))
    assert options[0]['ttl_seconds'] == 0
    assert options[0]['disk_namespace'] is None
