"""Compress large search and live-globe JSON responses."""
from starlette.middleware.gzip import GZipMiddleware


class SearchGZipMiddleware:
    def __init__(self,app):
        self.app=app
        self.compressed=GZipMiddleware(app,minimum_size=1000,compresslevel=5)

    async def __call__(self,scope,receive,send):
        path = scope.get('path', '')
        compress = path in {'/fires/search', '/api/harmonized_hotspots', '/api/fire_memory', '/api/fire_memory/saved', '/api/place_pipeline', '/api/place_pipeline/saved'} or path.startswith('/api/jobs/')
        app = self.compressed if scope['type'] == 'http' and compress else self.app
        await app(scope,receive,send)
