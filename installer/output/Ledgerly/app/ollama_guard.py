"""Global semaphore limiting concurrent Ollama HTTP work."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.config import OLLAMA_MAX_CONCURRENT


class OllamaGuard:
    def __init__(self, max_concurrent: int) -> None:
        self._sem = asyncio.Semaphore(max(1, max_concurrent))

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        await self._sem.acquire()
        try:
            yield
        finally:
            self._sem.release()


ollama_guard = OllamaGuard(OLLAMA_MAX_CONCURRENT)
