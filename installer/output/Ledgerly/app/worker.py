"""Generic worker loop stub."""

from __future__ import annotations

import asyncio
from typing import Any

from app.job_store import JobStore
from app.rate_limit import TokenBucket


async def worker_loop(job_store: JobStore, rate_limiter: TokenBucket) -> None:
    while True:
        try:
            job = await job_store.pop_pending()
            if job is None:
                await asyncio.sleep(1.0)
                continue
            job.status = __import__("app.job_store", fromlist=["JobStatus"]).JobStatus.DONE
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(1.0)
