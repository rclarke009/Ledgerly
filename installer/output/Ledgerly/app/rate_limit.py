"""Token-bucket rate limiter for LLM calls."""

from __future__ import annotations

import asyncio
import time

from app.config import LLM_RATE_LIMIT_SECONDS, LLM_TOKEN_LIMIT
from app.errors import LLMRateLimitedError


class TokenBucket:
    def __init__(
        self,
        *,
        limit: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        self._limit = limit if limit is not None else LLM_TOKEN_LIMIT
        self._window = window_seconds if window_seconds is not None else LLM_RATE_LIMIT_SECONDS
        self._tokens = self._limit
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed >= self._window:
            self._tokens = self._limit
            self._last_refill = now

    async def acquire(self) -> None:
        async with self._lock:
            self._refill()
            if self._tokens <= 0:
                raise LLMRateLimitedError(
                    f"Rate limit: max {self._limit} LLM calls per {self._window}s"
                )
            self._tokens -= 1
