"""Vector retrieval over ingested chunks."""

from __future__ import annotations

import time
from typing import Any

from app.ask_retrieval_boost import merge_retrieved_chunks, related_doc_ids_for_question
from app.ask_trace import log_ask_event
from app.config import RERANK_ENABLED, RERANK_INITIAL_K_MAX, RERANK_INITIAL_K_MULTIPLIER
from app.db import get_doc_ids_by_tag, get_embeddings_for_retrieval, is_postgres_conn
from app.models import RetrievedChunk
from app.reranker import rerank
from app.similarity import cosine_similarity


async def _retrieve_rows(
    conn: Any,
    query_vec: list[float],
    top_k: int,
    *,
    doc_id: str | None = None,
    doc_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.retrieve_top_k(
            conn, query_vec, top_k, doc_id=doc_id, doc_ids=doc_ids
        )

    rows_raw = get_embeddings_for_retrieval(conn, doc_id=doc_id, doc_ids=doc_ids)
    scored: list[tuple[float, str, str, str]] = []
    for chunk_id, did, vec, content in rows_raw:
        score = cosine_similarity(query_vec, vec)
        scored.append((score, chunk_id, did, content))
    scored.sort(key=lambda x: x[0], reverse=True)
    initial_k = top_k
    if RERANK_ENABLED:
        initial_k = min(top_k * RERANK_INITIAL_K_MULTIPLIER, RERANK_INITIAL_K_MAX)
    rows: list[RetrievedChunk] = []
    for score, chunk_id, did, content in scored[:initial_k]:
        snippet = (content or "")[:300]
        rows.append(RetrievedChunk(chunk_id=chunk_id, doc_id=did, score=score, content_snippet=snippet))
    return rows


async def retrieve_top_k(
    conn: Any,
    query_vec: list[float],
    top_k: int,
    *,
    doc_id: str | None = None,
    doc_ids: list[str] | None = None,
    tag: str | None = None,
    question: str | None = None,
) -> list[RetrievedChunk]:
    t0 = time.perf_counter()
    effective_doc_ids = doc_ids
    if tag and not doc_id and not doc_ids:
        effective_doc_ids = get_doc_ids_by_tag(conn, tag)

    rows = await _retrieve_rows(
        conn, query_vec, top_k, doc_id=doc_id, doc_ids=effective_doc_ids
    )

    if (
        question
        and not doc_id
        and not effective_doc_ids
        and not tag
    ):
        related_doc_ids = related_doc_ids_for_question(conn, question)
        if related_doc_ids:
            extra = await _retrieve_rows(conn, query_vec, top_k, doc_ids=related_doc_ids)
            rows = merge_retrieved_chunks(rows, extra, top_k)
            log_ask_event(
                "retrieval_boost",
                topic="mortgage" if related_doc_ids else None,
                related_docs=len(related_doc_ids),
                merged=len(rows),
            )

    if RERANK_ENABLED and rows:
        rows = await rerank(query_vec, rows, top_k)

    log_ask_event(
        "retrieve",
        duration_ms=int((time.perf_counter() - t0) * 1000),
        top_k=top_k,
        returned=len(rows),
    )
    return rows[:top_k]
