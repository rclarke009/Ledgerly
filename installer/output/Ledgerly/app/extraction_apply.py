"""Apply structured document extractions as positions or obligations."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from app.db import (
    clear_document_extracted_obligation,
    clear_document_extracted_position,
    get_obligations_by_document_id,
    get_positions_by_document_id,
    insert_obligation,
    insert_position,
    list_accounts,
    list_documents_with_extracted_obligation,
    list_documents_with_extracted_position,
    set_document_linked_account,
)
from app.models import ExtractedObligation, ExtractedPosition, ObligationResponse, PositionResponse

logger = logging.getLogger(__name__)


def find_or_create_account_for_extraction(
    conn: Any,
    institution: str | None,
    doc_id: str,
    now: int,
) -> str:
    label = (institution or "").strip() or "My account"
    for row in list_accounts(conn):
        if institution and row[3] and str(row[3]).strip().lower() == institution.strip().lower():
            return row[0]
        if str(row[1]).strip().lower() == label.lower():
            return row[0]
    acc_id = str(uuid.uuid4())
    from app.db import insert_account

    insert_account(conn, acc_id, label, now, type=None, institution=institution, document_id=doc_id)
    return acc_id


def _load_pending_position_extraction(
    conn: Any,
    document_id: str,
    overrides: ExtractedPosition | None,
) -> ExtractedPosition | None:
    if overrides is not None:
        return overrides
    for prow in list_documents_with_extracted_position(conn):
        if prow[0] == document_id:
            raw_json = prow[2]
            if not raw_json:
                return None
            try:
                return ExtractedPosition(**json.loads(raw_json))
            except (json.JSONDecodeError, TypeError, ValueError):
                return None
    return None


def _load_pending_obligation_extraction(
    conn: Any,
    document_id: str,
    overrides: ExtractedObligation | None,
) -> ExtractedObligation | None:
    if overrides is not None:
        return overrides
    for prow in list_documents_with_extracted_obligation(conn):
        if prow[0] == document_id:
            raw_json = prow[2]
            if not raw_json:
                return None
            try:
                return ExtractedObligation(**json.loads(raw_json))
            except (json.JSONDecodeError, TypeError, ValueError):
                return None
    return None


def apply_position_extraction(
    conn: Any,
    document_id: str,
    extracted: ExtractedPosition | None = None,
    overrides: ExtractedPosition | None = None,
) -> PositionResponse | None:
    """Create a position from pending extraction. Returns None if nothing to apply."""
    existing = get_positions_by_document_id(conn, document_id)
    if existing:
        row = existing[0]
        clear_document_extracted_position(conn, document_id)
        return PositionResponse(
            id=row[0],
            account_id=row[1],
            asset_type=row[2],
            description=row[3],
            principal=row[4],
            rate_apr=row[5],
            maturity_date=row[6],
            document_id=row[7],
            created_at=row[8],
            updated_at=row[9],
        )

    parsed = extracted or _load_pending_position_extraction(conn, document_id, overrides)
    if parsed is None:
        return None
    if not parsed.maturity_date:
        logger.warning("auto-track position: missing maturity_date for doc %s", document_id)
        return None

    now = int(time.time())
    acc_id = find_or_create_account_for_extraction(conn, parsed.institution, document_id, now)
    pos_id = str(uuid.uuid4())
    insert_position(
        conn,
        pos_id,
        acc_id,
        parsed.asset_type or "CD",
        now,
        now,
        parsed.description,
        parsed.principal,
        parsed.rate_apr,
        parsed.maturity_date,
        document_id,
    )
    set_document_linked_account(conn, document_id, acc_id)
    clear_document_extracted_position(conn, document_id)
    return PositionResponse(
        id=pos_id,
        account_id=acc_id,
        asset_type=parsed.asset_type or "CD",
        description=parsed.description,
        principal=parsed.principal,
        rate_apr=parsed.rate_apr,
        maturity_date=parsed.maturity_date,
        document_id=document_id,
        created_at=now,
        updated_at=now,
    )


def apply_obligation_extraction(
    conn: Any,
    document_id: str,
    extracted: ExtractedObligation | None = None,
    overrides: ExtractedObligation | None = None,
) -> ObligationResponse | None:
    """Create an obligation from pending extraction. Returns None if nothing to apply."""
    existing = get_obligations_by_document_id(conn, document_id)
    if existing:
        row = existing[0]
        clear_document_extracted_obligation(conn, document_id)
        return ObligationResponse(
            id=row[0],
            description=row[1],
            due_date=row[2],
            amount_estimate=row[3],
            priority=row[4],
            document_id=row[5],
            created_at=row[6],
        )

    parsed = extracted or _load_pending_obligation_extraction(conn, document_id, overrides)
    if parsed is None:
        return None
    if not parsed.due_date:
        logger.warning("auto-track obligation: missing due_date for doc %s", document_id)
        return None

    now = int(time.time())
    obl_id = str(uuid.uuid4())
    insert_obligation(
        conn,
        obl_id,
        parsed.description,
        parsed.due_date,
        now,
        parsed.amount_estimate,
        parsed.priority,
        document_id,
    )
    clear_document_extracted_obligation(conn, document_id)
    return ObligationResponse(
        id=obl_id,
        description=parsed.description,
        due_date=parsed.due_date,
        amount_estimate=parsed.amount_estimate,
        priority=parsed.priority,
        document_id=document_id,
        created_at=now,
    )
