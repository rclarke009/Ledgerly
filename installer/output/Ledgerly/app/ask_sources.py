"""Detect related documents for Ask responses."""

from __future__ import annotations

from typing import Any, Literal

from app.ask_retrieval_boost import related_doc_ids_for_question
from app.db import get_doc_ids_by_tag, get_document_title
from app.models import AskRequest, RelatedDocument, RetrievedChunk

RETRIEVED_DOC_LIMIT = 3
Reason = Literal["pinned", "retrieved", "topic_boost"]


def _title_for_doc(conn: Any, doc_id: str) -> str:
    title = get_document_title(conn, doc_id)
    return (title or doc_id).strip() or doc_id


def detect_related_documents(
    conn: Any,
    ask_request: AskRequest,
    top_chunks: list[RetrievedChunk],
    question: str,
) -> list[RelatedDocument]:
    """Merge pinned, retrieved, and topic-boosted documents for UI badges."""
    by_id: dict[str, RelatedDocument] = {}

    def add(doc_id: str, reason: Reason) -> None:
        if doc_id in by_id:
            existing = by_id[doc_id]
            if existing.reason == "pinned":
                return
            if reason == "pinned":
                by_id[doc_id] = RelatedDocument(
                    doc_id=doc_id,
                    title=_title_for_doc(conn, doc_id),
                    reason="pinned",
                )
            return
        by_id[doc_id] = RelatedDocument(
            doc_id=doc_id,
            title=_title_for_doc(conn, doc_id),
            reason=reason,
        )

    if ask_request.doc_id:
        add(ask_request.doc_id, "pinned")
    elif ask_request.doc_ids:
        for doc_id in ask_request.doc_ids:
            add(doc_id, "pinned")
    elif ask_request.tag:
        for doc_id in get_doc_ids_by_tag(conn, ask_request.tag):
            add(doc_id, "pinned")

    best_by_doc: dict[str, float] = {}
    for chunk in top_chunks:
        prev = best_by_doc.get(chunk.doc_id, -1.0)
        if chunk.score > prev:
            best_by_doc[chunk.doc_id] = chunk.score
    ranked = sorted(best_by_doc.items(), key=lambda x: x[1], reverse=True)
    for doc_id, _score in ranked[:RETRIEVED_DOC_LIMIT]:
        add(doc_id, "retrieved")

    for doc_id in related_doc_ids_for_question(conn, question):
        add(doc_id, "topic_boost")

    return list(by_id.values())
