"""Finance MCP client (optional)."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import FINANCE_TOOLS_BASE_URL, FINANCE_TOOLS_TIMEOUT_SECONDS
from app.ask_trace import log_ask_event


def _needs_finance_intent_llm(question: str) -> bool:
    q = (question or "").lower()
    patterns = (
        r"\bstock\b",
        r"\bticker\b",
        r"\bcompound interest\b",
        r"\bapy calculator\b",
        r"\$[a-z]{1,5}\b",
        r"\bquote\b",
    )
    return any(re.search(p, q) for p in patterns)


def _parse_finance_intent_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


async def fetch_finance_tools_block(question: str, *, skip_llm: bool = False) -> str:
    if not FINANCE_TOOLS_BASE_URL:
        return ""
    if skip_llm or not _needs_finance_intent_llm(question):
        log_ask_event("finance_tools", skipped=True, reason="heuristic")
        return ""
    # LLM intent path intentionally skipped for CPU savings; enable later if needed.
    log_ask_event("finance_tools", skipped=True, reason="disabled_for_cpu")
    return ""


async def call_finance_tool(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{FINANCE_TOOLS_BASE_URL.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=FINANCE_TOOLS_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"result": data}
