"""Structured API error envelopes."""

from __future__ import annotations

from typing import Any


def http_error_code(status_code: int) -> str:
    if status_code == 400:
        return "bad_request"
    if status_code == 404:
        return "not_found"
    if status_code == 409:
        return "conflict"
    if status_code == 429:
        return "rate_limit"
    if status_code == 503:
        return "service_unavailable"
    return "http_error"


def error_envelope(
    detail: str | dict[str, Any],
    code: str,
    *,
    request: Any = None,
) -> dict[str, Any]:
    msg = detail if isinstance(detail, str) else str(detail)
    out: dict[str, Any] = {"error": msg, "code": code}
    if request is not None:
        rid = getattr(getattr(request, "state", None), "request_id", None)
        if rid:
            out["request_id"] = rid
    return out
