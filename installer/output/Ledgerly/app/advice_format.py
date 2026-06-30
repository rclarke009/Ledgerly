"""Split OpenAI advice bullets."""

from __future__ import annotations

import re


def split_advice_bullets(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if len(lines) <= 1:
        parts = re.split(r"(?<=\.)\s+(?=\d+\.)", text.strip())
        return [p.strip() for p in parts if p.strip()]
    return lines
