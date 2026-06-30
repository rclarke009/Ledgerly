"""Optional cross-encoder reranker (disabled by default)."""

from __future__ import annotations

from app.models import RetrievedChunk


async def rerank(
    _query_vec: list[float],
    chunks: list[RetrievedChunk],
    top_k: int,
) -> list[RetrievedChunk]:
    return chunks[:top_k]
