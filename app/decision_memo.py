"""Operational decision memos: triggers, liquidity cross-check, rate comparison, guardrails."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import LIQUIDITY_CROSSCHECK_DAYS, MATURITY_DAYS_AHEAD, OBLIGATION_DAYS_AHEAD
from app.db import get_account, get_obligation, get_position, list_obligations
from app.reference_data import (
    RateInfo,
    closest_cd_benchmark,
    compare_user_rate,
    mmf_benchmark,
)
from app.triggers import _parse_date


def _format_money(amount: float | None) -> str:
    if amount is None:
        return "unknown amount"
    return f"${amount:,.0f}"


def obligations_near_date(
    conn: Any,
    event_date: str | None,
    *,
    window_days: int | None = None,
) -> list[dict[str, Any]]:
    """Obligations due within ±window_days of event_date."""
    days = window_days if window_days is not None else LIQUIDITY_CROSSCHECK_DAYS
    center = _parse_date(event_date)
    if center is None:
        return []
    start = center - timedelta(days=days)
    end = center + timedelta(days=days)
    out: list[dict[str, Any]] = []
    for row in list_obligations(conn):
        obl_id, description, due_date, amount_estimate, priority, doc_id, _resolved = row
        d = _parse_date(due_date)
        if d is None:
            continue
        if start.date() <= d.date() <= end.date():
            out.append(
                {
                    "id": obl_id,
                    "description": description,
                    "due_date": due_date,
                    "amount_estimate": amount_estimate,
                    "priority": priority,
                    "document_id": doc_id,
                    "days_from_event": (d.date() - center.date()).days,
                }
            )
    out.sort(key=lambda x: x["due_date"])
    return out


def liquidity_cross_check(
    conn: Any,
    position_id: str,
    maturity_date: str | None,
    principal: float | None,
) -> dict[str, Any]:
    """Check whether maturing principal likely covers nearby obligations."""
    nearby = obligations_near_date(conn, maturity_date)
    total_obligations = sum(o["amount_estimate"] or 0 for o in nearby)
    principal_val = principal or 0
    if not nearby:
        return {
            "nearby_obligations": [],
            "total_obligation_estimate": 0,
            "maturing_principal": principal,
            "covers_obligations": None,
            "summary": "No known cash obligations within the cross-check window.",
            "needs_liquid": False,
        }
    covers = principal_val >= total_obligations if total_obligations > 0 else True
    if total_obligations > 0 and not covers:
        summary = (
            f"Maturing {_format_money(principal)} may not cover "
            f"{_format_money(total_obligations)} in nearby obligations — consider keeping funds liquid or splitting."
        )
        needs_liquid = True
    elif total_obligations > 0:
        summary = (
            f"Maturing {_format_money(principal)} likely covers "
            f"{_format_money(total_obligations)} in nearby obligations."
        )
        needs_liquid = False
    else:
        summary = "Nearby obligations have no amount estimates — verify manually."
        needs_liquid = len(nearby) > 0
    return {
        "nearby_obligations": nearby,
        "total_obligation_estimate": total_obligations,
        "maturing_principal": principal,
        "covers_obligations": covers,
        "summary": summary,
        "needs_liquid": needs_liquid,
    }


def _infer_term_months(maturity_date: str | None) -> int | None:
    """Rough term hint from days until maturity (for benchmark pick)."""
    d = _parse_date(maturity_date)
    if d is None:
        return None
    now = datetime.now(timezone.utc)
    days = (d.date() - now.date()).days
    if days <= 0:
        return 6
    if days <= 120:
        return 3
    if days <= 240:
        return 6
    if days <= 450:
        return 12
    return 24


def action_threshold_met(
    *,
    rate_comparison: dict[str, Any],
    liquidity: dict[str, Any],
    maturing_soon: bool,
) -> tuple[bool, str]:
    """
    Recommend switching only when at least one threshold is true.
    Returns (recommend_action, reason).
    """
    reasons: list[str] = []
    if maturing_soon:
        reasons.append("CD maturing within decision window")
    if liquidity.get("needs_liquid"):
        reasons.append("Known cash obligation may require liquid funds")
    if rate_comparison.get("meaningful") and (rate_comparison.get("delta") or 0) > 0:
        reasons.append("Benchmark suggests materially higher yield available")
    if not reasons:
        return False, "No action threshold met — prefer hold/renew/wait unless you have new information."
    return True, "; ".join(reasons)


def build_maturity_memo_sections(
    conn: Any,
    position_id: str,
    event_date: str | None,
    rate_infos: list[RateInfo],
) -> dict[str, Any]:
    """Build structured sections for one maturity trigger."""
    pos = get_position(conn, position_id)
    if not pos:
        return {}
    (
        _pid,
        account_id,
        asset_type,
        desc,
        principal,
        rate_apr,
        maturity_date,
        _doc_id,
        _created,
        _updated,
        start_date,
        next_action,
        liquidity_note,
    ) = _unpack_position(pos)
    acc = get_account(conn, account_id)
    institution = acc[3] if acc and acc[3] else (acc[1] if acc else None)
    label = asset_type + (f" {desc}" if desc else "")
    term = _infer_term_months(maturity_date)
    bench = closest_cd_benchmark(rate_infos, term)
    mmf = mmf_benchmark(rate_infos)
    rate_cmp = compare_user_rate(rate_apr, bench)
    mmf_cmp = compare_user_rate(rate_apr, mmf) if mmf else {"summary": "MMF benchmark unavailable."}
    liquidity = liquidity_cross_check(conn, position_id, event_date or maturity_date, principal)
    threshold_met, threshold_reason = action_threshold_met(
        rate_comparison=rate_cmp,
        liquidity=liquidity,
        maturing_soon=True,
    )

    options = [
        "Hold / renew at same institution (simplest if rate is competitive)",
        "Roll to new CD term (if benchmark yield advantage is meaningful)",
        "Move to money market fund (if liquidity needed soon)",
        "Wait / no change yet (if outside final decision window)",
    ]
    if liquidity.get("needs_liquid"):
        recommendation = "Keep proceeds liquid (MMF or checking) until nearby obligations are covered."
    elif not threshold_met:
        recommendation = "No urgent switch — renew or hold unless institution offer is clearly worse."
    elif rate_cmp.get("meaningful") and (rate_cmp.get("delta") or 0) > 0:
        recommendation = "Compare institution renewal rate vs benchmark; roll only if net yield after effort is worth it."
    else:
        recommendation = "Renew or hold — your rate is competitive vs benchmarks."

    known = [
        f"Holding: {label} at {institution or 'unknown institution'}",
        f"Principal: {_format_money(principal)}",
        f"Rate: {rate_apr}%" if rate_apr is not None else "Rate: unknown",
        f"Maturity: {maturity_date or event_date or 'unknown'}",
    ]
    if start_date:
        known.append(f"Start date: {start_date}")
    if liquidity_note:
        known.append(f"Liquidity note: {liquidity_note}")
    if next_action:
        known.append(f"Planned next action: {next_action}")

    assumed = ["Taxable account unless documents indicate otherwise", "Benchmark rates are generic, not institution-specific"]
    missing: list[str] = []
    if rate_apr is None:
        missing.append("Current CD rate on position")
    if principal is None:
        missing.append("Principal amount")
    missing.append("Institution renewal offer (check statement or call bank)")

    provisional = bool(missing) or not rate_cmp.get("benchmark_rate")

    return {
        "trigger": f"CD maturity approaching ({maturity_date or event_date})",
        "relevant_holdings": known,
        "liquidity": liquidity,
        "rate_comparison": rate_cmp,
        "mmf_comparison": mmf_cmp,
        "options": options,
        "comparison_axes": {
            "safety": "CDs and MMFs are both capital-preservation options; verify FDIC/SIPC coverage for your product.",
            "income": rate_cmp.get("summary", ""),
            "liquidity": liquidity.get("summary", ""),
            "simplicity": "Auto-renew is simplest; moving funds adds steps.",
            "tax": "Taxable CD interest is ordinary income; confirm with tax advisor if needed.",
        },
        "recommendation": recommendation,
        "action_threshold_met": threshold_met,
        "action_threshold_reason": threshold_reason,
        "next_dates": {
            "maturity": maturity_date or event_date,
            "decision_window_days": MATURITY_DAYS_AHEAD,
        },
        "confidence": {
            "known": known,
            "assumed": assumed,
            "missing": missing,
            "status": "provisional" if provisional else "final",
        },
    }


def _unpack_position(row: tuple) -> tuple:
    """Normalize position row with optional ladder columns."""
    base = list(row[:10])
    while len(base) < 10:
        base.append(None)
    start_date = row[10] if len(row) > 10 else None
    next_action = row[11] if len(row) > 11 else None
    liquidity_note = row[12] if len(row) > 12 else None
    return tuple(base + [start_date, next_action, liquidity_note])


def format_operational_memo(sections: list[dict[str, Any]]) -> str:
    """Render structured sections as markdown memo text."""
    if not sections:
        return ""
    parts: list[str] = []
    for i, sec in enumerate(sections, 1):
        parts.append(f"### Decision {i}: {sec.get('trigger', 'Review')}")
        parts.append(f"**Recommendation:** {sec.get('recommendation', 'Review options')}")
        parts.append(f"**Action threshold:** {sec.get('action_threshold_reason', '')}")
        if sec.get("rate_comparison", {}).get("summary"):
            parts.append(f"**Rate comparison:** {sec['rate_comparison']['summary']}")
        liq = sec.get("liquidity") or {}
        if liq.get("summary"):
            parts.append(f"**Liquidity:** {liq['summary']}")
        opts = sec.get("options") or []
        if opts:
            parts.append("**Options:**")
            for j, opt in enumerate(opts, 1):
                parts.append(f"{j}. {opt}")
        conf = sec.get("confidence") or {}
        parts.append(f"**Confidence:** {conf.get('status', 'provisional')}")
        if conf.get("missing"):
            parts.append("**Missing data:** " + "; ".join(conf["missing"]))
        parts.append("")
    return "\n".join(parts).strip()


def build_openai_maturity_prompt(section: dict[str, Any]) -> str:
    """Sanitized OpenAI prompt for operational memo (no PII)."""
    rate = section.get("rate_comparison", {})
    liq = section.get("liquidity", {})
    principal = "a CD"
    user_rate = rate.get("user_rate")
    bench = rate.get("benchmark_rate")
    prompt = (
        "You are a conservative cash-management assistant. No account names or institutions.\n"
        f"Situation: {principal} maturing soon. "
        f"Current rate: {user_rate}% if known. Benchmark: ~{bench}% if known.\n"
        f"Liquidity note: {liq.get('summary', 'none')}.\n"
        f"Action threshold met: {section.get('action_threshold_met')}. "
        f"Reason: {section.get('action_threshold_reason', '')}.\n"
        "Output exactly these labeled lines (short, operational):\n"
        "Trigger: ...\n"
        "Options: (1) hold/renew (2) roll CD (3) MMF (4) wait\n"
        "Comparison: safety / income / liquidity / simplicity in one line\n"
        "Recommendation: one simplest action\n"
        "Next dates: maturity window only\n"
        "Confidence: known / assumed / missing / provisional-or-final\n"
        "Do not recommend switching unless action threshold is met."
    )
    return prompt


def build_no_action_memo(_conn: Any | None = None) -> str:
    days = max(MATURITY_DAYS_AHEAD, OBLIGATION_DAYS_AHEAD)
    return (
        f"No action required. No CDs maturing and no obligations due in the next {days} days. "
        "Status: monitor only."
    )


def build_action_summary_memo(trigger_count: int, sections: list[dict[str, Any]]) -> str:
    if sections:
        return format_operational_memo(sections)
    return (
        f"You have {trigger_count} item(s) needing attention. "
        "Review maturity and obligation dates; consider renewing or reallocating."
    )
