"""Ask pipeline: fast paths, heuristics, retrieval, prompt build."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable

from app.answer_format import ANSWER_FORMAT_PROMPT_SUFFIX
from app.ask_conversation import (
    expand_retrieval_query,
    load_conversation_turns,
    resolve_doc_scope,
)
from app.ask_fast_paths import detect_fast_path_kind, try_fast_path_answer, _is_mortgage_payment_question
from app.ask_sources import detect_related_documents
from app.ask_tool_router import run_ask_tools
from app.ask_trace import log_ask_event
from app.config import LLM_INTER_CALL_SLEEP_SEC
from app.db import list_accounts, list_obligations, list_positions
from app.models import AskRequest, RelatedDocument, RetrievedChunk
from app import embeddings_client
from app.retrieval import retrieve_top_k

ProgressCallback = Callable[[str], Awaitable[None]] | None

Route = str  # fast_path | structured_data | rag | rag_only


def _normalize(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower())


def heuristic_route(question: str) -> Route | None:
    q = _normalize(question)
    if detect_fast_path_kind(question) or _is_mortgage_payment_question(question):
        return "fast_path"
    doc_patterns = (
        r"\b1099\b",
        r"\btax document",
        r"\bfind my\b",
        r"\bfind\b.*\b(document|form|statement|letter)\b",
        r"\bw-?2\b",
        r"\b1098\b",
        r"\bmortgage\b",
        r"\bhome\s+loan\b",
        r"\bpayment\s+statement\b",
    )
    if any(re.search(p, q) for p in doc_patterns):
        return "rag_only"
    structured_patterns = (
        r"\bmatur",
        r"\bcd\b",
        r"\bbill",
        r"\bobligation",
        r"\bdue soon",
        r"\baccount",
        r"\bholding",
        r"\bsummarize",
        r"\bhow much",
    )
    if any(re.search(p, q) for p in structured_patterns):
        return "structured_data"
    return None


async def _maybe_sleep_before_llm() -> None:
    if LLM_INTER_CALL_SLEEP_SEC > 0:
        await asyncio.sleep(LLM_INTER_CALL_SLEEP_SEC)


async def _layer2_summary(conn: Any) -> str:
    accounts = list_accounts(conn)
    positions = list_positions(conn)
    obligations = list_obligations(conn)
    if not accounts and not positions and not obligations:
        return ""
    lines = ["Your saved data:"]
    for acc_id, name, acc_type, institution, *_ in accounts[:20]:
        lines.append(f"- Account: {name}" + (f" ({institution or acc_type})" if institution or acc_type else ""))
    for row in positions[:30]:
        _pid, account_id, asset_type, desc, principal, rate, maturity, *_ = row
        amt = f"${principal:,.0f}" if principal is not None else "unknown amount"
        lines.append(
            f"- Position: {asset_type}" + (f" {desc}" if desc else "") + f", {amt}"
            + (f", matures {maturity}" if maturity else "")
        )
    for row in obligations[:20]:
        obl_id, desc, due_date, amount, *_ = row
        amt = f"${amount:,.0f}" if amount is not None else ""
        lines.append(f"- Obligation: {desc}, due {due_date}" + (f", {amt}" if amt else ""))
    return "\n".join(lines)


def _build_rag_messages(
    question: str,
    chunks: list[RetrievedChunk],
    layer2: str,
    tool_block: str,
    prior_turns: list[dict[str, str]],
) -> list[dict[str, str]]:
    parts = [
        "You are Ledgerly, a private financial document assistant.",
        "Answer using the context below. Be concise and cite document ids when relevant.",
        (
            "If you used specific documents, briefly name them at the start "
            '(e.g. "Based on your CD maturity letter…"). '
            "If the user pinned a document, treat it as the primary source."
        ),
        "When tool results are present, treat them as authoritative for holdings, rates, and triggers.",
    ]
    if tool_block:
        parts.append(tool_block)
    elif layer2:
        parts.append(layer2)
    if chunks:
        parts.append("Document excerpts:")
        for c in chunks:
            parts.append(f"[doc {c.doc_id} chunk {c.chunk_id}] {c.content_snippet}")
    else:
        parts.append("No matching document excerpts were found.")
    parts.append(ANSWER_FORMAT_PROMPT_SUFFIX)
    messages: list[dict[str, str]] = [{"role": "system", "content": "\n\n".join(parts)}]
    for turn in prior_turns:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})
    return messages


def _need_more_context(
    chunks: list[RetrievedChunk],
    layer2: str,
    tool_block: str,
) -> bool:
    return not chunks and not layer2.strip() and not tool_block.strip()


def _has_doc_scope(ask_request: AskRequest) -> bool:
    return bool(ask_request.doc_id or ask_request.doc_ids or ask_request.tag)


def _skip_rag_for_structured(
    route: str,
    layer2: str,
    tool_block: str,
    ask_request: AskRequest,
) -> bool:
    has_data = bool(layer2.strip()) or bool(tool_block.strip())
    return route == "structured_data" and has_data and not _has_doc_scope(ask_request)


async def build_prompt_and_chunks(
    conn: Any,
    ask_request: AskRequest,
    *,
    progress_cb: ProgressCallback = None,
) -> tuple[list[dict[str, str]], list[RetrievedChunk], str, bool, str | None, list[RelatedDocument]]:
    question = (ask_request.question or "").strip()
    if not question:
        return [], [], "empty", False, None, []

    scoped_request = resolve_doc_scope(conn, ask_request)
    prior_turns: list[dict[str, str]] = []
    if scoped_request.conversation_id:
        prior_turns = load_conversation_turns(conn, scoped_request.conversation_id)

    if progress_cb:
        await progress_cb("routing")

    route = heuristic_route(question) or "rag"
    log_ask_event("classify_route", route=route, heuristic=True)

    if route == "fast_path":
        answer = try_fast_path_answer(conn, question)
        if answer:
            log_ask_event("build_prompt", route="fast_path", llm_calls=0)
            related = detect_related_documents(conn, scoped_request, [], question)
            return [], [], "fast_path", True, answer, related

    layer2 = ""
    tool_block = ""
    tool_results: list[dict] = []
    if route in ("structured_data", "rag", "rag_only"):
        layer2 = await _layer2_summary(conn)
        if progress_cb:
            await progress_cb("tools")
        tool_block, tool_results = await run_ask_tools(
            conn, question, route, ask_request=scoped_request
        )

    top_chunks: list[RetrievedChunk] = []
    skip_rag = _skip_rag_for_structured(route, layer2, tool_block, scoped_request)
    if skip_rag:
        log_ask_event("retrieval_gate", skipped=True, reason="structured_layer2", layer2_chars=len(layer2))
    elif scoped_request.use_rag and route in ("rag", "rag_only", "structured_data"):
        if progress_cb:
            await progress_cb("searching")
        retrieval_query = expand_retrieval_query(question, prior_turns)
        query_vec = await embeddings_client.embed_text(retrieval_query)
        top_chunks = await retrieve_top_k(
            conn,
            query_vec,
            scoped_request.top_k,
            doc_id=scoped_request.doc_id,
            doc_ids=scoped_request.doc_ids,
            tag=scoped_request.tag,
            question=retrieval_query,
        )
        log_ask_event("retrieval_gate", chunks=len(top_chunks), layer2_chars=len(layer2))

    related_documents = detect_related_documents(conn, scoped_request, top_chunks, question)

    if _need_more_context(top_chunks, layer2, tool_block) and route != "structured_data":
        return [], [], route, False, None, related_documents

    if progress_cb:
        await progress_cb("generating")

    messages = _build_rag_messages(question, top_chunks, layer2, tool_block, prior_turns)
    log_ask_event(
        "build_prompt",
        route=route,
        chunks=len(top_chunks),
        tools=len(tool_results),
        prompt_len=sum(len(m.get("content") or "") for m in messages),
    )
    return messages, top_chunks, route, True, None, related_documents
