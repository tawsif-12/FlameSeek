"""Compress large search and live-globe JSON responses."""
from starlette.middleware.gzip import GZipMiddleware


class SearchGZipMiddleware:
    def __init__(self,app):
        self.app=app
        self.compressed=GZipMiddleware(app,minimum_size=1000,compresslevel=5)

    async def __call__(self,scope,receive,send):
        app=self.compressed if scope['type']=='http' and scope.get('path') in {'/fires/search', '/api/harmonized_hotspots'} else self.app
        await app(scope,receive,send)
