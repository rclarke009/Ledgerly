"""Local Ask tools: registry, schemas, and executors (no external data)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from app.ask_calculations import (
    calculate_cd_maturity_value,
    calculate_compound_interest,
    calculate_simple_interest,
    compare_after_tax_yield,
)
from app.config import (
    LIQUIDITY_CROSSCHECK_DAYS,
    MATURITY_DAYS_AHEAD,
    OBLIGATION_DAYS_AHEAD,
)
from app.dashboard import build_dashboard
from app.db import (
    get_account,
    get_document_tags,
    get_position,
    list_accounts,
    list_decision_history,
    list_documents,
    list_ira_overview,
    list_obligations,
    list_positions,
)
from app.decision_memo import (
    build_action_summary_memo,
    build_maturity_memo_sections,
    build_no_action_memo,
    format_operational_memo,
    liquidity_cross_check,
)
from app.models import AskRequest
from app.reference_data import (
    RateInfo,
    closest_cd_benchmark,
    compare_user_rate,
    fetch_cd_rates_local,
    mmf_benchmark,
)
from app.triggers import _parse_date, evaluate_triggers

ToolExecutor = Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]


def tool_schemas() -> list[dict[str, Any]]:
    """OpenAI/Ollama-compatible tool definitions (local-only)."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_positions",
                "description": "List tracked positions/CDs with optional filters.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "maturity_within_days": {"type": "integer", "description": "Maturity within N days"},
                        "asset_type_keyword": {"type": "string", "description": "Filter by asset type substring"},
                        "keyword": {"type": "string", "description": "Filter description or institution"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_obligations",
                "description": "List cash obligations/bills with optional filters.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "due_within_days": {"type": "integer"},
                        "keyword": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_accounts",
                "description": "List all tracked accounts.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_ira_overview",
                "description": "List IRA awareness rows (dates, notes — not investment advice).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "evaluate_triggers",
                "description": "Decision triggers in configured windows (maturity, obligations, IRA).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "liquidity_cross_check",
                "description": "Check if maturing principal covers nearby obligations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "position_id": {"type": "string"},
                        "maturity_date": {"type": "string", "description": "ISO date if position_id unknown"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_dashboard_snapshot",
                "description": "Home-style status: maturities, obligations, ladder totals.",
                "parameters": {
                    "type": "object",
                    "properties": {"days": {"type": "integer", "default": 90}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_cd_benchmark_rates",
                "description": "Curated generic CD benchmarks (no institution data sent externally).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_mmf_benchmark",
                "description": "Curated money-market benchmark APR.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compare_user_rate",
                "description": "Compare a holding APY percent to nearest CD/MMF benchmark.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_rate_apr": {"type": "number"},
                        "term_months": {"type": "integer"},
                    },
                    "required": ["user_rate_apr"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compare_roll_options",
                "description": "Structured hold/roll/MMF/wait analysis for a maturing CD.",
                "parameters": {
                    "type": "object",
                    "properties": {"position_id": {"type": "string"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_documents",
                "description": "Semantic search over ingested document chunks (local).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_document_metadata",
                "description": "List ingested documents or metadata for one doc_id.",
                "parameters": {
                    "type": "object",
                    "properties": {"doc_id": {"type": "string"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_decision_memo",
                "description": "Operational decision memo from triggers (local only, no OpenAI).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_decision_history",
                "description": "Past decision memos from local history.",
                "parameters": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 10}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calculate_compound_interest",
                "description": "Compound growth; rate as decimal (0.05 = 5%).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "principal": {"type": "number"},
                        "rate": {"type": "number"},
                        "years": {"type": "integer"},
                    },
                    "required": ["principal", "rate", "years"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calculate_simple_interest",
                "description": "Simple interest; rate as decimal.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "principal": {"type": "number"},
                        "rate": {"type": "number"},
                        "years": {"type": "number"},
                    },
                    "required": ["principal", "rate", "years"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calculate_cd_maturity_value",
                "description": "Estimate CD value at maturity; rate_apr as percent.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "principal": {"type": "number"},
                        "rate_apr": {"type": "number"},
                        "term_months": {"type": "integer"},
                    },
                    "required": ["principal", "rate_apr", "term_months"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compare_after_tax_yield",
                "description": "Approximate after-tax interest; tax rates as decimals.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "principal": {"type": "number"},
                        "rate_apr": {"type": "number"},
                        "years": {"type": "number"},
                        "federal_marginal_rate": {"type": "number"},
                        "state_rate": {"type": "number"},
                    },
                    "required": ["principal", "rate_apr", "years", "federal_marginal_rate"],
                },
            },
        },
    ]


def _serialize_position_row(conn: Any, row: tuple) -> dict[str, Any]:
    pos_id, account_id, asset_type, desc, principal, rate, maturity, doc_id = row[:8]
    acc = get_account(conn, account_id)
    acc_name = acc[1] if acc else account_id
    institution = acc[3] if acc and len(acc) > 3 else None
    start_date = row[10] if len(row) > 10 else None
    next_action = row[11] if len(row) > 11 else None
    liquidity_note = row[12] if len(row) > 12 else None
    return {
        "id": pos_id,
        "account_id": account_id,
        "account_name": acc_name,
        "institution": institution,
        "asset_type": asset_type,
        "description": desc,
        "principal": principal,
        "rate_apr": rate,
        "maturity_date": maturity,
        "document_id": doc_id,
        "start_date": start_date,
        "next_action": next_action,
        "liquidity_note": liquidity_note,
    }


def _tool_get_positions(conn: Any, args: dict[str, Any]) -> dict[str, Any]:
    days = args.get("maturity_within_days")
    asset_kw = (args.get("asset_type_keyword") or "").lower()
    keyword = (args.get("keyword") or "").lower()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=int(days)) if days is not None else None
    out: list[dict[str, Any]] = []
    for row in list_positions(conn):
        item = _serialize_position_row(conn, row)
        if asset_kw and asset_kw not in (item.get("asset_type") or "").lower():
            continue
        if keyword:
            hay = " ".join(
                str(x or "")
                for x in (
                    item.get("description"),
                    item.get("asset_type"),
                    item.get("account_name"),
                    item.get("institution"),
                )
            ).lower()
            if keyword not in hay:
                continue
        if cutoff is not None:
            d = _parse_date(item.get("maturity_date"))
            if d is None or d > cutoff:
                continue
        out.append(item)
    return {"positions": out, "count": len(out)}


def _tool_get_obligations(conn: Any, args: dict[str, Any]) -> dict[str, Any]:
    days = args.get("due_within_days")
    keyword = (args.get("keyword") or "").lower()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=int(days)) if days is not None else None
    out: list[dict[str, Any]] = []
    for row in list_obligations(conn):
        obl_id, desc, due_date, amount, priority, doc_id, _resolved = row[:7]
        if keyword and keyword not in (desc or "").lower():
            continue
        if cutoff is not None:
            d = _parse_date(due_date)
            if d is None or d > cutoff:
                continue
        out.append(
            {
                "id": obl_id,
                "description": desc,
                "due_date": due_date,
                "amount_estimate": amount,
                "priority": priority,
                "document_id": doc_id,
            }
        )
    return {"obligations": out, "count": len(out)}


def _tool_get_accounts(conn: Any, _args: dict[str, Any]) -> dict[str, Any]:
    accounts = []
    for acc_id, name, acc_type, institution, *_ in list_accounts(conn):
        accounts.append(
            {"id": acc_id, "name": name, "account_type": acc_type, "institution": institution}
        )
    return {"accounts": accounts, "count": len(accounts)}


def _tool_get_ira_overview(conn: Any, _args: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in list_ira_overview(conn):
        (
            rid,
            account_name,
            institution,
            account_type,
            balance,
            rmd_note,
            next_date,
            doc_id,
            *_,
        ) = row
        rows.append(
            {
                "id": rid,
                "account_name": account_name,
                "institution": institution,
                "account_type": account_type,
                "balance_estimate": balance,
                "rmd_note": rmd_note,
                "next_relevant_date": next_date,
                "document_id": doc_id,
            }
        )
    return {"ira_overview": rows, "count": len(rows)}


def _tool_evaluate_triggers(conn: Any, _args: dict[str, Any]) -> dict[str, Any]:
    triggers = evaluate_triggers(conn, persist=False)
    items = []
    for tid, ttype, etype, eid, event_date, evaluated_at, status in triggers:
        label = f"{ttype} ({etype})"
        if etype == "position":
            pos = get_position(conn, eid)
            if pos:
                item = _serialize_position_row(conn, pos)
                label = f"CD maturity: {item.get('asset_type')} at {item.get('account_name')}, {event_date}"
        elif etype == "obligation":
            for row in list_obligations(conn):
                if row[0] == eid:
                    label = f"Obligation due: {row[1]} on {event_date}"
                    break
        items.append(
            {
                "id": tid,
                "trigger_type": ttype,
                "entity_type": etype,
                "entity_id": eid,
                "event_date": event_date,
                "status": status,
                "label": label,
            }
        )
    return {
        "triggers": items,
        "count": len(items),
        "no_action_required": len(items) == 0,
        "windows_days": {
            "maturity": MATURITY_DAYS_AHEAD,
            "obligation": OBLIGATION_DAYS_AHEAD,
        },
    }


def _resolve_position_for_liquidity(conn: Any, args: dict[str, Any]) -> tuple[str, str | None, float | None] | None:
    position_id = args.get("position_id")
    if position_id:
        pos = get_position(conn, position_id)
        if not pos:
            return None
        item = _serialize_position_row(conn, pos)
        return position_id, item.get("maturity_date"), item.get("principal")
    maturity_date = args.get("maturity_date")
    if maturity_date:
        for row in list_positions(conn):
            item = _serialize_position_row(conn, row)
            if item.get("maturity_date") == maturity_date:
                return item["id"], maturity_date, item.get("principal")
        return ("", maturity_date, None)
    triggers = evaluate_triggers(conn, persist=False)
    for _tid, ttype, etype, eid, event_date, *_ in triggers:
        if ttype == "maturity" and etype == "position":
            pos = get_position(conn, eid)
            if pos:
                item = _serialize_position_row(conn, pos)
                return eid, event_date or item.get("maturity_date"), item.get("principal")
    positions = list_positions(conn)
    if positions:
        item = _serialize_position_row(conn, positions[0])
        return item["id"], item.get("maturity_date"), item.get("principal")
    return None


def _tool_liquidity_cross_check(conn: Any, args: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_position_for_liquidity(conn, args)
    if not resolved:
        return {"error": "No position found for liquidity cross-check"}
    position_id, maturity_date, principal = resolved
    if not position_id and not maturity_date:
        return {"error": "No position found for liquidity cross-check"}
    result = liquidity_cross_check(conn, position_id or "", maturity_date, principal)
    result["position_id"] = position_id or None
    result["crosscheck_window_days"] = LIQUIDITY_CROSSCHECK_DAYS
    return result


def _tool_get_dashboard_snapshot(conn: Any, args: dict[str, Any]) -> dict[str, Any]:
    days = int(args.get("days") or 90)
    days = max(1, min(days, 3650))
    return build_dashboard(conn, days=days)


async def _local_rate_infos(conn: Any) -> list[RateInfo]:
    from app.reference_data import fetch_cd_rates_with_cache

    return await fetch_cd_rates_with_cache(conn, include_external=False)


def _tool_get_cd_benchmark_rates(_conn: Any, _args: dict[str, Any]) -> dict[str, Any]:
    infos = fetch_cd_rates_local()
    cds = [
        {
            "term_months": r.term_months,
            "rate_apr": r.rate_apr,
            "quote": r.quote,
            "source_name": r.source_name,
        }
        for r in infos
        if r.product_type == "cd"
    ]
    return {"benchmarks": cds, "source": "local_curated"}


def _tool_get_mmf_benchmark(_conn: Any, _args: dict[str, Any]) -> dict[str, Any]:
    infos = fetch_cd_rates_local()
    mmf = mmf_benchmark(infos)
    if not mmf:
        return {"error": "MMF benchmark unavailable"}
    return {
        "rate_apr": mmf.rate_apr,
        "quote": mmf.quote,
        "source_name": mmf.source_name,
        "source": "local_curated",
    }


def _tool_compare_user_rate(_conn: Any, args: dict[str, Any]) -> dict[str, Any]:
    user_rate = args.get("user_rate_apr")
    if user_rate is None:
        return {"error": "user_rate_apr required"}
    term_months = args.get("term_months")
    infos = fetch_cd_rates_local()
    bench = closest_cd_benchmark(infos, int(term_months) if term_months is not None else None)
    return compare_user_rate(float(user_rate), bench)


async def _tool_compare_roll_options(conn: Any, args: dict[str, Any]) -> dict[str, Any]:
    position_id = args.get("position_id")
    if not position_id:
        triggers = evaluate_triggers(conn, persist=False)
        for _tid, ttype, etype, eid, event_date, *_ in triggers:
            if ttype == "maturity" and etype == "position":
                position_id = eid
                break
        if not position_id:
            positions = list_positions(conn)
            if positions:
                position_id = positions[0][0]
    if not position_id:
        return {"error": "No position available for roll comparison"}
    pos = get_position(conn, position_id)
    if not pos:
        return {"error": f"Position {position_id} not found"}
    item = _serialize_position_row(conn, pos)
    rate_infos = await _local_rate_infos(conn)
    section = build_maturity_memo_sections(
        conn, position_id, item.get("maturity_date"), rate_infos
    )
    if not section:
        return {"error": "Could not build roll options"}
    return {"position_id": position_id, **section}


async def _tool_search_documents(
    conn: Any,
    args: dict[str, Any],
    *,
    ask_request: AskRequest | None,
) -> dict[str, Any]:
    from app.ask_conversation import resolve_doc_scope
    from app import embeddings_client
    from app.retrieval import retrieve_top_k

    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query required"}
    top_k = int(args.get("top_k") or 5)
    scoped = resolve_doc_scope(conn, ask_request or AskRequest(question=query, top_k=top_k))
    query_vec = await embeddings_client.embed_text(query)
    chunks = await retrieve_top_k(
        conn,
        query_vec,
        top_k,
        doc_id=scoped.doc_id,
        doc_ids=scoped.doc_ids,
        tag=scoped.tag,
        question=query,
    )
    return {
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "doc_id": c.doc_id,
                "score": c.score,
                "content_snippet": c.content_snippet,
            }
            for c in chunks
        ],
        "count": len(chunks),
    }


def _tool_get_document_metadata(conn: Any, args: dict[str, Any]) -> dict[str, Any]:
    doc_id = args.get("doc_id")
    if doc_id:
        for row in list_documents(conn):
            if row[0] == doc_id:
                tags = get_document_tags(conn, doc_id)
                return {
                    "doc_id": row[0],
                    "title": row[1],
                    "source": row[2],
                    "created_at": row[3],
                    "num_chunks": row[4],
                    "snippet": (row[5] or "")[:250] if len(row) > 5 else None,
                    "tags": tags,
                }
        return {"error": f"Document {doc_id} not found"}
    docs = []
    for row in list_documents(conn):
        did = row[0]
        docs.append(
            {
                "doc_id": did,
                "title": row[1],
                "source": row[2],
                "created_at": row[3],
                "num_chunks": row[4],
                "tags": get_document_tags(conn, did),
            }
        )
    return {"documents": docs, "count": len(docs)}


async def _tool_get_decision_memo(conn: Any, _args: dict[str, Any]) -> dict[str, Any]:
    triggers = evaluate_triggers(conn, persist=False)
    rate_infos = await _local_rate_infos(conn)
    sections: list[dict[str, Any]] = []
    for t in triggers:
        if t[1] != "maturity" or t[2] != "position":
            continue
        section = build_maturity_memo_sections(conn, t[3], t[4], rate_infos)
        if section:
            sections.append(section)
    if not triggers:
        return {
            "status": "no_action_required",
            "memo": build_no_action_memo(conn),
            "sections": [],
        }
    return {
        "status": "actionable" if triggers else "no_action_required",
        "memo": build_action_summary_memo(len(triggers), sections) if sections else build_no_action_memo(conn),
        "memo_markdown": format_operational_memo(sections),
        "sections": sections,
        "trigger_count": len(triggers),
    }


def _tool_get_decision_history(conn: Any, args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 10)
    limit = max(1, min(limit, 50))
    rows = list_decision_history(conn, limit=limit)
    items = [
        {
            "id": r[0],
            "evaluated_at": r[1],
            "status": r[2],
            "memo": r[3],
            "trigger_ids": r[4],
        }
        for r in rows
    ]
    return {"history": items, "count": len(items)}


_SYNC_EXECUTORS: dict[str, Callable[[Any, dict[str, Any]], dict[str, Any]]] = {
    "get_positions": _tool_get_positions,
    "get_obligations": _tool_get_obligations,
    "get_accounts": _tool_get_accounts,
    "get_ira_overview": _tool_get_ira_overview,
    "evaluate_triggers": _tool_evaluate_triggers,
    "liquidity_cross_check": _tool_liquidity_cross_check,
    "get_dashboard_snapshot": _tool_get_dashboard_snapshot,
    "get_cd_benchmark_rates": _tool_get_cd_benchmark_rates,
    "get_mmf_benchmark": _tool_get_mmf_benchmark,
    "compare_user_rate": _tool_compare_user_rate,
    "get_document_metadata": _tool_get_document_metadata,
    "get_decision_history": _tool_get_decision_history,
    "calculate_compound_interest": lambda _c, a: calculate_compound_interest(
        float(a["principal"]), float(a["rate"]), int(a["years"])
    ),
    "calculate_simple_interest": lambda _c, a: calculate_simple_interest(
        float(a["principal"]), float(a["rate"]), float(a["years"])
    ),
    "calculate_cd_maturity_value": lambda _c, a: calculate_cd_maturity_value(
        float(a["principal"]), float(a["rate_apr"]), int(a["term_months"])
    ),
    "compare_after_tax_yield": lambda _c, a: compare_after_tax_yield(
        float(a["principal"]),
        float(a["rate_apr"]),
        float(a["years"]),
        float(a["federal_marginal_rate"]),
        state_rate=float(a.get("state_rate") or 0),
    ),
}

_ASYNC_EXECUTORS = {
    "compare_roll_options": _tool_compare_roll_options,
    "search_documents": _tool_search_documents,
    "get_decision_memo": _tool_get_decision_memo,
}


async def execute_tool(
    conn: Any,
    name: str,
    args: dict[str, Any] | None = None,
    *,
    ask_request: AskRequest | None = None,
) -> dict[str, Any]:
    """Run a named local tool; returns JSON-serializable dict."""
    args = args or {}
    if name in _SYNC_EXECUTORS:
        try:
            return _SYNC_EXECUTORS[name](conn, args)
        except (KeyError, TypeError, ValueError) as e:
            return {"error": str(e)}
    if name in _ASYNC_EXECUTORS:
        try:
            fn = _ASYNC_EXECUTORS[name]
            if name == "search_documents":
                return await fn(conn, args, ask_request=ask_request)
            return await fn(conn, args)
        except (KeyError, TypeError, ValueError) as e:
            return {"error": str(e)}
    return {"error": f"Unknown tool: {name}"}


def format_tool_results(results: list[dict[str, Any]]) -> str:
    """Compact block for LLM prompt injection."""
    if not results:
        return ""
    lines = [
        "Tool results (authoritative local data — prefer over guessing; do not invent numbers):",
    ]
    for item in results:
        name = item.get("tool", "?")
        payload = item.get("result", {})
        try:
            body = json.dumps(payload, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            body = str(payload)
        if len(body) > 4000:
            body = body[:4000] + "…"
        lines.append(f"[{name}] {body}")
    return "\n".join(lines)
