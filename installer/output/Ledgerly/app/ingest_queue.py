"""In-memory ingest job queue."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.ingest_jobs import IngestJob, IngestJobStatus


class IngestJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, IngestJob] = {}
        self._lock = asyncio.Lock()

    async def add(self, job: IngestJob) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def get(self, job_id: str) -> IngestJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_ids(self, ids: list[str]) -> list[IngestJob]:
        async with self._lock:
            return [self._jobs[i] for i in ids if i in self._jobs]

    async def list_recent(self, limit: int = 50) -> list[IngestJob]:
        async with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.id, reverse=True)
        return jobs[:limit]

    async def update(self, job: IngestJob) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def pop_next_pending(self) -> IngestJob | None:
        async with self._lock:
            for job in self._jobs.values():
                if job.status == IngestJobStatus.PENDING:
                    job.status = IngestJobStatus.RUNNING
                    job.stage = "starting"
                    return job
        return None

    async def has_running_job(self) -> bool:
        async with self._lock:
            return any(j.status == IngestJobStatus.RUNNING for j in self._jobs.values())
