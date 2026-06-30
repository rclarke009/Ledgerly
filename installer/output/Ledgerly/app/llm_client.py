"""Ollama and OpenAI LLM clients."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

import httpx

from app.config import (
    LLAVA_MODEL,
    LLM_BASE_URL,
    LLM_MAX_ATTEMPTS,
    LLM_MODEL,
    LLM_STREAM_TIMEOUT_SECONDS,
    LLM_TIMEOUT_SECONDS,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MAX_ATTEMPTS,
    OPENAI_MODEL,
    OPENAI_TIMEOUT_SECONDS,
)
from app.ask_trace import log_ask_event
from app.errors import LLMServiceError, LLMUpstreamTimeoutError
from app.ollama_guard import ollama_guard

logger = logging.getLogger(__name__)


async def answer_with_context(prompt: str) -> str:
    return await answer_with_messages([{"role": "user", "content": prompt}])


async def answer_with_context_stream(prompt: str) -> AsyncIterator[str]:
    async for delta in answer_with_messages_stream([{"role": "user", "content": prompt}]):
        yield delta


async def answer_with_messages(messages: list[dict[str, str]]) -> str:
    t0 = time.perf_counter()
    text = await _chat_messages_once(messages, stream=False)
    log_ask_event(
        "llm_completion",
        kind="chat",
        duration_ms=int((time.perf_counter() - t0) * 1000),
        response_chars=len(text or ""),
    )
    return text


async def answer_with_messages_stream(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    t0 = time.perf_counter()
    total_chars = 0
    async for delta in _chat_messages_stream(messages):
        total_chars += len(delta)
        yield delta
    log_ask_event(
        "llm_completion",
        kind="stream",
        duration_ms=int((time.perf_counter() - t0) * 1000),
        response_chars=total_chars,
    )


async def answer_with_image(image_base64: str, prompt: str) -> str:
    url = f"{LLM_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": LLAVA_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_base64],
            }
        ],
        "stream": False,
    }
    async with ollama_guard.acquire():
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    return _message_content(data)


FINANCIAL_IMAGE_OCR_PROMPT = """Extract all readable text from this financial document image. Return plain text only.

Prioritize payment summaries, amount due, principal and interest, escrow, fees, total amount due, payment due date, loan number, borrower, property address, and outstanding balance.

Preserve dollar amounts exactly as shown (e.g. $2,247.00). Preserve dates exactly as shown.

Do not describe the image, comment on blur, or add markdown code fences. If text is unclear, transcribe your best reading without apologizing."""


async def image_to_text_for_ingest(image_base64: str, *, filename_hint: str | None = None) -> str:
    prompt = FINANCIAL_IMAGE_OCR_PROMPT
    if filename_hint and filename_hint.strip():
        prompt += f"\n\nUploaded filename hint: {filename_hint.strip()}"
    return await answer_with_image(image_base64, prompt)


async def answer_openai(prompt: str) -> str | None:
    if not OPENAI_API_KEY:
        return None
    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }
    last_err: Exception | None = None
    for attempt in range(OPENAI_MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=OPENAI_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            choices = data.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                return (msg.get("content") or "").strip()
            return ""
        except Exception as e:
            last_err = e
            if attempt + 1 < OPENAI_MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * (2**attempt))
    logger.warning("OpenAI call failed: %s", last_err)
    return None


async def _chat_messages_once(messages: list[dict[str, str]], *, stream: bool) -> str:
    url = f"{LLM_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "stream": stream,
    }
    last_err: Exception | None = None
    for attempt in range(LLM_MAX_ATTEMPTS):
        try:
            async with ollama_guard.acquire():
                async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
            return _message_content(data)
        except httpx.TimeoutException as e:
            last_err = LLMUpstreamTimeoutError(str(e))
            if attempt + 1 < LLM_MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * (2**attempt))
        except httpx.HTTPStatusError as e:
            raise LLMServiceError(str(e)) from e
        except Exception as e:
            last_err = e
            if attempt + 1 < LLM_MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * (2**attempt))
    raise last_err or LLMServiceError("LLM chat failed")


async def _chat_messages_stream(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    url = f"{LLM_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "stream": True,
    }
    last_err: Exception | None = None
    for attempt in range(LLM_MAX_ATTEMPTS):
        try:
            async with ollama_guard.acquire():
                async with httpx.AsyncClient(timeout=LLM_STREAM_TIMEOUT_SECONDS) as client:
                    async with client.stream("POST", url, json=payload) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            msg = data.get("message") or {}
                            delta = msg.get("content") or ""
                            if delta:
                                yield delta
                            if data.get("done"):
                                return
            return
        except httpx.TimeoutException as e:
            last_err = LLMUpstreamTimeoutError(str(e))
            if attempt + 1 < LLM_MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * (2**attempt))
        except httpx.HTTPStatusError as e:
            raise LLMServiceError(str(e)) from e
        except Exception as e:
            last_err = e
            if attempt + 1 < LLM_MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * (2**attempt))
    raise last_err or LLMServiceError("LLM stream failed")


async def _chat_once(prompt: str, *, stream: bool) -> str:
    return await _chat_messages_once([{"role": "user", "content": prompt}], stream=stream)


async def _chat_stream(prompt: str) -> AsyncIterator[str]:
    async for delta in _chat_messages_stream([{"role": "user", "content": prompt}]):
        yield delta


def _message_content(data: dict) -> str:
    msg = data.get("message") or {}
    return (msg.get("content") or "").strip()
