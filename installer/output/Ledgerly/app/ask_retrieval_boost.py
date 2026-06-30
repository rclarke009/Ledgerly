"""Question-aware retrieval boosts for Ask."""

from __future__ import annotations

import re
from typing import Any

from app.db import find_doc_ids_by_label_keyword, list_obligations
from app.models import RetrievedChunk

_TOPIC_LABEL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "mortgage": ("mortgage",),
}


def topic_label_keywords(question: str) -> list[str]:
    q = (question or "").lower()
    topics: list[str] = []
    if re.search(r"\bmortgage\b|\bhome\s+loan\b|\bescrow\b", q):
        topics.append("mortgage")
    return topics


def related_doc_ids_for_question(conn: Any, question: str) -> list[str]:
    topics = topic_label_keywords(question)
    if not topics:
        return []
    doc_ids: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        for keyword in _TOPIC_LABEL_KEYWORDS.get(topic, (topic,)):
            for doc_id in find_doc_ids_by_label_keyword(conn, keyword):
                if doc_id not in seen:
                    seen.add(doc_id)
                    doc_ids.append(doc_id)
    if "mortgage" in topics:
        for row in list_obligations(conn):
            doc_id = row[5] if len(row) > 5 else None
            desc = (row[1] or "").lower()
            if doc_id and "mortgage" in desc and doc_id not in seen:
                seen.add(doc_id)
                doc_ids.append(doc_id)
    return doc_ids


def merge_retrieved_chunks(
    primary: list[RetrievedChunk],
    extra: list[RetrievedChunk],
    top_k: int,
) -> list[RetrievedChunk]:
    seen: set[str] = set()
    merged: list[RetrievedChunk] = []
    for chunk in sorted(primary + extra, key=lambda c: c.score, reverse=True):
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        merged.append(chunk)
        if len(merged) >= top_k:
            break
    return merged
