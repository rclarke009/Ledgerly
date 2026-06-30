"""Persist Ask Ledgerly Q&A history to the database."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.db import (
    get_conversation_last_turn_id,
    insert_ask_history_complete,
    insert_ask_history_pending,
    list_ask_history,
    list_conversation_turns,
    update_ask_history_result,
)
from app.models import AskHistoryItem, AskRequest, RelatedDocument, RetrievedChunk


@dataclass
class AskTurnResult:
    turn_id: str
    conversation_id: str


def doc_filter_from_request(ask_request: AskRequest) -> str | None:
    if ask_request.doc_id:
        return ask_request.doc_id
    if ask_request.tag:
        return f"tag:{ask_request.tag}"
    return None


def _conversation_ids_for_insert(
    conn: Any,
    ask_request: AskRequest,
    *,
    turn_id: str,
) -> tuple[str, str | None]:
    if ask_request.conversation_id:
        parent_id = get_conversation_last_turn_id(conn, ask_request.conversation_id)
        return ask_request.conversation_id, parent_id
    return turn_id, None


def insert_pending_for_job(
    conn: Any,
    job_id: str,
    ask_request: AskRequest,
    asked_at: float | None = None,
) -> AskTurnResult:
    ts = int(asked_at if asked_at is not None else time.time())
    conversation_id, parent_id = _conversation_ids_for_insert(conn, ask_request, turn_id=job_id)
    insert_ask_history_pending(
        conn,
        id=job_id,
        job_id=job_id,
        asked_at=ts,
        question=ask_request.question.strip(),
        doc_filter=doc_filter_from_request(ask_request),
        conversation_id=conversation_id,
        parent_id=parent_id,
    )
    return AskTurnResult(turn_id=job_id, conversation_id=conversation_id)


def insert_complete_answer(
    conn: Any,
    ask_request: AskRequest,
    answer: str,
    *,
    tables: list | None = None,
    charts: list | None = None,
    route: str | None = None,
    asked_at: float | None = None,
    related_documents: list[RelatedDocument] | None = None,
    top_chunks: list[RetrievedChunk] | None = None,
    turn_id: str | None = None,
) -> AskTurnResult:
    ts = int(asked_at if asked_at is not None else time.time())
    tid = turn_id or uuid.uuid4().hex
    conversation_id, parent_id = _conversation_ids_for_insert(conn, ask_request, turn_id=tid)
    tables_json = json.dumps(tables) if tables else None
    charts_json = json.dumps(charts) if charts else None
    related_json = (
        json.dumps([d.model_dump() for d in related_documents]) if related_documents else None
    )
    chunks_json = None
    if top_chunks:
        chunks_json = json.dumps(
            [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in top_chunks]
        )
    insert_ask_history_complete(
        conn,
        id=tid,
        asked_at=ts,
        question=ask_request.question.strip(),
        answer=answer,
        tables_json=tables_json,
        charts_json=charts_json,
        route=route,
        doc_filter=doc_filter_from_request(ask_request),
        conversation_id=conversation_id,
        parent_id=parent_id,
        related_docs_json=related_json,
        top_chunks_json=chunks_json,
    )
    return AskTurnResult(turn_id=tid, conversation_id=conversation_id)


def update_job_result(
    conn: Any,
    job_id: str,
    *,
    status: str,
    answer: str | None = None,
    tables: list | None = None,
    charts: list | None = None,
    route: str | None = None,
    error: str | None = None,
    related_documents: list[RelatedDocument] | None = None,
    top_chunks: list | None = None,
) -> None:
    tables_json = json.dumps(tables) if tables else None
    charts_json = json.dumps(charts) if charts else None
    update_ask_history_result(
        conn,
        job_id,
        status=status,
        answer=answer,
        tables_json=tables_json,
        charts_json=charts_json,
        route=route,
        error=error,
        related_docs_json=(
            json.dumps([d.model_dump() for d in related_documents]) if related_documents else None
        ),
        top_chunks_json=json.dumps(top_chunks) if top_chunks else None,
    )


def _parse_related_docs(raw: str | None) -> list[RelatedDocument]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[RelatedDocument] = []
    for item in data:
        if isinstance(item, dict) and item.get("doc_id"):
            out.append(RelatedDocument.model_validate(item))
    return out


def _row_to_history_item(row: tuple) -> AskHistoryItem:
    (
        id_,
        job_id,
        asked_at,
        status,
        question,
        answer,
        tables_json,
        charts_json,
        route,
        doc_filter,
        error,
        conversation_id,
        parent_id,
        related_docs_json,
        _top_chunks_json,
    ) = row
    tables = json.loads(tables_json) if tables_json else []
    charts = json.loads(charts_json) if charts_json else []
    return AskHistoryItem(
        id=id_,
        job_id=job_id,
        asked_at=int(asked_at),
        status=status,
        question=question,
        answer=answer,
        tables=tables,
        charts=charts,
        route=route,
        doc_filter=doc_filter,
        error=error,
        conversation_id=conversation_id,
        parent_id=parent_id,
        related_documents=_parse_related_docs(related_docs_json),
    )


def rows_to_history_items(rows: list[tuple]) -> list[AskHistoryItem]:
    return [_row_to_history_item(row) for row in rows]


def fetch_ask_history(conn: Any, limit: int = 50) -> list[AskHistoryItem]:
    return rows_to_history_items(list_ask_history(conn, limit=limit))


def fetch_conversation(conn: Any, conversation_id: str) -> list[AskHistoryItem]:
    return rows_to_history_items(list_conversation_turns(conn, conversation_id))
