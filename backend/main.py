from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import APP_NAME, APP_VERSION, FRONTEND_ORIGINS
from routers.analysis import router as analysis_router
from routers.memory import router as memory_router
from routers.places import router as places_router
from routers.sources import router as sources_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="FlameSeek API", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router, prefix="/api", tags=["analysis"])
app.include_router(memory_router, prefix="/api", tags=["fire memory"])
app.include_router(places_router, prefix="/api", tags=["places and jobs"])
app.include_router(sources_router, tags=["sources"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": APP_NAME, "message": "FlameSeek API", "version": APP_VERSION}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME}
