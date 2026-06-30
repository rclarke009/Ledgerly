"""Conversation context for multi-turn Ask."""

from __future__ import annotations

from typing import Any

from app.db import get_conversation_doc_filter, list_conversation_turns
from app.models import AskRequest

ASSISTANT_HISTORY_MAX_CHARS = 2000
DEFAULT_MAX_TURNS = 6


def expand_retrieval_query(question: str, prior_turns: list[dict[str, str]]) -> str:
    """Build a standalone retrieval query from follow-up + prior user turn."""
    q = (question or "").strip()
    if not prior_turns:
        return q
    last_user = ""
    for turn in reversed(prior_turns):
        if turn.get("role") == "user":
            last_user = (turn.get("content") or "").strip()
            break
    if last_user:
        return f"{last_user} | {q}"
    return q


def load_conversation_turns(
    conn: Any,
    conversation_id: str,
    *,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> list[dict[str, str]]:
    """Load prior user/assistant turns for LLM context (excludes current question)."""
    rows = list_conversation_turns(conn, conversation_id, limit=500)
    turns: list[dict[str, str]] = []
    for row in rows:
        status = row[3]
        if status != "complete":
            continue
        question = (row[4] or "").strip()
        answer = (row[5] or "").strip()
        if question:
            turns.append({"role": "user", "content": question})
        if answer:
            content = answer
            if len(content) > ASSISTANT_HISTORY_MAX_CHARS:
                content = content[:ASSISTANT_HISTORY_MAX_CHARS] + "…"
            turns.append({"role": "assistant", "content": content})
    if len(turns) > max_turns * 2:
        turns = turns[-(max_turns * 2) :]
    return turns


def resolve_doc_scope(conn: Any, ask_request: AskRequest) -> AskRequest:
    """Inherit doc scope from conversation root when request has no explicit scope."""
    if ask_request.doc_id or ask_request.doc_ids or ask_request.tag:
        return ask_request
    if not ask_request.conversation_id:
        return ask_request
    doc_filter = get_conversation_doc_filter(conn, ask_request.conversation_id)
    if not doc_filter:
        return ask_request
    if doc_filter.startswith("tag:"):
        return ask_request.model_copy(update={"tag": doc_filter[4:]})
    return ask_request.model_copy(update={"doc_id": doc_filter})
