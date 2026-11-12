from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from geocode import reverse_geocode, search_places
from http_utils import ExternalServiceError
from jobs import get_job
from place_query import location_query
from place_autocomplete import suggest_places, resolve_place


router = APIRouter()


@router.get("/places/search")
async def places_search(response: Response, q: str = Query(min_length=2, max_length=120), suggest: bool = False) -> dict[str, Any]:
    """Country, state, district, forest or protected-area search for AOI selection."""
    response.headers["Cache-Control"] = "no-store"
    try:
        location = location_query(q)
        if len(location) < 2:
            return {"results": []}
        results = await suggest_places(location) if suggest else await search_places(location, fresh=True)
        return {"results": results, "location_query": location, "source": "live"}
    except ExternalServiceError as exc:
        raise HTTPException(status_code=502, detail={"error": "geocoder_unavailable", "message": "Location search is temporarily unavailable. Retry search or select an area on the map."}) from exc


@router.get('/places/resolve')
async def places_resolve(response: Response, place_id: str = Query(pattern=r'^(osm:(node|way|relation):[1-9][0-9]*|geonames:[1-9][0-9]*)$')):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return {'result': await resolve_place(place_id)}
    except ExternalServiceError as exc:
        raise HTTPException(status_code=502, detail={'error': 'boundary_unavailable', 'message': 'Could not load this place boundary. Retry or select an area on the map.'}) from exc


@router.get("/places/reverse")
async def places_reverse(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)) -> dict[str, Any]:
    return await reverse_geocode(lat, lon)


@router.get("/jobs/{job_id}")
async def job_status(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "job_not_found", "message": "Unknown or expired job (jobs are kept in memory until the server restarts)."})
    return job.to_dict()
