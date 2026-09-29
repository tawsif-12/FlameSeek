"""In-process background jobs with progress, for analyses that take minutes on a cold cache."""

from __future__ import annotations

import asyncio
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


from firms_client import FIRMS_WAIT_SECONDS


JobFn = Callable[["Job"], Awaitable[Any]]
_JOBS: dict[str, "Job"] = {}
MAX_JOBS = 200
JOB_FIRMS_WAIT = {"fire_memory": 900.0, "outlook": 900.0, "evidence": 30.0}


class Job:
    def __init__(self, kind: str, params: dict[str, Any]):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.params = params
        self.status = "queued"
        self.progress = 0.0
        self.message = "Queued"
        self.result: Any = None
        self.error: str | None = None
        self.created_at = datetime.now(timezone.utc)
        self.finished_at: datetime | None = None

    async def update(self, message: str, progress: float | None = None) -> None:
        self.message = message
        if progress is not None:
            self.progress = max(self.progress, min(1.0, progress))

    def to_dict(self, include_result: bool = True) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 3),
            "message": self.message,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result": self.result if include_result and self.status == "completed" else None,
        }


def start_job(kind: str, params: dict[str, Any], fn: JobFn) -> Job:
    job = Job(kind, params)
    if len(_JOBS) >= MAX_JOBS:
        for old in sorted(_JOBS.values(), key=lambda j: j.created_at)[: len(_JOBS) - MAX_JOBS + 1]:
            _JOBS.pop(old.id, None)
    _JOBS[job.id] = job

    async def runner() -> None:
        # Long analyses may wait for the FIRMS transaction window instead of losing data.
        FIRMS_WAIT_SECONDS.set(JOB_FIRMS_WAIT.get(kind, 30.0))
        job.status = "running"
        try:
            job.result = await fn(job)
            job.status = "completed"
            job.progress = 1.0
            job.message = "Completed"
        except Exception as exc:  # noqa: BLE001 - surface any failure to the client
            job.status = "failed"
            job.error = f"{exc.__class__.__name__}: {exc}"
            print(traceback.format_exc())
        finally:
            job.finished_at = datetime.now(timezone.utc)

    asyncio.get_running_loop().create_task(runner())
    return job


def get_job(job_id: str) -> Job | None:
    return _JOBS.get(job_id)
