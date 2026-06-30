"""Tests for mortgage-aware Ask improvements."""

from __future__ import annotations

import sqlite3
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.ask_fast_paths import try_fast_path_answer
from app.ask_graph import build_prompt_and_chunks
from app.ask_retrieval_boost import merge_retrieved_chunks, related_doc_ids_for_question
from app.db import (
    create_db,
    find_doc_ids_by_label_keyword,
    insert_document,
    insert_obligation,
)
from app.models import AskRequest, RetrievedChunk
from app.retrieval import retrieve_top_k


@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "mortgage.sqlite"))
    create_db(c)
    return c


def test_find_doc_ids_by_label_keyword(conn):
    now = int(time.time())
    insert_document(conn, "mortgage-doc", now, title="July mortgage", source="statement.pdf")
    insert_document(conn, "other-doc", now, title="Tax return", source="1120s.pdf")
    conn.commit()
    assert find_doc_ids_by_label_keyword(conn, "mortgage") == ["mortgage-doc"]


def test_related_doc_ids_includes_obligation_document(conn):
    now = int(time.time())
    insert_document(conn, "mortgage-doc", now, title="Home loan", source="loan.pdf")
    insert_obligation(
        conn,
        "obl-1",
        "Monthly mortgage payment",
        "2026-07-01",
        now,
        2247.0,
        None,
        "mortgage-doc",
    )
    conn.commit()
    doc_ids = related_doc_ids_for_question(conn, "what is my total mortgage payment")
    assert "mortgage-doc" in doc_ids


def test_mortgage_payment_fast_path(conn):
    now = int(time.time())
    insert_obligation(
        conn,
        "obl-1",
        "Mortgage Statement - July 2026",
        "2026-07-01",
        now,
        2247.0,
        None,
        None,
    )
    conn.commit()
    answer = try_fast_path_answer(conn, "What is my total mortgage payment?")
    assert answer is not None
    assert "$2,247" in answer
    assert "2026-07-01" in answer


def test_merge_retrieved_chunks_prefers_higher_scores():
    primary = [
        RetrievedChunk(chunk_id="a:0", doc_id="a", score=0.4, content_snippet="tax"),
        RetrievedChunk(chunk_id="b:0", doc_id="b", score=0.3, content_snippet="other"),
    ]
    extra = [
        RetrievedChunk(chunk_id="c:0", doc_id="c", score=0.9, content_snippet="mortgage payment $2,247"),
    ]
    merged = merge_retrieved_chunks(primary, extra, 2)
    assert merged[0].doc_id == "c"
    assert merged[1].doc_id == "a"


@pytest.mark.asyncio
async def test_build_prompt_mortgage_payment_skips_llm(conn):
    now = int(time.time())
    insert_obligation(
        conn,
        "obl-1",
        "Mortgage Statement - July 2026",
        "2026-07-01",
        now,
        2247.0,
        None,
        None,
    )
    conn.commit()
    req = AskRequest(question="What is my total mortgage payment?", top_k=3)

    with patch("app.llm_client.answer_with_context", new_callable=AsyncMock) as mock_llm:
        _messages, _chunks, route, has_context, direct, _related = await build_prompt_and_chunks(conn, req)
        mock_llm.assert_not_called()

    assert route == "fast_path"
    assert has_context is True
    assert direct is not None
    assert "$2,247" in direct


@pytest.mark.asyncio
async def test_retrieve_boosts_mortgage_docs(conn):
    now = int(time.time())
    insert_document(conn, "mortgage-doc", now, title="Mortgage Statement", source="mortgage.pdf")
    insert_document(conn, "tax-doc", now, title="Tax return", source="1120s.pdf")
    conn.commit()

    vec = [0.0] * 768
    vec[0] = 1.0

    async def fake_retrieve_rows(_conn, _query_vec, top_k, *, doc_id=None, doc_ids=None):
        if doc_ids == ["mortgage-doc"]:
            return [
                RetrievedChunk(
                    chunk_id="mortgage-doc:0",
                    doc_id="mortgage-doc",
                    score=0.95,
                    content_snippet="Total amount due $2,247.00",
                )
            ]
        return [
            RetrievedChunk(
                chunk_id="tax-doc:0",
                doc_id="tax-doc",
                score=0.55,
                content_snippet="Mortgages, notes, bonds payable",
            )
        ]

    with patch("app.retrieval._retrieve_rows", side_effect=fake_retrieve_rows):
        with patch("app.retrieval.RERANK_ENABLED", False):
            chunks = await retrieve_top_k(
                conn,
                vec,
                3,
                question="what is my total mortgage payment",
            )

    assert any(c.doc_id == "mortgage-doc" for c in chunks)
    assert chunks[0].doc_id == "mortgage-doc"
