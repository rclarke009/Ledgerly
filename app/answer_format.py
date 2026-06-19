"""Answer markdown layout and structured JSON tail parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field


class AnswerTable(BaseModel):
    title: str | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class AnswerChart(BaseModel):
    title: str | None = None
    chart_type: str = "bar"
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)

LEDGERLY_STRUCTURED_MARKER = "\n---LEDGERLY_STRUCTURED---\n"
_STRUCTURED_MARKER_LINE = re.compile(
    r"^\s*(?:---\s*)?LEDGERLY_STRUCTURED(?:\s*---)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_LOOSE_TAIL_ARRAY = re.compile(
    r"(tables|charts)\s*:\s*(\[[\s\S]*?\])",
    re.IGNORECASE,
)
ANSWER_FORMAT_PROMPT_SUFFIX = (
    "\n\nAfter your answer, on its own line, output exactly:\n"
    "---LEDGERLY_STRUCTURED---\n"
    'Then optional JSON with keys tables (array) and charts (array), e.g. {"tables":[],"charts":[]}. '
    "Omit the marker if you have no structured data."
)


def _trim_trailing_hr_before_marker(body: str) -> str:
    return re.sub(r"\n---\s*$", "", body.rstrip()).rstrip()


def _find_structured_marker_start(text: str) -> int | None:
    matches = list(_STRUCTURED_MARKER_LINE.finditer(text))
    if not matches:
        return None
    return matches[-1].start()


def _parse_structured_tail(tail_raw: str) -> dict[str, Any] | None:
    tail_raw = tail_raw.strip()
    if not tail_raw:
        return None
    try:
        tail = json.loads(tail_raw)
        if isinstance(tail, dict):
            return tail
    except json.JSONDecodeError:
        pass
    loose: dict[str, Any] = {}
    for key, raw_array in _LOOSE_TAIL_ARRAY.findall(tail_raw):
        try:
            loose[key.lower()] = json.loads(raw_array)
        except json.JSONDecodeError:
            continue
    return loose or None


def split_structured(raw: str) -> tuple[str, dict[str, Any] | None]:
    if not raw:
        return "", None
    text = raw.replace("\r\n", "\n")
    idx = text.rfind(LEDGERLY_STRUCTURED_MARKER)
    if idx != -1:
        body = _trim_trailing_hr_before_marker(text[:idx].strip())
        tail_raw = text[idx + len(LEDGERLY_STRUCTURED_MARKER) :].strip()
        return body, _parse_structured_tail(tail_raw)

    marker_start = _find_structured_marker_start(text)
    if marker_start is None:
        return raw.strip(), None

    body = _trim_trailing_hr_before_marker(text[:marker_start].strip())
    marker_line_end = text.find("\n", marker_start)
    if marker_line_end == -1:
        return body, None
    tail_raw = text[marker_line_end + 1 :].strip()
    return body, _parse_structured_tail(tail_raw)


def merge_structured_to_response(
    body: str,
    tail: dict[str, Any] | None,
) -> tuple[str, list[AnswerTable], list[AnswerChart]]:
    tables: list[AnswerTable] = []
    charts: list[AnswerChart] = []
    if tail:
        for t in tail.get("tables") or []:
            if isinstance(t, dict):
                try:
                    tables.append(AnswerTable.model_validate(t))
                except Exception:
                    pass
        for c in tail.get("charts") or []:
            if isinstance(c, dict):
                try:
                    charts.append(AnswerChart.model_validate(c))
                except Exception:
                    pass
    return body, tables, charts


def normalize_markdown_layout(md: str) -> str:
    if not md or not md.strip():
        return md or ""
    text = md.replace("\r\n", "\n")
    text = re.sub(r"(?<!\n)\s+(#{2,6}\s+)", r"\n\n\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
