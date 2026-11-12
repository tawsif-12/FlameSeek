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
    photon_calls = [(url, options) for url, options in calls if url == autocomplete.PHOTON_URL]
    assert len(photon_calls) == 2
    assert all(options['ttl_seconds'] == 0 and not options.get('disk_namespace') for _, options in calls)
    assert photon_calls[0][1]['params']['q'] == 'Chattogram'


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


def test_blocked_photon_uses_fresh_live_fallback(monkeypatch):
    calls = []
    async def provider(url, **kwargs):
        calls.append((url, kwargs))
        if url == autocomplete.PHOTON_URL:
            raise autocomplete.ExternalServiceError('Photon', 'HTTP 403', 403)
        return {'results': [{'id': 1185241, 'name': 'Dhaka', 'longitude': 90.40744,
                             'latitude': 23.7104, 'country': 'Bangladesh', 'feature_code': 'PPLC'}]}
    monkeypatch.setattr(autocomplete, 'request_json', provider)
    monkeypatch.setattr(autocomplete, '_photon_retry_after', 0)
    for _ in range(2):
        result = asyncio.run(autocomplete.suggest_places('Dha'))[0]
        assert result['place_id'] == 'geonames:1185241'
        assert result['geometry'] is None
        assert result['requires_resolution'] is True
    assert len([url for url, _ in calls if url == autocomplete.PHOTON_URL]) == 1
    assert len([url for url, _ in calls if url.endswith('/search')]) == 2
    assert all(options['ttl_seconds'] == 0 for _, options in calls)


def test_slow_provider_does_not_delay_live_suggestions(monkeypatch):
    cancelled = []
    async def photon(*args):
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.append(True)
    async def fallback(*args):
        return [{'name': 'Dhaka'}]
    monkeypatch.setattr(autocomplete, '_photon_retry_after', 0)
    monkeypatch.setattr(autocomplete, '_photon_suggestions', photon)
    monkeypatch.setattr(autocomplete, '_geonames_suggestions', fallback)
    async def run():
        return await asyncio.wait_for(autocomplete.suggest_places('Dha'), timeout=0.5)
    assert asyncio.run(run()) == [{'name': 'Dhaka'}]
    assert cancelled == [True]


def test_fallback_selection_resolves_fresh_boundary_and_rejects_distant_names(monkeypatch):
    polygon = {'type': 'Polygon', 'coordinates': [[[90, 23], [91, 23], [91, 24], [90, 23]]]}
    async def provider(url, **kwargs):
        assert url.endswith('/get') and kwargs['params']['id'] == '1185241'
        assert kwargs['ttl_seconds'] == 0
        return {'id': 1185241, 'name': 'Dhaka', 'longitude': 90.4, 'latitude': 23.7, 'country': 'Bangladesh'}
    candidates = [{'name': 'Dhaka, India', 'center': [85, 26], 'geometry': polygon},
                  {'name': 'Dhaka, Bangladesh', 'center': [90.41, 23.71], 'geometry': polygon}]
    async def search(query, *, fresh):
        assert query == 'Dhaka, Bangladesh' and fresh
        return candidates
    monkeypatch.setattr(autocomplete, 'request_json', provider)
    monkeypatch.setattr(autocomplete, 'search_places', search)
    assert asyncio.run(autocomplete.resolve_place('geonames:1185241')) == candidates[1]
    candidates.pop()
    result = asyncio.run(autocomplete.resolve_place('geonames:1185241'))
    assert result['geometry'] is None
