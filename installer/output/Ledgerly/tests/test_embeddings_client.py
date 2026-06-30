"""Tests for batched Ollama embedding client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app import embeddings_client


class _FakeGuard:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_embed_batch_uses_single_multi_input_request(monkeypatch):
    monkeypatch.setattr(embeddings_client, "EMBED_BATCH_SIZE", 32)
    calls: list[dict] = []

    async def fake_post(self, url, **kwargs):
        json_payload = kwargs.get("json") or {}
        calls.append(json_payload)
        dim = 4
        inputs = json_payload["input"]
        if isinstance(inputs, str):
            inputs = [inputs]
        return type(
            "Resp",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"embeddings": [[0.1] * dim for _ in inputs]},
            },
        )()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        post = fake_post

    monkeypatch.setattr(embeddings_client.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(embeddings_client.ollama_guard, "acquire", lambda: _FakeGuard())

    texts = ["one", "two", "three"]
    vecs = await embeddings_client.embed_batch(texts, model="test-model")
    assert len(vecs) == 3
    assert len(calls) == 1
    assert calls[0]["input"] == texts


@pytest.mark.asyncio
async def test_embed_batch_splits_by_embed_batch_size(monkeypatch):
    monkeypatch.setattr(embeddings_client, "EMBED_BATCH_SIZE", 2)
    batch_sizes: list[int] = []

    async def fake_post(self, url, **kwargs):
        json_payload = kwargs.get("json") or {}
        inputs = json_payload["input"]
        if isinstance(inputs, str):
            inputs = [inputs]
        batch_sizes.append(len(inputs))
        dim = 3
        return type(
            "Resp",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"embeddings": [[0.0] * dim for _ in inputs]},
            },
        )()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        post = fake_post

    monkeypatch.setattr(embeddings_client.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(embeddings_client.ollama_guard, "acquire", lambda: _FakeGuard())

    vecs = await embeddings_client.embed_batch(["a", "b", "c", "d", "e"], model="m")
    assert len(vecs) == 5
    assert batch_sizes == [2, 2, 1]


@pytest.mark.asyncio
async def test_embed_batch_progress_callback(monkeypatch):
    monkeypatch.setattr(embeddings_client, "EMBED_BATCH_SIZE", 2)
    progress: list[tuple[int, int]] = []

    async def on_done(batch_idx: int, total: int) -> None:
        progress.append((batch_idx, total))

    async def fake_post(self, url, **kwargs):
        json_payload = kwargs.get("json") or {}
        inputs = json_payload["input"]
        if isinstance(inputs, str):
            inputs = [inputs]
        dim = 2
        return type(
            "Resp",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"embeddings": [[0.0] * dim for _ in inputs]},
            },
        )()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        post = fake_post

    monkeypatch.setattr(embeddings_client.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(embeddings_client.ollama_guard, "acquire", lambda: _FakeGuard())

    await embeddings_client.embed_batch(["a", "b", "c"], model="m", on_batch_complete=on_done)
    assert progress == [(1, 2), (2, 2)]
