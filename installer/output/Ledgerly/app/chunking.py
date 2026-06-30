"""Text chunking for ingest."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    content: str
    start_offset: int
    end_offset: int


def chunk_text_chars(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[TextChunk]:
    if not text:
        return []
    if chunk_size <= 0:
        chunk_size = 800
    if chunk_overlap < 0:
        chunk_overlap = 0
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size - 1)
    step = max(1, chunk_size - chunk_overlap)
    chunks: list[TextChunk] = []
    i = 0
    idx = 0
    while i < len(text):
        end = min(i + chunk_size, len(text))
        chunks.append(
            TextChunk(
                chunk_index=idx,
                content=text[i:end],
                start_offset=i,
                end_offset=end,
            )
        )
        if end >= len(text):
            break
        i += step
        idx += 1
    return chunks
