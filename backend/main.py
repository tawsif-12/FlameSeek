from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import APP_NAME, FRONTEND_ORIGINS
from routers.analysis import router as analysis_router
from routers.sources import router as sources_router


app = FastAPI(title="Burning Activity Calendar API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router, prefix="/api", tags=["analysis"])
app.include_router(sources_router, tags=["sources"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": APP_NAME, "message": "Burning Activity Calendar API"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME}

