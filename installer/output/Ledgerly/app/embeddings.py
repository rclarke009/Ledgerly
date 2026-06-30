"""Embedding wrapper used by ingest."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.config import EMBED_DIM, EMBED_MODEL
from app import embeddings_client

OnEmbedBatchComplete = Callable[[int, int], Awaitable[None] | None] | None


class HttpEmbedder:
    def __init__(self, model: str | None = None, dim: int | None = None) -> None:
        self.model = model or EMBED_MODEL
        self.dim = dim if dim is not None else EMBED_DIM

    async def embed_many(
        self,
        texts: list[str],
        *,
        on_embed_batch_complete: OnEmbedBatchComplete = None,
    ) -> list[list[float]]:
        return await embeddings_client.embed_batch(
            texts,
            model=self.model,
            on_batch_complete=on_embed_batch_complete,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self.embed_many(texts)
