import json
import place_suggestions as suggestions


def test_prefix_and_misspelling_keep_saved_boundary(tmp_path, monkeypatch):
    boundary = {'type': 'Polygon', 'coordinates': [[[88, 21], [90, 21], [90, 23], [88, 23], [88, 21]]]}
    folder = tmp_path / 'nominatim'
    folder.mkdir()
    (folder / 'place.txt').write_text(json.dumps([{
        'osm_type': 'relation', 'osm_id': 123, 'name': 'Sundarbans',
        'display_name': 'Sundarbans, Bangladesh', 'lat': '22', 'lon': '89',
        'geojson': boundary,
    }]))
    monkeypatch.setattr(suggestions, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(suggestions, '_loaded_at', 0)
    monkeypatch.setattr(suggestions, '_records', [])
    for query in ('sun', 'shundarban', 'Sundarbans'):
        found = suggestions.cached_places(query)
        assert found[0]['place_name'] == 'Sundarbans'
        assert found[0]['geometry'] == boundary
    assert suggestions.cached_places('unrelated place') == []
