"""Serve the built SPA and the existing API under one Render origin."""
from pathlib import Path
import sys
from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
# The API's forecast.py and the offline forecast/ package have the same name.
# API imports must resolve exactly as they do when started from backend/.
sys.path.insert(0, str(ROOT / 'backend'))
from main import app as api

API_PATHS = ('/api', '/meta', '/fires', '/events', '/detections', '/grid', '/health')


class SPA(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or Path(path).suffix:
                raise
            return await super().get_response('index.html', scope)


static = SPA(directory=ROOT / 'frontend/dist', html=True)


async def app(scope, receive, send):
    path = scope.get('path', '')
    is_api = any(path == prefix or path.startswith(prefix + '/') for prefix in API_PATHS)
    if scope['type'] != 'http' or is_api:
        await api(scope, receive, send)
    else:
        try:
            await static(scope, receive, send)
        except HTTPException as exc:
            await PlainTextResponse(str(exc.detail), status_code=exc.status_code)(scope, receive, send)
