"""Background Ollama model warmup for Ask and Ingest tabs."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Literal

import httpx

from app.config import (
    EMBED_BASE_URL,
    EMBED_MODEL,
    EMBED_TIMEOUT,
    LLAVA_MODEL,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    OLLAMA_WARMUP_ENABLED,
    OLLAMA_WARMUP_KEEP_ALIVE,
    OLLAMA_WARMUP_SESSION_SEC,
)
from app.ollama_guard import ollama_guard

logger = logging.getLogger(__name__)

Profile = Literal["ask", "ingest"]
WarmupState = Literal["idle", "running", "ready"]


@dataclass
class _ProfileState:
    status: WarmupState = "idle"
    ready_at: float | None = None


_states: dict[str, _ProfileState] = {
    "ask": _ProfileState(),
    "ingest": _ProfileState(),
}
_embed_ready_at: float | None = None
_lock = asyncio.Lock()


def _within_session(ready_at: float | None) -> bool:
    if ready_at is None:
        return False
    return (time.time() - ready_at) < OLLAMA_WARMUP_SESSION_SEC


def _embed_fresh() -> bool:
    return _within_session(_embed_ready_at)


async def _warm_embed() -> None:
    global _embed_ready_at
    url = f"{EMBED_BASE_URL.rstrip('/')}/api/embed"
    payload = {
        "model": EMBED_MODEL,
        "input": "warmup",
        "keep_alive": OLLAMA_WARMUP_KEEP_ALIVE,
    }
    async with ollama_guard.acquire():
        async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
    _embed_ready_at = time.time()


async def _warm_chat(model: str) -> None:
    url = f"{LLM_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "options": {"num_predict": 1},
        "keep_alive": OLLAMA_WARMUP_KEEP_ALIVE,
    }
    async with ollama_guard.acquire():
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()


async def _run_ask_warmup() -> None:
    state = _states["ask"]
    try:
        if not _embed_fresh():
            await _warm_embed()
        await _warm_chat(LLM_MODEL)
        state.status = "ready"
        state.ready_at = time.time()
    except Exception as e:
        logger.warning("Ask warmup failed: %s", e)
        state.status = "idle"
        state.ready_at = None


async def _run_ingest_warmup() -> None:
    state = _states["ingest"]
    try:
        if not _embed_fresh():
            await _warm_embed()
        await _warm_chat(LLAVA_MODEL)
        state.status = "ready"
        state.ready_at = time.time()
    except Exception as e:
        logger.warning("Ingest warmup failed: %s", e)
        state.status = "idle"
        state.ready_at = None


async def _warmup_task(profile: Profile) -> None:
    if profile == "ask":
        await _run_ask_warmup()
    else:
        await _run_ingest_warmup()


async def request_warmup(profile: Profile) -> dict:
    if not OLLAMA_WARMUP_ENABLED:
        return {"status": "skipped", "profile": profile}
    async with _lock:
        state = _states[profile]
        if state.status == "ready" and _within_session(state.ready_at):
            return {"status": "ready", "profile": profile}
        if state.status == "running":
            return {"status": "warming", "profile": profile}
        state.status = "running"
        asyncio.create_task(_warmup_task(profile))
        return {"status": "started", "profile": profile}


def get_warmup_status() -> dict:
    def _ready_until(st: _ProfileState) -> int | None:
        if st.status != "ready" or st.ready_at is None:
            return None
        return int(st.ready_at + OLLAMA_WARMUP_SESSION_SEC)

    return {
        "ask": _states["ask"].status,
        "ingest": _states["ingest"].status,
        "ready_until": {
            "ask": _ready_until(_states["ask"]),
            "ingest": _ready_until(_states["ingest"]),
        },
    }


def reset_warmup_state() -> None:
    """Clear in-process warmup state (tests)."""
    global _embed_ready_at
    _embed_ready_at = None
    for st in _states.values():
        st.status = "idle"
        st.ready_at = None
