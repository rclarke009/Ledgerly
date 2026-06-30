import sqlite3
import time

from app.dashboard import build_dashboard
from app.db import create_db, insert_account, insert_position, insert_obligation


def _conn(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "dash.sqlite"))
    create_db(conn)
    return conn


def test_dashboard_empty(tmp_path):
    conn = _conn(tmp_path)
    data = build_dashboard(conn)
    assert data["status"] == "no_action_required"
    assert data["next_maturity"] is None
    assert data["upcoming_maturing"] == []
    conn.close()


def test_dashboard_upcoming_maturity(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    from datetime import datetime, timedelta, timezone

    future = (datetime.now(timezone.utc) + timedelta(days=120)).strftime("%Y-%m-%d")
    insert_account(conn, "acc1", "Chase", now, institution="Chase Bank")
    insert_position(
        conn,
        "pos1",
        "acc1",
        "CD",
        now,
        now,
        "12-month CD",
        50000.0,
        4.5,
        future,
        None,
    )
    conn.commit()
    data = build_dashboard(conn)
    assert data["next_maturity"] is not None
    assert data["next_maturity"]["maturity_date"] == future
    assert data["upcoming_maturing"] == []
    assert data["totals_by_asset_type"]["CD"] == 50000.0
    conn.close()


def test_dashboard_ladder_positions(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    from datetime import datetime, timedelta, timezone

    future = (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%d")
    insert_account(conn, "acc1", "PenFed", now, institution="PenFed")
    insert_position(
        conn,
        "pos1",
        "acc1",
        "CD",
        now,
        now,
        "12-mo",
        25000.0,
        4.5,
        future,
        None,
        start_date="2025-06-01",
        next_action="renew",
    )
    conn.commit()
    data = build_dashboard(conn)
    assert len(data["ladder_positions"]) == 1
    assert data["ladder_positions"][0]["institution"] == "PenFed"
    assert data["ladder_positions"][0]["next_action"] == "renew"
    conn.close()


def test_dashboard_actionable_within_30_days(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d")
    insert_account(conn, "acc1", "Bank", now)
    insert_position(conn, "pos1", "acc1", "CD", now, now, None, 1000.0, None, soon, None)
    conn.commit()
    data = build_dashboard(conn)
    assert data["actionable"] is True
    assert data["status"] == "actionable"
    assert len(data["renewal_tips"]) >= 4
    assert any(t.endswith(soon + ".") for t in data["renewal_tips"])
    assert any("Decide whether to renew" in t for t in data["renewal_tips"])
    assert data["next_maturity"] is None
    assert data["upcoming_maturing"] == []
    assert data["trigger_days_ahead"] >= 30
    conn.close()


def test_dashboard_actionable_cd_and_obligation_grouped(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d")
    due = (datetime.now(timezone.utc) + timedelta(days=12)).strftime("%Y-%m-%d")
    insert_account(conn, "acc1", "Riverside Community Credit Union", now)
    insert_position(conn, "pos1", "acc1", "CD", now, now, None, 25000.0, None, soon, None)
    insert_obligation(conn, "obl1", "Mortgage Statement - July 2026", due, now)
    conn.commit()
    data = build_dashboard(conn)
    tips = data["renewal_tips"]
    assert data["actionable"] is True
    cd_idx = next(i for i, t in enumerate(tips) if "matures on" in t)
    decide_idx = next(i for i, t in enumerate(tips) if "Decide whether to renew" in t)
    contact_idx = next(i for i, t in enumerate(tips) if "Contact your institution" in t)
    compare_idx = next(i for i, t in enumerate(tips) if "Compare current rates" in t)
    mortgage_idx = next(i for i, t in enumerate(tips) if "Mortgage Statement" in t)
    assert cd_idx < decide_idx < contact_idx < compare_idx < mortgage_idx
    conn.close()


def test_dashboard_actionable_multi_cd(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d")
    later = (datetime.now(timezone.utc) + timedelta(days=200)).strftime("%Y-%m-%d")
    insert_account(conn, "acc1", "Bank", now)
    insert_position(conn, "pos1", "acc1", "CD", now, now, "Urgent CD", 1000.0, None, soon, None)
    insert_position(conn, "pos2", "acc1", "CD", now, now, "Later CD", 2000.0, None, later, None)
    conn.commit()
    data = build_dashboard(conn)
    assert data["actionable"] is True
    assert data["next_maturity"] is None
    assert len(data["upcoming_maturing"]) == 1
    assert data["upcoming_maturing"][0]["id"] == "pos2"
    assert data["upcoming_maturing"][0]["maturity_date"] == later
    assert any("Urgent CD" in t for t in data["renewal_tips"])
    conn.close()


def test_dashboard_api(client):
    res = client.get("/dashboard")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] in ("no_action_required", "actionable")
    assert "memo" in body
    assert "renewal_tips" in body
    assert "trigger_days_ahead" in body

def test_dashboard_recently_added(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    insert_account(conn, "acc1", "Bank", now)
    insert_position(conn, "pos-recent", "acc1", "CD", now, now, "Recent CD", 1000.0, None, "2028-01-01", None)
    insert_obligation(conn, "obl-recent", "Tax bill", "2026-05-01", now, 500.0, "high", None)
    conn.commit()
    data = build_dashboard(conn)
    recent = data.get("recently_added") or []
    assert len(recent) >= 2
    kinds = {item["kind"] for item in recent}
    assert "position" in kinds
    assert "obligation" in kinds
    conn.close()
