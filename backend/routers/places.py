from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from geocode import reverse_geocode, search_places
from http_utils import ExternalServiceError
from jobs import get_job


router = APIRouter()


@router.get("/places/search")
async def places_search(q: str = Query(min_length=2, max_length=120)) -> dict[str, Any]:
    """Country, state, district, forest or protected-area search for AOI selection."""
    try:
        return {"results": await search_places(q)}
    except ExternalServiceError as exc:
        raise HTTPException(status_code=502, detail={"error": "geocoder_unavailable", "message": str(exc)}) from exc


@router.get("/places/reverse")
async def places_reverse(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)) -> dict[str, Any]:
    return await reverse_geocode(lat, lon)


@router.get("/jobs/{job_id}")
async def job_status(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "job_not_found", "message": "Unknown or expired job (jobs are kept in memory until the server restarts)."})
    return job.to_dict()
