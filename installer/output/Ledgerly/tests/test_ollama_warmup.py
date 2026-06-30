"""Tests for Ollama tab warmup."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import ollama_warmup as warmup_mod
from app.main import app


@pytest.fixture(autouse=True)
def _reset_warmup():
    warmup_mod.reset_warmup_state()
    yield
    warmup_mod.reset_warmup_state()


def _mock_client(*, embed_ok: bool = True, chat_ok: bool = True):
    mock = MagicMock()

    async def post(url, json=None, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "/api/embed" in url:
            if not embed_ok:
                raise RuntimeError("embed failed")
            resp.json.return_value = {"embeddings": [[0.1, 0.2]]}
        elif "/api/chat" in url:
            if not chat_ok:
                raise RuntimeError("chat failed")
            resp.json.return_value = {"message": {"content": "ok"}}
        else:
            raise AssertionError(f"unexpected url {url}")
        return resp

    mock.post = AsyncMock(side_effect=post)
    return mock


async def _drain_warmup_tasks():
    await asyncio.sleep(0.05)
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_ask_warmup_calls_embed_then_llm():
    mock_http = _mock_client()
    with patch("app.ollama_warmup.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_http
        result = await warmup_mod.request_warmup("ask")
        assert result == {"status": "started", "profile": "ask"}
        await _drain_warmup_tasks()

    assert warmup_mod.get_warmup_status()["ask"] == "ready"
    calls = mock_http.post.call_args_list
    assert len(calls) == 2
    embed_payload = calls[0].kwargs["json"]
    chat_payload = calls[1].kwargs["json"]
    assert embed_payload["input"] == "warmup"
    assert embed_payload["keep_alive"]
    assert chat_payload["options"]["num_predict"] == 1
    assert chat_payload["keep_alive"]


@pytest.mark.asyncio
async def test_ingest_warmup_calls_embed_then_vision():
    mock_http = _mock_client()
    with patch("app.ollama_warmup.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_http
        result = await warmup_mod.request_warmup("ingest")
        assert result == {"status": "started", "profile": "ingest"}
        await _drain_warmup_tasks()

    assert warmup_mod.get_warmup_status()["ingest"] == "ready"
    chat_payload = mock_http.post.call_args_list[1].kwargs["json"]
    from app.config import LLAVA_MODEL

    assert chat_payload["model"] == LLAVA_MODEL


@pytest.mark.asyncio
async def test_second_request_returns_ready_without_new_http():
    mock_http = _mock_client()
    with patch("app.ollama_warmup.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_http
        await warmup_mod.request_warmup("ask")
        await _drain_warmup_tasks()
        first_calls = len(mock_http.post.call_args_list)
        result = await warmup_mod.request_warmup("ask")
        assert result == {"status": "ready", "profile": "ask"}
        assert len(mock_http.post.call_args_list) == first_calls


@pytest.mark.asyncio
async def test_concurrent_request_while_running_returns_warming():
    gate = asyncio.Event()

    async def slow_post(url, json=None, **kwargs):
        await gate.wait()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "/api/embed" in url:
            resp.json.return_value = {"embeddings": [[0.0]]}
        else:
            resp.json.return_value = {"message": {"content": "ok"}}
        return resp

    mock_http = MagicMock()
    mock_http.post = AsyncMock(side_effect=slow_post)
    with patch("app.ollama_warmup.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_http
        first = await warmup_mod.request_warmup("ask")
        assert first["status"] == "started"
        second = await warmup_mod.request_warmup("ask")
        assert second == {"status": "warming", "profile": "ask"}
        gate.set()
        await _drain_warmup_tasks()


@pytest.mark.asyncio
async def test_ingest_skips_embed_when_ask_already_warmed():
    mock_http = _mock_client()
    with patch("app.ollama_warmup.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_http
        await warmup_mod.request_warmup("ask")
        await _drain_warmup_tasks()
        embed_calls_after_ask = sum(
            1 for c in mock_http.post.call_args_list if "/api/embed" in c.args[0]
        )
        assert embed_calls_after_ask == 1

        await warmup_mod.request_warmup("ingest")
        await _drain_warmup_tasks()
        embed_calls_after_ingest = sum(
            1 for c in mock_http.post.call_args_list if "/api/embed" in c.args[0]
        )
        assert embed_calls_after_ingest == 1


@pytest.mark.asyncio
async def test_warmup_disabled_returns_skipped():
    with patch("app.ollama_warmup.OLLAMA_WARMUP_ENABLED", False):
        result = await warmup_mod.request_warmup("ask")
    assert result == {"status": "skipped", "profile": "ask"}


@pytest.mark.asyncio
async def test_warmup_failure_resets_to_idle():
    mock_http = _mock_client(chat_ok=False)
    with patch("app.ollama_warmup.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_http
        await warmup_mod.request_warmup("ask")
        await _drain_warmup_tasks()
    assert warmup_mod.get_warmup_status()["ask"] == "idle"


def test_warmup_ask_endpoint():
    mock_http = _mock_client()
    with patch("app.ollama_warmup.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_http
        client = TestClient(app)
        r = client.post("/warmup/ask")
        assert r.status_code == 200
        assert r.json()["status"] == "started"
        assert r.json()["profile"] == "ask"


def test_warmup_status_endpoint():
    client = TestClient(app)
    r = client.get("/warmup/status")
    assert r.status_code == 200
    data = r.json()
    assert data["ask"] == "idle"
    assert data["ingest"] == "idle"
    assert "ready_until" in data
