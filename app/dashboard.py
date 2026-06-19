"""Deterministic dashboard data for the Home view (no LLM)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import MATURITY_DAYS_AHEAD, OBLIGATION_DAYS_AHEAD, RECENT_TRACK_DAYS, RECENT_TRACK_LIMIT
from app.db import (
    get_account,
    get_position,
    list_documents_with_extracted_position,
    list_documents_with_extracted_obligation,
    list_ira_overview,
    list_obligations,
    list_positions,
    list_recent_positions,
    list_recent_obligations,
    get_positions_by_document_id,
    get_obligations_by_document_id,
)
from app.triggers import evaluate_triggers, _parse_date


def _days_until(event_date: str | None, now: datetime) -> int | None:
    d = _parse_date(event_date)
    if not d:
        return None
    return (d.date() - now.date()).days


def _position_item(row: tuple, conn: Any, now: datetime) -> dict[str, Any]:
    pos_id, account_id, asset_type, desc, principal, rate_apr, maturity_date, doc_id, _, _ = row[:10]
    start_date = row[10] if len(row) > 10 else None
    next_action = row[11] if len(row) > 11 else None
    liquidity_note = row[12] if len(row) > 12 else None
    acc = get_account(conn, account_id)
    acc_name = acc[1] if acc else account_id
    institution = acc[3] if acc else None
    label_parts = [asset_type]
    if desc:
        label_parts.append(desc)
    label = " ".join(label_parts)
    days = _days_until(maturity_date, now)
    return {
        "id": pos_id,
        "account_id": account_id,
        "account_name": acc_name,
        "institution": institution,
        "asset_type": asset_type,
        "description": desc,
        "principal": principal,
        "rate_apr": rate_apr,
        "maturity_date": maturity_date,
        "document_id": doc_id,
        "start_date": start_date,
        "next_action": next_action,
        "liquidity_note": liquidity_note,
        "label": label,
        "days_until": days,
    }


def _obligation_item(row: tuple, now: datetime) -> dict[str, Any]:
    obl_id, description, due_date, amount_estimate, priority, doc_id, _ = row
    days = _days_until(due_date, now)
    return {
        "id": obl_id,
        "description": description,
        "due_date": due_date,
        "amount_estimate": amount_estimate,
        "priority": priority,
        "document_id": doc_id,
        "days_until": days,
    }


def _format_money(amount: float | None) -> str:
    if amount is None:
        return ""
    return f"${amount:,.0f}"


def _recent_position_label(row: tuple, conn: Any) -> str:
    _, account_id, asset_type, desc, principal, _, maturity_date, *_rest = row[:10]
    acc = get_account(conn, account_id)
    institution = acc[3] if acc and acc[3] else (acc[1] if acc else None)
    parts = [asset_type or "CD"]
    if institution:
        parts.append(f"at {institution}")
    if principal is not None:
        parts.append(_format_money(principal))
    if maturity_date:
        parts.append(f"matures {maturity_date}")
    elif desc:
        parts.append(desc)
    return " · ".join(parts)


def _recent_obligation_label(row: tuple) -> str:
    _, description, due_date, amount_estimate, _, _, _ = row
    parts = []
    if description:
        parts.append(description)
    if amount_estimate is not None:
        parts.append(_format_money(amount_estimate))
    if due_date:
        parts.append(f"due {due_date}")
    return " · ".join(parts) if parts else "Bill"




def _build_recently_added(conn: Any, now: datetime) -> list[dict[str, Any]]:
    import time

    since_ts = int(now.timestamp()) - RECENT_TRACK_DAYS * 86400
    items: list[dict[str, Any]] = []
    for row in list_recent_positions(conn, since_ts, RECENT_TRACK_LIMIT):
        items.append(
            {
                "kind": "position",
                "id": row[0],
                "label": _recent_position_label(row, conn),
                "document_id": row[7],
                "created_at": row[8],
            }
        )
    for row in list_recent_obligations(conn, since_ts, RECENT_TRACK_LIMIT):
        items.append(
            {
                "kind": "obligation",
                "id": row[0],
                "label": _recent_obligation_label(row),
                "document_id": row[5],
                "created_at": row[6],
            }
        )
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return items[:RECENT_TRACK_LIMIT]


def build_dashboard(conn: Any, days: int = 365) -> dict[str, Any]:
    """Build dashboard payload for GET /dashboard."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)

    positions = list_positions(conn)
    obligations = list_obligations(conn)

    with_maturity: list[tuple[Any, ...]] = []
    overdue: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    next_maturity: dict[str, Any] | None = None
    next_maturity_days: int | None = None

    for row in positions:
        maturity_date = row[6]
        if maturity_date is None or not str(maturity_date).strip():
            continue
        with_maturity.append(row)
        d = _parse_date(maturity_date)
        if not d:
            continue
        item = _position_item(row, conn, now)
        if d.date() < now.date():
            overdue.append(item)
        else:
            days_left = item["days_until"]
            if days_left is not None and (next_maturity_days is None or days_left < next_maturity_days):
                next_maturity = item
                next_maturity_days = days_left
            if d <= cutoff:
                upcoming.append(item)

    upcoming.sort(key=lambda x: x.get("maturity_date") or "")
    overdue.sort(key=lambda x: x.get("maturity_date") or "", reverse=True)

    upcoming_obligations: list[dict[str, Any]] = []
    overdue_obligations: list[dict[str, Any]] = []
    for row in obligations:
        due_date = row[2]
        d = _parse_date(due_date)
        if not d:
            continue
        item = _obligation_item(row, now)
        if d.date() < now.date():
            overdue_obligations.append(item)
        elif d <= cutoff:
            upcoming_obligations.append(item)
    upcoming_obligations.sort(key=lambda x: x.get("due_date") or "")
    overdue_obligations.sort(key=lambda x: x.get("due_date") or "", reverse=True)

    triggers = evaluate_triggers(
        conn,
        maturity_days_ahead=MATURITY_DAYS_AHEAD,
        obligation_days_ahead=OBLIGATION_DAYS_AHEAD,
        persist=False,
    )
    actionable = len(triggers) > 0
    days_label = max(MATURITY_DAYS_AHEAD, OBLIGATION_DAYS_AHEAD)
    renewal_tips: list[str] = []
    if actionable:
        status = "actionable"
        memo = f"You have {len(triggers)} item(s) needing attention in the next {days_label} days."
        maturity_triggers = [t for t in triggers if t[1] == "maturity" and t[2] == "position"]
        obligation_triggers = [
            t for t in triggers if t[1] == "obligation_due" and t[2] == "obligation"
        ]

        has_cd_tips = False
        for t in maturity_triggers:
            pos = get_position(conn, t[3])
            if pos:
                _, account_id, asset_type, desc, principal, _, maturity_date, *_rest = pos
                acc = get_account(conn, account_id)
                acc_name = acc[1] if acc else "your account"
                label = asset_type + (f" {desc}" if desc else "")
                amt = f" ({format(principal, ',.0f')} dollars)" if principal is not None else ""
                renewal_tips.append(
                    f"Your {label}{amt} at {acc_name} matures on {maturity_date}."
                )
                renewal_tips.append(
                    "Decide whether to renew, withdraw, or move the funds."
                )
                has_cd_tips = True
        if has_cd_tips:
            renewal_tips.extend([
                "Contact your institution before the date if you want to renew or withdraw.",
                "Compare current rates before automatically renewing a CD.",
            ])

        for t in obligation_triggers:
            for row in obligations:
                if row[0] == t[3]:
                    renewal_tips.append(
                        f"Pay or schedule: {row[1]} due {row[2]}."
                    )
                    break
        if not renewal_tips:
            renewal_tips.append("Review upcoming maturity and due dates with your bank or advisor.")
    else:
        status = "no_action_required"
        if with_maturity:
            memo = f"No action required in the next {days_label} days."
        else:
            memo = "No maturities or due dates tracked yet. Add a document or position to get started."

    actionable_position_ids = {
        t[3] for t in triggers if t[1] == "maturity" and t[2] == "position"
    }
    actionable_obligation_ids = {
        t[3] for t in triggers if t[1] == "obligation_due" and t[2] == "obligation"
    }

    display_next_maturity = None if actionable else next_maturity

    upcoming = [i for i in upcoming if i["id"] not in actionable_position_ids]
    if display_next_maturity:
        upcoming = [i for i in upcoming if i["id"] != display_next_maturity["id"]]

    upcoming_obligations = [
        i for i in upcoming_obligations if i["id"] not in actionable_obligation_ids
    ]

    totals: dict[str, float] = {}
    for row in positions:
        asset_type = (row[2] or "Other").strip() or "Other"
        principal = row[4]
        if principal is not None:
            totals[asset_type] = totals.get(asset_type, 0.0) + float(principal)

    pending: list[dict[str, Any]] = []
    for doc_row in list_documents_with_extracted_position(conn):
        doc_id, title, extracted_json = doc_row[0], doc_row[1], doc_row[2]
        if get_positions_by_document_id(conn, doc_id):
            continue
        try:
            import json

            extracted = json.loads(extracted_json) if extracted_json else None
        except (json.JSONDecodeError, TypeError):
            extracted = None
        if not extracted or not isinstance(extracted, dict):
            continue
        if not extracted.get("maturity_date"):
            continue
        pending.append(
            {
                "document_id": doc_id,
                "title": title,
                "extraction": extracted,
            }
        )

    pending_obligations: list[dict[str, Any]] = []
    for doc_row in list_documents_with_extracted_obligation(conn):
        doc_id, title, extracted_json = doc_row[0], doc_row[1], doc_row[2]
        if get_obligations_by_document_id(conn, doc_id):
            continue
        try:
            import json

            extracted = json.loads(extracted_json) if extracted_json else None
        except (json.JSONDecodeError, TypeError):
            extracted = None
        if not extracted or not isinstance(extracted, dict):
            continue
        if not extracted.get("due_date"):
            continue
        pending_obligations.append(
            {
                "document_id": doc_id,
                "title": title,
                "extraction": extracted,
            }
        )

    ladder_positions: list[dict[str, Any]] = []
    for row in positions:
        maturity_date = row[6]
        if maturity_date is None or not str(maturity_date).strip():
            continue
        asset_type = (row[2] or "").strip().lower()
        if asset_type not in ("cd", "money market", "treasury", "brokered cd"):
            if "cd" not in asset_type and "money" not in asset_type:
                continue
        ladder_positions.append(_position_item(row, conn, now))
    ladder_positions.sort(key=lambda x: x.get("maturity_date") or "")

    ira_overview: list[dict[str, Any]] = []
    for row in list_ira_overview(conn):
        ira_id, account_name, institution, account_type, balance_estimate, rmd_note, next_date, doc_id, _, _ = row
        ira_overview.append(
            {
                "id": ira_id,
                "account_name": account_name,
                "institution": institution,
                "account_type": account_type,
                "balance_estimate": balance_estimate,
                "rmd_note": rmd_note,
                "next_relevant_date": next_date,
                "days_until": _days_until(next_date, now),
            }
        )

    return {
        "status": status,
        "actionable": actionable,
        "memo": memo,
        "trigger_count": len(triggers),
        "trigger_days_ahead": days_label,
        "renewal_tips": renewal_tips,
        "next_maturity": display_next_maturity,
        "upcoming_maturing": upcoming,
        "overdue_maturing": overdue,
        "upcoming_obligations": upcoming_obligations,
        "overdue_obligations": overdue_obligations,
        "totals_by_asset_type": totals,
        "pending_extractions": pending,
        "pending_obligation_extractions": pending_obligations,
        "recently_added": _build_recently_added(conn, now),
        "days_window": days,
        "ladder_positions": ladder_positions,
        "ira_overview": ira_overview,
    }
