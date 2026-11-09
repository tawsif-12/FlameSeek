import asyncio
import geocode


def test_names_boundary_identity_and_point_only_result(monkeypatch):
    requests = []
    async def response(url, **kwargs):
        requests.append(kwargs)
        return [dict(display_name='Noakhali Road, Bangladesh', lon='90', lat='24', type='road', namedetails={'name':'Noakhali Road'}),
                dict(display_name='Noakhali, Chattogram, Bangladesh', lon='90', lat='24', osm_type='relation', osm_id=3824792,
                     namedetails={'name:en':'Noakhali','name:bn':'নোয়াখালী'}, address={'state':'Chattogram','country':'Bangladesh'},
                     geojson={'type':'Polygon','coordinates':[[[89,23],[91,23],[91,25],[89,25],[89,23]]]})]
    monkeypatch.setattr(geocode,'request_json',response)
    for query in ('Noakhali','নোয়াখালী'):
        rows=asyncio.run(geocode.search_places(query))
        assert rows[0]['place_id']=='osm:relation:3824792'
        assert rows[0]['geometry']['type']=='Polygon'
        assert rows[0]['parent_region']=='Chattogram, Bangladesh'
        assert rows[1]['geometry'] is None
    assert requests[0]['params']['namedetails']==1
    assert requests[0]['disk_namespace']=='nominatim'


def test_equivalent_queries_share_provider_cache_key(monkeypatch):
    queries = []
    async def response(url, **kwargs):
        queries.append(kwargs['params']['q'])
        return []
    monkeypatch.setattr(geocode, 'request_json', response)
    for query in ('Bangladesh', 'bangladesh', '  BANGLADESH  ', 'Ｂａｎｇｌａｄｅｓｈ'):
        assert asyncio.run(geocode.search_places(query)) == []
    assert queries == ['bangladesh'] * 4
