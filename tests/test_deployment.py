"""Production routing must preserve API errors and SPA deep links."""
import importlib.util
from pathlib import Path
import sys
import types

from fastapi import FastAPI
from starlette.testclient import TestClient


def test_combined_app_routes_api_and_static(monkeypatch, tmp_path):
    api = FastAPI()

    @api.get('/health')
    def health():
        return {'status': 'ok'}

    fake_main = types.ModuleType('main')
    fake_main.app = api
    monkeypatch.setitem(sys.modules, 'main', fake_main)
    path = Path(__file__).resolve().parents[1] / 'deploy/web.py'
    spec = importlib.util.spec_from_file_location('deployment_web_test', path)
    web = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(web)
    (tmp_path / 'index.html').write_text('<html>FlameSeek</html>')
    (tmp_path / 'worker.js').write_text('self.onmessage = () => {};')
    web.static = web.SPA(directory=tmp_path, html=True)
    client = TestClient(web.app)
    assert client.get('/health').json() == {'status': 'ok'}
    assert client.get('/fire-map').text == '<html>FlameSeek</html>'
    assert client.get('/data-sources').headers['content-type'].startswith('text/html')
    assert client.get('/worker.js').status_code == 200
    assert client.get('/missing.js').status_code == 404
    for url in ('/api/missing', '/fires/missing', '/grid/lambda', '/events/missing'):
        response = client.get(url)
        assert response.status_code == 404
        assert response.headers['content-type'].startswith('application/json')
