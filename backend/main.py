from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import APP_NAME, APP_VERSION, FRONTEND_ORIGINS
from routers.analysis import router as analysis_router
from routers.fire_events import list_events
from routers.fire_events import router as events_router
from routers.memory import router as memory_router
from routers.places import router as places_router
from routers.sources import router as sources_router


async def _warm_event_set() -> None:
    """Reconstruct the recent world event set once at startup so the globe's first load is fast."""
    try:
        await list_events(bbox=None, days=2, limit=1, min_detections=1)
        print("event set warmed")
    except Exception as exc:  # noqa: BLE001 - warm-up is best effort
        print(f"event warm-up skipped: {exc}")


async def _warm_current_hotspots() -> None:
    """Prime the FIRMS CSV cache for the default globe request so the first UI load is instant."""
    from firms_client import fetch_recent_hotspots
    from config import DEFAULT_SENSORS
    try:
        await fetch_recent_hotspots(bbox=None, sensors=DEFAULT_SENSORS, days=1)
        print("current hotspots warmed")
    except Exception as exc:  # noqa: BLE001 - warm-up is best effort
        print(f"current hotspots warm-up skipped: {exc}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    tasks = [
        asyncio.create_task(_warm_current_hotspots()),
        asyncio.create_task(_warm_event_set()),
    ]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="Burning_Activity API", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router, prefix="/api", tags=["analysis"])
app.include_router(memory_router, prefix="/api", tags=["fire memory"])
app.include_router(events_router, prefix="/api", tags=["fire events"])
app.include_router(places_router, prefix="/api", tags=["places and jobs"])
app.include_router(sources_router, tags=["sources"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": APP_NAME, "message": "Burning_Activity API", "version": APP_VERSION}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME}
