"""In-memory ask job queue."""

from __future__ import annotations

import asyncio

from app.ask_jobs import AskJob, AskJobStatus


class AskJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, AskJob] = {}
        self._lock = asyncio.Lock()

    async def add(self, job: AskJob) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def get(self, job_id: str) -> AskJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_recent(self, limit: int = 50) -> list[AskJob]:
        async with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    async def update(self, job: AskJob) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def pop_next_pending(self) -> AskJob | None:
        async with self._lock:
            pending = [j for j in self._jobs.values() if j.status == AskJobStatus.PENDING]
            pending.sort(key=lambda j: j.created_at)
            if not pending:
                return None
            job = pending[0]
            job.status = AskJobStatus.RUNNING
            job.stage = "routing"
            job.progress_pct = 5.0
            return job

    async def pending_count(self) -> int:
        async with self._lock:
            return sum(1 for j in self._jobs.values() if j.status == AskJobStatus.PENDING)
