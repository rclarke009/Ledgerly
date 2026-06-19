import sqlite3
import time

import pytest

from app.db import create_db, insert_account, insert_obligation, insert_position
from app.decision_memo import (
    liquidity_cross_check,
    build_maturity_memo_sections,
    action_threshold_met,
)
from app.reference_data import fetch_cd_rates


def _conn(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "memo.sqlite"))
    create_db(conn)
    return conn


def test_liquidity_cross_check_no_obligations(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    insert_account(conn, "acc1", "Bank", now)
    insert_position(conn, "p1", "acc1", "CD", now, now, None, 50000.0, 4.5, "2026-06-17", None)
    conn.commit()
    result = liquidity_cross_check(conn, "p1", "2026-06-17", 50000.0)
    assert result["nearby_obligations"] == []
    assert result["needs_liquid"] is False
    conn.close()


def test_liquidity_cross_check_coverage_gap(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    insert_account(conn, "acc1", "Bank", now)
    insert_position(conn, "p1", "acc1", "CD", now, now, None, 10000.0, 4.5, "2026-06-17", None)
    insert_obligation(conn, "o1", "Property tax", "2026-06-20", now, 25000.0, None, None)
    conn.commit()
    result = liquidity_cross_check(conn, "p1", "2026-06-17", 10000.0)
    assert len(result["nearby_obligations"]) == 1
    assert result["needs_liquid"] is True
    assert result["covers_obligations"] is False
    conn.close()


def test_action_threshold_met_on_liquidity():
    met, reason = action_threshold_met(
        rate_comparison={"meaningful": False, "delta": 0},
        liquidity={"needs_liquid": True},
        maturing_soon=False,
    )
    assert met is True
    assert "obligation" in reason.lower()


@pytest.mark.asyncio
async def test_build_maturity_memo_sections(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    insert_account(conn, "acc1", "PenFed", now, institution="PenFed")
    insert_position(conn, "p1", "acc1", "CD", now, now, "12-mo", 50000.0, 4.5, "2026-06-17", None)
    conn.commit()
    rate_infos = await fetch_cd_rates()
    section = build_maturity_memo_sections(conn, "p1", "2026-06-17", rate_infos)
    assert section.get("trigger")
    assert section.get("recommendation")
    assert section.get("confidence", {}).get("status") in ("provisional", "final")
    conn.close()
