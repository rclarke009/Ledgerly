"""Heuristic tool selection and execution for Ask (no external calls)."""

from __future__ import annotations

import re
from typing import Any

from app.ask_tools import execute_tool, format_tool_results
from app.ask_trace import log_ask_event
from app.config import ASK_TOOLS_ENABLED, ASK_TOOLS_MAX_PER_QUESTION
from app.models import AskRequest

Route = str

# (tool_name, default_args)
_TOOL_PATTERNS: list[tuple[str, dict[str, Any], tuple[str, ...]]] = [
    (
        "get_positions",
        {"maturity_within_days": 90},
        (r"\bmatur", r"\bcd\b", r"\bbiggest", r"\bposition", r"\bladder", r"\brung"),
    ),
    (
        "get_obligations",
        {"due_within_days": 30},
        (r"\bbill", r"\bobligation", r"\bdue", r"\bmortgage", r"\bpayment"),
    ),
    ("get_accounts", {}, (r"\baccount", r"\bholding")),
    ("get_ira_overview", {}, (r"\bira\b", r"\brmd\b")),
    (
        "evaluate_triggers",
        {},
        (r"\btrigger", r"\bdecision", r"\baction required", r"\battention", r"\bnext decision"),
    ),
    (
        "liquidity_cross_check",
        {},
        (r"\bliquid", r"\bcover", r"\bobligation", r"\bbill", r"\bmatur", r"\brung"),
    ),
    (
        "get_dashboard_snapshot",
        {"days": 90},
        (r"\bstatus", r"\boverview", r"\bsummarize", r"\bhome\b", r"\btotal"),
    ),
    (
        "get_cd_benchmark_rates",
        {},
        (r"\bbenchmark", r"\bmarket rate", r"\bcurrent rate", r"\bapy", r"\byield", r"\broll", r"\brenew"),
    ),
    ("get_mmf_benchmark", {}, (r"\bmmf\b", r"\bmoney market", r"\bvmfxx")),
    (
        "compare_roll_options",
        {},
        (r"\broll", r"\brenew", r"\boptions at maturity", r"\bwhat should i do", r"\bhold or", r"\bmmf"),
    ),
    (
        "search_documents",
        {},
        (r"\bdocument", r"\bletter", r"\bfind\b", r"\b1099", r"\bstatement", r"\bwhat does", r"\bw-?2"),
    ),
    (
        "get_document_metadata",
        {},
        (r"\bingested", r"\bwhich document", r"\blist document", r"\buploaded"),
    ),
    (
        "get_decision_memo",
        {},
        (r"\bdecision memo", r"\brecommend", r"\bwhat should i do", r"\btrigger"),
    ),
    (
        "get_decision_history",
        {},
        (r"\bpast advice", r"\bprevious recommendation", r"\bdecision history"),
    ),
    (
        "calculate_compound_interest",
        {},
        (r"\bcompound interest", r"\bgrow to", r"\bprojection"),
    ),
    (
        "calculate_simple_interest",
        {},
        (r"\bsimple interest", r"\bannual interest", r"\b1[- ]year cd", r"\binterest earned"),
    ),
    (
        "calculate_cd_maturity_value",
        {},
        (r"\bmaturity value", r"\bworth at maturity", r"\bat maturity"),
    ),
    (
        "compare_after_tax_yield",
        {},
        (r"\bafter.?tax", r"\btax.*interest", r"\bflorida", r"\bstate tax"),
    ),
]


def _normalize(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower())


def _parse_money(text: str) -> float | None:
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)\s*k?\b", text, re.I)
    if not m:
        m = re.search(r"\b([\d,]{4,}(?:\.\d+)?)\s*dollars?\b", text, re.I)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        val = float(raw)
        if re.search(r"\bk\b", text[m.start() : m.end() + 2], re.I):
            val *= 1000
        return val
    except ValueError:
        return None


def _parse_rate_percent(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*percent", text, re.I)
    return float(m.group(1)) if m else None


def _parse_years(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*[- ]?\s*years?", text, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+)\s*months?", text, re.I)
    if m:
        return float(m.group(1)) / 12.0
    return None


def _enrich_tool_args(question: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """Fill calculation args from question text; return None to skip tool if required fields missing."""
    q = question
    if tool_name == "calculate_compound_interest":
        principal = args.get("principal") or _parse_money(q)
        rate_pct = _parse_rate_percent(q)
        years = args.get("years") or _parse_years(q)
        if principal is None or rate_pct is None or years is None:
            return None
        return {
            "principal": principal,
            "rate": rate_pct / 100.0,
            "years": int(round(years)),
        }
    if tool_name == "calculate_simple_interest":
        principal = args.get("principal") or _parse_money(q)
        rate_pct = _parse_rate_percent(q)
        years = args.get("years") or _parse_years(q)
        if principal is None or rate_pct is None or years is None:
            return None
        return {"principal": principal, "rate": rate_pct / 100.0, "years": years}
    if tool_name == "calculate_cd_maturity_value":
        principal = args.get("principal") or _parse_money(q)
        rate_pct = args.get("rate_apr") or _parse_rate_percent(q)
        term = args.get("term_months")
        if term is None:
            ym = re.search(r"(\d+)\s*months?", q, re.I)
            term = int(ym.group(1)) if ym else None
        if principal is None or rate_pct is None or term is None:
            return None
        return {"principal": principal, "rate_apr": rate_pct, "term_months": int(term)}
    if tool_name == "compare_after_tax_yield":
        principal = args.get("principal") or _parse_money(q)
        rate_pct = args.get("rate_apr") or _parse_rate_percent(q)
        years = args.get("years") or _parse_years(q) or 1.0
        federal = args.get("federal_marginal_rate")
        if federal is None:
            federal = 0.22
        state = args.get("state_rate") or 0.0
        if re.search(r"\bflorida\b", q, re.I):
            state = 0.0
        if principal is None or rate_pct is None:
            return None
        return {
            "principal": principal,
            "rate_apr": rate_pct,
            "years": years,
            "federal_marginal_rate": federal,
            "state_rate": state,
        }
    if tool_name == "compare_user_rate":
        rate_pct = args.get("user_rate_apr") or _parse_rate_percent(q)
        if rate_pct is None:
            return None
        out = {"user_rate_apr": rate_pct}
        if args.get("term_months") is not None:
            out["term_months"] = args["term_months"]
        return out
    return args


def select_tools_for_question(
    question: str,
    route: Route,
    *,
    ask_request: AskRequest | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Return ordered (tool_name, args) to run; all local-only."""
    if not ASK_TOOLS_ENABLED:
        return []

    q = _normalize(question)
    selected: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()

    def add(name: str, args: dict[str, Any] | None = None) -> None:
        if name in seen or len(selected) >= ASK_TOOLS_MAX_PER_QUESTION:
            return
        seen.add(name)
        selected.append((name, dict(args or {})))

    for tool_name, default_args, patterns in _TOOL_PATTERNS:
        if any(re.search(p, q) for p in patterns):
            add(tool_name, default_args)

    if route == "rag_only" and "search_documents" not in seen:
        add("search_documents", {"query": question, "top_k": ask_request.top_k if ask_request else 5})

    if route == "structured_data" and not selected:
        add("get_dashboard_snapshot", {"days": 90})

    if route in ("rag", "structured_data") and "get_positions" not in seen:
        if re.search(r"\bhow much\b|\bcd\b|\bholding", q):
            add("get_positions", {})

    if "search_documents" in seen:
        for i, (n, a) in enumerate(selected):
            if n == "search_documents":
                merged = dict(a)
                if "query" not in merged:
                    merged["query"] = question
                if ask_request and "top_k" not in merged:
                    merged["top_k"] = ask_request.top_k
                selected[i] = (n, merged)
                break

    enriched: list[tuple[str, dict[str, Any]]] = []
    for name, args in selected:
        filled = _enrich_tool_args(question, name, args)
        if filled is None and (
            name.startswith("calculate_")
            or name in ("compare_after_tax_yield", "compare_user_rate")
        ):
            continue
        if filled is None:
            filled = args
        enriched.append((name, filled))
    return enriched


async def run_ask_tools(
    conn: Any,
    question: str,
    route: Route,
    *,
    ask_request: AskRequest | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Execute selected tools and return (prompt block, raw results)."""
    tools = select_tools_for_question(question, route, ask_request=ask_request)
    if not tools:
        log_ask_event("ask_tools", skipped=True, reason="no_match")
        return "", []

    results: list[dict[str, Any]] = []
    for name, args in tools:
        result = await execute_tool(conn, name, args, ask_request=ask_request)
        results.append({"tool": name, "args": args, "result": result})

    block = format_tool_results(results)
    log_ask_event(
        "ask_tools",
        tools=[t[0] for t in tools],
        result_chars=len(block),
    )
    return block, results


def tool_results_have_data(results: list[dict[str, Any]]) -> bool:
    """True if any tool returned non-empty, non-error payload."""
    for item in results:
        payload = item.get("result") or {}
        if isinstance(payload, dict) and payload.get("error"):
            continue
        if payload:
            return True
    return False
