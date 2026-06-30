"""Ollama embedding HTTP client."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.config import (
    EMBED_BASE_URL,
    EMBED_BATCH_SIZE,
    EMBED_INTER_BATCH_SLEEP_SEC,
    EMBED_MAX_ATTEMPTS,
    EMBED_MODEL,
    EMBED_TIMEOUT,
)
from app.ask_trace import log_ask_event
from app.ollama_guard import ollama_guard

logger = logging.getLogger(__name__)

_embed_cache: dict[tuple[str, str], list[float]] = {}

OnBatchComplete = Callable[[int, int], Awaitable[None] | None] | None


async def embed_text(text: str, *, model: str | None = None) -> list[float]:
    m = model or EMBED_MODEL
    key = (m, text)
    if key in _embed_cache:
        return _embed_cache[key]
    t0 = time.perf_counter()
    vec = (await _embed_many_once([text], model=m))[0]
    log_ask_event("embed_query", duration_ms=int((time.perf_counter() - t0) * 1000), dim=len(vec))
    _embed_cache[key] = vec
    return vec


async def embed_batch(
    texts: list[str],
    *,
    model: str | None = None,
    on_batch_complete: OnBatchComplete = None,
) -> list[list[float]]:
    if not texts:
        return []
    m = model or EMBED_MODEL
    batch_size = len(texts) if EMBED_BATCH_SIZE <= 0 else EMBED_BATCH_SIZE
    total_batches = max(1, (len(texts) + batch_size - 1) // batch_size)
    out: list[list[float]] = []

    for batch_num, start in enumerate(range(0, len(texts), batch_size), start=1):
        batch = texts[start : start + batch_size]
        out.extend(await _embed_batch_with_cache(batch, model=m))
        if on_batch_complete is not None:
            maybe = on_batch_complete(batch_num, total_batches)
            if asyncio.iscoroutine(maybe):
                await maybe
        if EMBED_INTER_BATCH_SLEEP_SEC > 0 and batch_num < total_batches:
            await asyncio.sleep(EMBED_INTER_BATCH_SLEEP_SEC)

    log_ask_event("embed_batch", count=len(texts), batches=total_batches)
    return out


async def _embed_batch_with_cache(texts: list[str], *, model: str) -> list[list[float]]:
    results: list[list[float] | None] = [None] * len(texts)
    to_fetch: list[tuple[int, str]] = []
    for i, text in enumerate(texts):
        key = (model, text)
        if key in _embed_cache:
            results[i] = _embed_cache[key]
        else:
            to_fetch.append((i, text))
    if to_fetch:
        fetch_texts = [text for _, text in to_fetch]
        vecs = await _embed_many_once(fetch_texts, model=model)
        for (i, text), vec in zip(to_fetch, vecs, strict=True):
            results[i] = vec
            _embed_cache[(model, text)] = vec
    return [vec for vec in results if vec is not None]


async def _embed_many_once(texts: list[str], *, model: str) -> list[list[float]]:
    if not texts:
        return []
    url = f"{EMBED_BASE_URL.rstrip('/')}/api/embed"
    payload: dict[str, Any] = {"model": model, "input": texts if len(texts) > 1 else texts[0]}
    last_err: Exception | None = None
    for attempt in range(EMBED_MAX_ATTEMPTS):
        try:
            async with ollama_guard.acquire():
                async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
            return _parse_embed_response(data, expected=len(texts))
        except Exception as e:
            last_err = e
            if attempt + 1 < EMBED_MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * (2**attempt))
    raise last_err or RuntimeError("embed failed")


def _parse_embed_response(data: dict[str, Any], *, expected: int) -> list[list[float]]:
    embeddings = data.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        if isinstance(embeddings[0], list):
            return [[float(x) for x in row] for row in embeddings]
        if expected == 1:
            return [[float(x) for x in embeddings]]
    single = data.get("embedding")
    if isinstance(single, list):
        if single and isinstance(single[0], list):
            return [[float(x) for x in row] for row in single]
        return [[float(x) for x in single]]
    raise RuntimeError("Unexpected embed response shape")
