"""Ask pipeline: fast paths, heuristics, retrieval, prompt build."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable

from app.answer_format import ANSWER_FORMAT_PROMPT_SUFFIX
from app.ask_fast_paths import detect_fast_path_kind, try_fast_path_answer, _is_mortgage_payment_question
from app.ask_trace import log_ask_event
from app.config import LLM_INTER_CALL_SLEEP_SEC
from app.db import list_accounts, list_obligations, list_positions
from app.finance_tools_client import fetch_finance_tools_block
from app.models import AskRequest, RetrievedChunk
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


def _build_rag_prompt(question: str, chunks: list[RetrievedChunk], layer2: str, finance: str) -> str:
    parts = [
        "You are Ledgerly, a private financial document assistant.",
        "Answer using the context below. Be concise and cite document ids when relevant.",
    ]
    if layer2:
        parts.append(layer2)
    if finance:
        parts.append(finance)
    if chunks:
        parts.append("Document excerpts:")
        for c in chunks:
            parts.append(f"[doc {c.doc_id} chunk {c.chunk_id}] {c.content_snippet}")
    else:
        parts.append("No matching document excerpts were found.")
    parts.append(f"Question:\n{question}")
    parts.append(ANSWER_FORMAT_PROMPT_SUFFIX)
    return "\n\n".join(parts)


def _need_more_context(chunks: list[RetrievedChunk], layer2: str) -> bool:
    return not chunks and not layer2.strip()


def _has_doc_scope(ask_request: AskRequest) -> bool:
    return bool(ask_request.doc_id or ask_request.doc_ids or ask_request.tag)


def _skip_rag_for_structured(route: str, layer2: str, ask_request: AskRequest) -> bool:
    return route == "structured_data" and bool(layer2.strip()) and not _has_doc_scope(ask_request)


async def build_prompt_and_chunks(
    conn: Any,
    ask_request: AskRequest,
    *,
    progress_cb: ProgressCallback = None,
) -> tuple[str, list[RetrievedChunk], str, bool, str | None]:
    question = (ask_request.question or "").strip()
    if not question:
        return "", [], "empty", False, None

    if progress_cb:
        await progress_cb("routing")

    route = heuristic_route(question) or "rag"
    log_ask_event("classify_route", route=route, heuristic=True)

    if route == "fast_path":
        answer = try_fast_path_answer(conn, question)
        if answer:
            log_ask_event("build_prompt", route="fast_path", llm_calls=0)
            return "", [], "fast_path", True, answer

    layer2 = ""
    if route in ("structured_data", "rag"):
        layer2 = await _layer2_summary(conn)

    finance_block = ""
    if route == "rag":
        await _maybe_sleep_before_llm()
        finance_block = await fetch_finance_tools_block(question, skip_llm=True)

    top_chunks: list[RetrievedChunk] = []
    skip_rag = _skip_rag_for_structured(route, layer2, ask_request)
    if skip_rag:
        log_ask_event("retrieval_gate", skipped=True, reason="structured_layer2", layer2_chars=len(layer2))
    elif ask_request.use_rag and route in ("rag", "rag_only", "structured_data"):
        if progress_cb:
            await progress_cb("searching")
        query_vec = await embeddings_client.embed_text(question)
        top_chunks = await retrieve_top_k(
            conn,
            query_vec,
            ask_request.top_k,
            doc_id=ask_request.doc_id,
            doc_ids=ask_request.doc_ids,
            tag=ask_request.tag,
            question=question,
        )
        log_ask_event("retrieval_gate", chunks=len(top_chunks), layer2_chars=len(layer2))

    if _need_more_context(top_chunks, layer2) and route != "structured_data":
        return "", [], route, False, None

    if progress_cb:
        await progress_cb("generating")

    prompt = _build_rag_prompt(question, top_chunks, layer2, finance_block)
    log_ask_event("build_prompt", route=route, chunks=len(top_chunks), prompt_len=len(prompt))
    return prompt, top_chunks, route, True, None
