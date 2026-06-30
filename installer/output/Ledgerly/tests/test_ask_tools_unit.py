"""Unit tests for Ask local tools."""

from __future__ import annotations

import sqlite3
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.ask_calculations import (
    calculate_compound_interest,
    calculate_simple_interest,
    compare_after_tax_yield,
)
from app.ask_tool_router import select_tools_for_question
from app.ask_tools import execute_tool, tool_schemas
from app.db import create_db, insert_account, insert_obligation, insert_position
from app.models import AskRequest


@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "tools.sqlite"))
    create_db(c)
    return c


def test_tool_schemas_count():
    names = {s["function"]["name"] for s in tool_schemas()}
    assert "get_positions" in names
    assert "get_decision_memo" in names
    assert "calculate_compound_interest" in names
    assert "get_stock_quote" not in names


def test_calculate_compound_interest():
    out = calculate_compound_interest(10000, 0.05, 10)
    assert out["final_amount"] == pytest.approx(16288.95, rel=0.01)
    assert out["total_interest"] == pytest.approx(6288.95, rel=0.01)


def test_compare_after_tax_yield():
    out = compare_after_tax_yield(10000, 4.0, 1.0, 0.22, state_rate=0.0)
    assert out["gross_interest"] == pytest.approx(400.0, rel=0.01)
    assert out["after_tax_interest"] == pytest.approx(312.0, rel=0.01)


@pytest.mark.asyncio
async def test_get_positions_filter(conn):
    now = int(time.time())
    insert_account(conn, "acc1", "Test Bank", now)
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
        "2099-06-01",
        None,
    )
    conn.commit()
    result = await execute_tool(conn, "get_positions", {"asset_type_keyword": "cd"})
    assert result["count"] == 1
    assert result["positions"][0]["principal"] == 10000.0


@pytest.mark.asyncio
async def test_get_cd_benchmark_rates_local_only(conn):
    result = await execute_tool(conn, "get_cd_benchmark_rates", {})
    assert "benchmarks" in result
    assert len(result["benchmarks"]) >= 1
    assert result["source"] == "local_curated"


@pytest.mark.asyncio
async def test_liquidity_cross_check(conn):
    now = int(time.time())
    insert_account(conn, "acc1", "Bank", now)
    insert_position(
        conn,
        "p1",
        "acc1",
        "CD",
        now,
        now,
        None,
        5000.0,
        4.0,
        "2026-07-01",
        None,
    )
    insert_obligation(conn, "o1", "Property tax", "2026-07-05", now, 4500.0, None, None)
    conn.commit()
    result = await execute_tool(
        conn,
        "liquidity_cross_check",
        {"position_id": "p1"},
    )
    assert "summary" in result
    assert result.get("covers_obligations") is True


def test_select_tools_maturity_question():
    tools = select_tools_for_question(
        "What's maturing in the next 3 months?",
        "structured_data",
    )
    names = [t[0] for t in tools]
    assert "get_positions" in names


def test_select_tools_calc_skipped_without_numbers():
    tools = select_tools_for_question(
        "Tell me about compound interest in general",
        "rag",
    )
    names = [t[0] for t in tools]
    assert "calculate_compound_interest" not in names


def test_select_tools_calc_with_numbers():
    tools = select_tools_for_question(
        "If I put $10,000 in a 1-year CD at 4% annual interest, what's the interest?",
        "rag",
    )
    names = [t[0] for t in tools]
    calc_tools = [n for n in names if n.startswith("calculate_") or n == "compare_after_tax_yield"]
    assert calc_tools


@pytest.mark.asyncio
async def test_get_decision_memo_no_triggers(conn):
    result = await execute_tool(conn, "get_decision_memo", {})
    assert result["status"] == "no_action_required"
    assert "memo" in result


@pytest.mark.asyncio
async def test_ask_graph_includes_tool_block(conn):
    from app.ask_graph import build_prompt_and_chunks

    now = int(time.time())
    insert_account(conn, "acc1", "Bank", now)
    insert_position(conn, "p1", "acc1", "CD", now, now, None, 5000.0, None, "2099-06-01", None)
    conn.commit()
    req = AskRequest(question="How much do I have in CDs and what are benchmarks?", top_k=3)

    with patch("app.embeddings_client.embed_text", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = [0.1] * 8
        messages, _chunks, route, has_context, direct, _related = await build_prompt_and_chunks(
            conn, req
        )
        mock_embed.assert_not_called()

    assert has_context is True
    assert direct is None
    assert route == "structured_data"
    system = messages[0]["content"]
    assert "Tool results" in system
