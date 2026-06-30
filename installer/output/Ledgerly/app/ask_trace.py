"""Ask pipeline trace context and structured logging."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from app.config import LOG_JSON

logger = logging.getLogger(__name__)

_trace_ctx: ContextVar["AskTraceContext | None"] = ContextVar("ask_trace_ctx", default=None)


@dataclass(frozen=True)
class AskTraceContext:
    request_id: str
    http_route: str
    question_preview: str


class ask_trace_scope:
    def __init__(self, ctx: AskTraceContext) -> None:
        self._ctx = ctx
        self._token: Any = None

    def __enter__(self) -> AskTraceContext:
        self._token = _trace_ctx.set(self._ctx)
        return self._ctx

    def __exit__(self, *args: Any) -> None:
        if self._token is not None:
            _trace_ctx.reset(self._token)


def log_ask_event(stage: str, **fields: Any) -> None:
    ctx = _trace_ctx.get()
    if ctx is None:
        return
    payload = {
        "stage": stage,
        "request_id": ctx.request_id,
        "http_route": ctx.http_route,
        "question_preview": ctx.question_preview,
        **fields,
    }
    if LOG_JSON:
        logger.info(json.dumps({"ask_trace": payload}, default=str))
    else:
        logger.info("ask_trace %s", json.dumps(payload, default=str))
