"""Unit tests for ask graph heuristics and fast paths."""

from __future__ import annotations

import sqlite3
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.ask_fast_paths import detect_fast_path_kind, try_fast_path_answer
from app.ask_graph import build_prompt_and_chunks, heuristic_route
from app.db import create_db, insert_account, insert_position
from app.models import AskRequest


@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "ask.sqlite"))
    create_db(c)
    return c


def test_heuristic_route_presets():
    assert heuristic_route("What's maturing in the next 3 months?") == "fast_path"
    assert heuristic_route("Find my tax documents like 1099 forms.") == "rag_only"
    assert heuristic_route("How much do I have in CDs?") == "fast_path"
    assert heuristic_route("What is my total mortgage payment?") == "fast_path"
    assert heuristic_route("Show my mortgage statement") == "rag_only"


def test_needs_finance_intent_llm_skipped_by_default():
    from app.finance_tools_client import _needs_finance_intent_llm

    assert _needs_finance_intent_llm("What's maturing soon?") is False
    assert _needs_finance_intent_llm("What is the stock price of AAPL?") is True


@pytest.mark.asyncio
async def test_fast_path_maturing_no_llm(conn):
    now = int(time.time())
    insert_account(conn, "acc1", "Bank", now)
    insert_position(
        conn,
        "p1",
        "acc1",
        "CD",
        now,
        now,
        "12-month",
        10000.0,
        4.5,
        "2099-01-01",
        None,
    )
    conn.commit()
    answer = try_fast_path_answer(conn, "What's maturing in the next 3 months?")
    assert answer is not None
    assert "Maturities" in answer


@pytest.mark.asyncio
async def test_build_prompt_fast_path_zero_llm_calls(conn):
    now = int(time.time())
    insert_account(conn, "acc1", "Bank", now)
    insert_position(conn, "p1", "acc1", "CD", now, now, None, 5000.0, None, "2099-06-01", None)
    conn.commit()
    req = AskRequest(question="How much do I have in CDs?", top_k=3)

    with patch("app.llm_client.answer_with_context", new_callable=AsyncMock) as mock_llm:
        messages, chunks, route, has_context, direct, related = await build_prompt_and_chunks(conn, req)
        mock_llm.assert_not_called()

    assert route == "fast_path"
    assert has_context is True
    assert direct is not None
    assert "CD" in direct
    assert messages == []


@pytest.mark.asyncio
async def test_classify_route_skips_llm_for_cd_advice(conn):
    req = AskRequest(question="Summarize my accounts and holdings.", top_k=3)
    with patch("app.llm_client.answer_with_context", new_callable=AsyncMock) as mock_llm:
        _messages, _chunks, route, has_context, direct = (await build_prompt_and_chunks(conn, req))[:5]
        mock_llm.assert_not_called()
    assert route == "fast_path"
    assert direct is not None


@pytest.mark.asyncio
async def test_structured_route_skips_embed_when_layer2_present(conn):
    now = int(time.time())
    insert_account(conn, "acc1", "Bank", now)
    insert_position(conn, "p1", "acc1", "CD", now, now, None, 5000.0, None, "2099-06-01", None)
    conn.commit()
    req = AskRequest(question="Summarize my bills and obligations due soon.", top_k=3)

    with patch("app.embeddings_client.embed_text", new_callable=AsyncMock) as mock_embed:
        _messages, chunks, route, has_context, direct, _related = await build_prompt_and_chunks(conn, req)
        mock_embed.assert_not_called()

    assert route == "structured_data"
    assert has_context is True
    assert direct is None
    assert chunks == []


def test_detect_fast_path_kind():
    assert detect_fast_path_kind("Summarize my accounts and holdings.") == "accounts_summary"
