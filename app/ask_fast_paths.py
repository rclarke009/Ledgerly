"""Deterministic Ask answers for preset questions (no LLM)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.config import MATURITY_DAYS_AHEAD, OBLIGATION_DAYS_AHEAD, IRA_DAYS_AHEAD
from app.dashboard import build_dashboard
from app.db import get_account, list_accounts, list_obligations, list_positions
from app.triggers import evaluate_triggers, _parse_date

FastPathKind = Literal[
    "maturing_soon",
    "cd_totals",
    "obligations_soon",
    "accounts_summary",
    "next_trigger",
]

PRESET_QUESTIONS: dict[str, FastPathKind] = {
    "what's maturing in the next 3 months?": "maturing_soon",
    "how much do i have in cds?": "cd_totals",
    "what bills or obligations are due soon?": "obligations_soon",
    "summarize my accounts and holdings.": "accounts_summary",
    "what is my next decision trigger?": "next_trigger",
}


def normalize_question(question: str) -> str:
    q = (question or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q


def detect_fast_path_kind(question: str) -> FastPathKind | None:
    return PRESET_QUESTIONS.get(normalize_question(question))


def try_fast_path_answer(conn: Any, question: str) -> str | None:
    mortgage = _answer_mortgage_payment(conn, question)
    if mortgage is not None:
        return mortgage
    kind = detect_fast_path_kind(question)
    if kind is None:
        return None
    if kind == "maturing_soon":
        return _answer_maturing_soon(conn)
    if kind == "cd_totals":
        return _answer_cd_totals(conn)
    if kind == "obligations_soon":
        return _answer_obligations_soon(conn)
    if kind == "accounts_summary":
        return _answer_accounts_summary(conn)
    if kind == "next_trigger":
        return _answer_next_trigger(conn)
    return None


def _answer_next_trigger(conn: Any) -> str:
    triggers = evaluate_triggers(conn, persist=False)
    if not triggers:
        days = max(MATURITY_DAYS_AHEAD, OBLIGATION_DAYS_AHEAD, IRA_DAYS_AHEAD)
        return f"No decision triggers in the next {days} days. Status: no action required."
    lines = ["**Next decision triggers:**", ""]
    for tid, ttype, etype, eid, event_date, _eval, _status in triggers[:8]:
        label = f"{ttype} ({etype})"
        if etype == "position":
            pos = list_positions(conn)
            match = next((p for p in pos if p[0] == eid), None)
            if match:
                acc = get_account(conn, match[1])
                inst = acc[3] if acc and acc[3] else (acc[1] if acc else "")
                label = f"CD maturity: {match[2]} at {inst}, matures {event_date}"
        elif etype == "obligation":
            for row in list_obligations(conn):
                if row[0] == eid:
                    label = f"Obligation due: {row[1]} on {event_date}"
                    break
        elif etype == "ira_overview":
            label = f"IRA awareness date: {event_date}"
        lines.append(f"- {label}")
    return "\n".join(lines)


def _format_money(amount: float | None) -> str:
    if amount is None:
        return "—"
    return f"${amount:,.0f}"


def _answer_maturing_soon(conn: Any) -> str:
    data = build_dashboard(conn, days=90)
    overdue = data.get("overdue_maturing") or []
    upcoming = data.get("upcoming_maturing") or []
    next_m = data.get("next_maturity")
    lines = ["## Maturities in the next 3 months", ""]
    if not overdue and not upcoming and not next_m:
        return (
            "## Maturities in the next 3 months\n\n"
            "No tracked CDs or positions with maturity dates in the next 90 days."
        )
    if overdue:
        lines.append("### Overdue")
        for item in overdue:
            lines.append(
                f"- **{item.get('label', 'Position')}** at {item.get('account_name', 'account')} — "
                f"matured {item.get('maturity_date', '?')} ({_format_money(item.get('principal'))})"
            )
        lines.append("")
    if next_m:
        lines.append("### Next up")
        lines.append(
            f"- **{next_m.get('label', 'Position')}** at {next_m.get('account_name', 'account')} — "
            f"{next_m.get('maturity_date', '?')} ({_format_money(next_m.get('principal'))})"
        )
        lines.append("")
    if upcoming:
        lines.append("### Upcoming")
        for item in upcoming[:15]:
            days = item.get("days_until")
            days_txt = f"in {days} days" if days is not None else ""
            lines.append(
                f"- **{item.get('label', 'Position')}** at {item.get('account_name', 'account')} — "
                f"{item.get('maturity_date', '?')} {days_txt} ({_format_money(item.get('principal'))})"
            )
    return "\n".join(lines).strip()


def _is_cd_asset(asset_type: str | None) -> bool:
    if not asset_type:
        return False
    t = asset_type.lower()
    return "cd" in t or "certificate" in t or "time deposit" in t


def _answer_cd_totals(conn: Any) -> str:
    positions = list_positions(conn)
    cd_rows = [r for r in positions if _is_cd_asset(r[2])]
    if not cd_rows:
        return "## CD holdings\n\nNo CD positions tracked yet."
    total = sum(float(r[4]) for r in cd_rows if r[4] is not None)
    lines = ["## CD holdings", "", f"**Total in CDs:** {_format_money(total)}", ""]
    for row in cd_rows:
        pos_id, account_id, asset_type, desc, principal, rate, maturity, *_ = row
        acc = get_account(conn, account_id)
        acc_name = acc[1] if acc else account_id
        label = asset_type + (f" — {desc}" if desc else "")
        rate_txt = f"{rate}% APR" if rate is not None else ""
        mat_txt = f"matures {maturity}" if maturity else ""
        lines.append(
            f"- **{label}** at {acc_name}: {_format_money(principal)}"
            + (f", {rate_txt}" if rate_txt else "")
            + (f", {mat_txt}" if mat_txt else "")
        )
    return "\n".join(lines)


def _is_mortgage_payment_question(question: str) -> bool:
    q = normalize_question(question)
    return bool(
        re.search(r"\bmortgage\b|\bhome\s+loan\b", q)
        and re.search(r"\b(payment|pay|due|amount|cost|total)\b", q)
    )


def _answer_mortgage_payment(conn: Any, question: str) -> str | None:
    if not _is_mortgage_payment_question(question):
        return None
    rows = list_obligations(conn)
    mortgage_rows = [r for r in rows if "mortgage" in (r[1] or "").lower()]
    if not mortgage_rows:
        return None
    lines = ["## Mortgage payment", ""]
    if len(mortgage_rows) == 1:
        _obl_id, desc, due_date, amount, priority, *_rest = mortgage_rows[0]
        lines.append(
            f"Your **{desc}** payment is {_format_money(amount)}, due {due_date or '—'}."
        )
        return "\n".join(lines)
    lines.append("Tracked mortgage obligations:")
    for _obl_id, desc, due_date, amount, priority, *_rest in mortgage_rows:
        lines.append(
            f"- **{desc}** — {_format_money(amount)}, due {due_date or '—'}"
            + (f", priority {priority}" if priority else "")
        )
    return "\n".join(lines)


def _answer_obligations_soon(conn: Any) -> str:
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=OBLIGATION_DAYS_AHEAD)
    rows = list_obligations(conn)
    due_soon: list[tuple] = []
    overdue: list[tuple] = []
    for row in rows:
        d = _parse_date(row[2])
        if not d:
            continue
        if d.date() < now.date():
            overdue.append(row)
        elif d <= cutoff:
            due_soon.append(row)
    lines = [f"## Bills and obligations (next {OBLIGATION_DAYS_AHEAD} days)", ""]
    if not due_soon and not overdue:
        return lines[0] + f"\n\nNo obligations due in the next {OBLIGATION_DAYS_AHEAD} days."
    if overdue:
        lines.append("### Overdue")
        for obl_id, desc, due_date, amount, priority, *_ in overdue:
            lines.append(
                f"- **{desc}** — due {due_date} ({_format_money(amount)})"
                + (f", priority {priority}" if priority else "")
            )
        lines.append("")
    if due_soon:
        lines.append("### Due soon")
        for obl_id, desc, due_date, amount, priority, *_ in due_soon:
            lines.append(
                f"- **{desc}** — due {due_date} ({_format_money(amount)})"
                + (f", priority {priority}" if priority else "")
            )
    return "\n".join(lines)


def _answer_accounts_summary(conn: Any) -> str:
    accounts = list_accounts(conn)
    positions = list_positions(conn)
    if not accounts and not positions:
        return "## Accounts and holdings\n\nNo accounts or positions tracked yet."
    lines = ["## Accounts and holdings", ""]
    for acc_id, name, acc_type, institution, *_ in accounts:
        inst = institution or acc_type or ""
        header = f"### {name}" + (f" ({inst})" if inst else "")
        lines.append(header)
        acc_positions = [p for p in positions if p[1] == acc_id]
        if not acc_positions:
            lines.append("- No positions")
        else:
            for row in acc_positions:
                _pid, _aid, asset_type, desc, principal, rate, maturity, *_ = row
                label = asset_type + (f" — {desc}" if desc else "")
                extra = []
                if principal is not None:
                    extra.append(_format_money(principal))
                if rate is not None:
                    extra.append(f"{rate}%")
                if maturity:
                    extra.append(f"matures {maturity}")
                lines.append(f"- **{label}**" + (": " + ", ".join(extra) if extra else ""))
        lines.append("")
    return "\n".join(lines).strip()
